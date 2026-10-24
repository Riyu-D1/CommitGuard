"""Action handlers for /execute-action (owner: Darsh).

Every action writes an audit line to audit_log.jsonl. STAGE_INVOICE also
appends to round_staging_queue.json (the mock Round Treasury pickup queue).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

BASE = Path(__file__).parent
AUDIT_PATH = BASE / "audit_log.jsonl"
STAGING_PATH = BASE / "round_staging_queue.json"

DEDUPE_ACTION_TYPES = {"STAGE_INVOICE", "ESCALATE_FRAUD"}
DEDUPE_WINDOW = timedelta(minutes=10)

VALID_ACTION_TYPES = {"SEND_APPROVED", "APPLY_REWRITE_AND_LOG", "APPROVE_OVERRIDE",
                      "STAGE_INVOICE", "ESCALATE_FRAUD"}


def audit(entry: dict) -> dict:
    now = datetime.now(timezone.utc)
    entry = {
        **entry,
        "audit_log_id": f"log_{uuid.uuid4().hex[:8]}",
        "ts": now.isoformat(),
        "epoch_ms": int(now.timestamp() * 1000),
    }
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_audit(limit: int = 20, type: str = None, result: str = None) -> list:
    """Newest-first audit entries.

    `type` filters to one action_type, `result` filters to one result value;
    both apply before the limit slice. (Query-param wiring belongs to
    Riyansh's main.py — do not edit it there.)
    """
    if not AUDIT_PATH.exists():
        return []
    entries = []
    for line in AUDIT_PATH.read_text().strip().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict):
            entries.append(e)
    if type is not None:
        entries = [e for e in entries if e.get("action_type") == type]
    if result is not None:
        entries = [e for e in entries if e.get("result") == result]
    return entries[-limit:][::-1] if limit > 0 else []


def _invoice_identifier(payload: dict):
    if not isinstance(payload, dict):
        return None
    for key in ("invoice", "invoice_id", "id", "vendor"):
        if payload.get(key):
            return payload[key]
    return None


def _dedupe_key(action_type: str, payload: dict):
    ident = _invoice_identifier(payload)
    return f"{action_type}|{ident}" if ident is not None else None


def _recent_duplicate(dedupe_key: str) -> bool:
    if not AUDIT_PATH.exists():
        return False
    now = datetime.now(timezone.utc)
    for line in AUDIT_PATH.read_text().strip().splitlines():
        try:
            e = json.loads(line)
            if not isinstance(e, dict):
                continue
            ts = datetime.fromisoformat(e["ts"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if now - ts > DEDUPE_WINDOW:
            continue
        if _dedupe_key(e.get("action_type"), e.get("payload")) == dedupe_key:
            return True
    return False


def execute_action(action_type: str, payload: dict, brain: dict) -> dict:
    if action_type not in VALID_ACTION_TYPES:
        raise HTTPException(400, f"Unknown action_type '{action_type}'")

    if action_type in DEDUPE_ACTION_TYPES:
        key = _dedupe_key(action_type, payload)
        if key and _recent_duplicate(key):
            entry = audit({"action_type": action_type, "payload": payload,
                           "result": "duplicate_rejected"})
            return {"success": False, "error": "duplicate",
                    "audit_log_id": entry["audit_log_id"],
                    "message": "Duplicate action within 10 minutes — rejected and logged."}

    if action_type == "STAGE_INVOICE":
        try:
            queue = json.loads(STAGING_PATH.read_text())
            if not isinstance(queue, list):
                queue = []
        except (json.JSONDecodeError, OSError):
            queue = []
        queue.append({**payload,
                      "staged_at": datetime.now(timezone.utc).isoformat(),
                      "invoice_ref": _invoice_identifier(payload)})
        STAGING_PATH.write_text(json.dumps(queue, indent=2))
        entry = audit({"action_type": action_type, "payload": payload,
                       "result": "staged_in_round_queue"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": "Invoice staged to Round Treasury approval queue."}

    if action_type == "APPROVE_OVERRIDE" and not payload.get("reason"):
        raise HTTPException(400, "Override requires a reason - it goes in the audit log.")

    if action_type == "ESCALATE_FRAUD":
        entry = audit({"action_type": action_type, "payload": payload,
                       "result": "escalated_to_cfo"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": f"Escalated to {brain.get('people', {}).get('cfo', 'CFO')} - payment blocked pending out-of-band verification."}

    entry = audit({"action_type": action_type, "payload": payload, "result": "ok"})
    return {"success": True, "audit_log_id": entry["audit_log_id"],
            "message": f"Processed {action_type} and wrote it to the audit trail."}
