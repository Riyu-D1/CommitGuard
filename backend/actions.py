"""Action handlers for /execute-action (owner: Darsh).

Every action writes an audit line to audit_log.jsonl. STAGE_INVOICE also
appends to round_staging_queue.json (the mock Round Treasury pickup queue).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

BASE = Path(__file__).parent
AUDIT_PATH = BASE / "audit_log.jsonl"
STAGING_PATH = BASE / "round_staging_queue.json"


def audit(entry: dict) -> dict:
    entry = {
        "audit_log_id": f"log_{uuid.uuid4().hex[:8]}",
        "ts": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_audit(limit: int = 20) -> list:
    if not AUDIT_PATH.exists():
        return []
    lines = AUDIT_PATH.read_text().strip().splitlines()
    return [json.loads(l) for l in lines[-limit:]][::-1]


def execute_action(action_type: str, payload: dict, brain: dict) -> dict:
    if action_type == "STAGE_INVOICE":
        queue = json.loads(STAGING_PATH.read_text()) if STAGING_PATH.exists() else []
        queue.append({"staged_at": datetime.now(timezone.utc).isoformat(), **payload})
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
