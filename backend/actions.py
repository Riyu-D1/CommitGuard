"""Action handlers for /execute-action (owner: Darsh).

Every action writes an audit line to audit_log.jsonl. STAGE_INVOICE also
appends to round_staging_queue.json (the mock Round Treasury pickup queue).
"""

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
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


def _days_overdue(inv: dict, today: date) -> int:
    try:
        return max(0, (today - date.fromisoformat(str(inv.get("due_date", ""))[:10])).days)
    except ValueError:
        return 0


def _chase_hands(text: str, brain: dict) -> list:
    """Open receivables whose customer name or invoice no is mentioned in
    `text` — e.g. 'Acme still hasn't paid'. Pure scan; returns
    {invoice_id, counterparty, amount_gbp, days_overdue} rows."""
    if not text:
        return []
    today = date.today()
    hits = []
    for inv in brain.get("finance", {}).get("invoices", []):
        if inv.get("kind") != "receivable" or inv.get("status") == "paid":
            continue
        iid = str(inv.get("id") or "")
        name = str(inv.get("counterparty") or "")
        first = name.split()[0] if name else ""
        if not ((iid and iid.lower() in text.lower()) or
                (first and re.search(rf"(?i)\b{re.escape(first)}\b", text))):
            continue
        hits.append({"invoice_id": iid, "counterparty": name,
                     "amount_gbp": inv.get("amount_gbp"),
                     "days_overdue": _days_overdue(inv, today),
                     "status": inv.get("status")})
    return hits


def plan_actions(result: dict, brain: dict, text: str = None) -> list:
    """Suggest next actions for a /verify-context result — pure, no side effects.

    Every target comes from the brain (people.cfo, finance_approval_channel);
    nothing is hardcoded. Deduped by action type. `text` (optional) is the
    checked message — used to spot mentions of open receivables and offer a
    CHASE_INVOICE draft.
    """
    violations = result.get("violations") or []
    cats = {v.get("category") for v in violations}
    crit_cats = {v.get("category") for v in violations
                 if v.get("severity") == "CRITICAL"}
    people = brain.get("people", {})
    plan = {}

    # Invoice references carried in violation evidence (finance checks).
    invoice_refs = [v["evidence"]["invoice_id"] for v in violations
                    if isinstance(v.get("evidence"), dict)
                    and v["evidence"].get("invoice_id")]
    spend_approvers = next(
        (v["evidence"]["required_approvers"] for v in violations
         if v.get("category") == "SPEND_OVER_LIMIT"
         and isinstance(v.get("evidence"), dict)
         and v["evidence"].get("required_approvers")), None)

    hold_cats = {"PAYMENT_REDIRECTION", "URGENT_PAYMENT_CHANGE",
                 "UNAPPROVED_PAYMENT", "NEW_VENDOR_BANK_CHANGE"}
    if (crit_cats & hold_cats) or (cats & {"UNAPPROVED_PAYMENT",
                                         "NEW_VENDOR_BANK_CHANGE"}):
        hold_payload = {"violations": violations}
        if invoice_refs:
            hold_payload["invoices"] = invoice_refs
        plan["HOLD_PAYMENT"] = {"type": "HOLD_PAYMENT",
                                "label": "Hold payment — do not pay",
                                "target": invoice_refs[0] if invoice_refs
                                else None,
                                "payload": hold_payload}
        cfo = people.get("cfo")
        plan["ESCALATE"] = {"type": "ESCALATE",
                            "label": f"Escalate to {cfo}" if cfo else "Escalate to CFO",
                            "target": cfo,
                            "payload": {"violations": violations}}

    if cats & {"PAYMENT_REDIRECTION", "URGENT_PAYMENT_CHANGE",
               "NEW_VENDOR_BANK_CHANGE"}:
        plan["VERIFY_VENDOR"] = {
            "type": "VERIFY_VENDOR",
            "label": "Verify vendor bank details out-of-band",
            "target": None,
            "payload": {"violations": violations}}

    if cats & {"APPROVAL_REQUIRED", "SPEND_OVER_LIMIT",
               "UNAPPROVED_PAYMENT", "PAYMENT_OFF_CYCLE"}:
        channel = people.get("finance_approval_channel")
        target = " + ".join(spend_approvers) if spend_approvers else channel
        label = (f"Request approval from {target}" if spend_approvers
                 else f"Request approval in {channel}" if channel
                 else "Request approval")
        plan["REQUEST_APPROVAL"] = {
            "type": "REQUEST_APPROVAL",
            "label": label,
            "target": target,
            "payload": {"violations": violations}}

    if "CONFIDENTIAL_LEAK" in cats:
        plan["BLOCK_AND_REDACT"] = {
            "type": "BLOCK_AND_REDACT",
            "label": "Block send and redact confidential data",
            "target": None,
            "payload": {"violations": violations}}

    if cats & {"PRICE_FLOOR", "MARGIN_BREACH"}:
        payload = {}
        if result.get("suggested_rewrite"):
            payload["suggested_rewrite"] = result["suggested_rewrite"]
        plan["SUGGEST_REWRITE"] = {"type": "SUGGEST_REWRITE",
                                   "label": "Apply suggested rewrite",
                                   "target": None,
                                   "payload": payload}

    for hit in _chase_hands(text or "", brain):
        label = (f"Draft chase for {hit['invoice_id']} — {hit['counterparty']} "
                 f"£{(hit['amount_gbp'] or 0):,}"
                 + (f", {hit['days_overdue']}d overdue"
                    if hit["days_overdue"] else ""))
        plan[f"CHASE_INVOICE:{hit['invoice_id']}"] = {
            "type": "CHASE_INVOICE",
            "label": label,
            "target": hit["invoice_id"],
            "payload": {"invoice_id": hit["invoice_id"],
                        "customer": hit["counterparty"],
                        "draft_only": True}}

    return list(plan.values())
