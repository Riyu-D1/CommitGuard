"""Action handlers for /execute-action (owner: Darsh).

Every action writes an audit line to audit_log.jsonl. STAGE_INVOICE also
appends to round_staging_queue.json (the mock Round Treasury pickup queue).
HOLD_PAYMENT, VERIFY_VENDOR, REQUEST_CREDIT_NOTE and REQUEST_APPROVAL handle
the AuditTrace invoice-interceptor flow.
"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

BASE = Path(__file__).parent
AUDIT_PATH = BASE / "audit_log.jsonl"
STAGING_PATH = BASE / "round_staging_queue.json"

DEDUPE_ACTION_TYPES = {"STAGE_INVOICE", "ESCALATE_FRAUD", "HOLD_PAYMENT"}
DEDUPE_WINDOW = timedelta(minutes=10)

VALID_ACTION_TYPES = {"SEND_APPROVED", "APPLY_REWRITE_AND_LOG", "APPROVE_OVERRIDE",
                      "STAGE_INVOICE", "ESCALATE_FRAUD", "HOLD_PAYMENT",
                      "VERIFY_VENDOR", "REQUEST_CREDIT_NOTE",
                      "REQUEST_APPROVAL"}


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

    if action_type == "HOLD_PAYMENT":
        held = f" on {payload['invoice']}" if payload.get("invoice") else ""
        entry = audit({"action_type": action_type, "payload": payload,
                       "result": "payment_held"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": f"Payment held{held} — do not pay until the "
                           "vendor is verified out-of-band."}

    if action_type == "VERIFY_VENDOR":
        vendor = payload.get("vendor")
        phone = payload.get("phone_on_file")
        if vendor and phone:
            msg = (f"Verify {vendor} on {phone} — the number on file, "
                   "never the email.")
        elif vendor:
            msg = f"Verify {vendor} on the number on file — never the email."
        elif phone:
            msg = (f"Verify the vendor on {phone} — the number on file, "
                   "never the email.")
        else:
            msg = "Verify the vendor on the number on file — never the email."
        entry = audit({"action_type": action_type, "payload": payload,
                       "result": "vendor_verification_requested"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": msg}

    if action_type == "REQUEST_CREDIT_NOTE":
        delta = payload.get("delta_gbp")
        vendor = payload.get("vendor")
        amount = f"£{delta:g}" if isinstance(delta, (int, float)) else None
        if amount and vendor:
            msg = f"Credit note drafted for {amount} overage to {vendor}."
        elif amount:
            msg = f"Credit note drafted for {amount} overage."
        elif vendor:
            msg = f"Credit note drafted for the overage to {vendor}."
        else:
            msg = "Credit note drafted for the overage."
        entry = audit({"action_type": action_type, "payload": payload,
                       "result": "credit_note_drafted"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": msg}

    if action_type == "REQUEST_APPROVAL":
        entry = audit({"action_type": action_type, "payload": payload,
                       "result": "approval_requested"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": "Approval requested from "
                           f"{payload.get('target') or 'the approver'} — "
                           "holding until sign-off."}

    entry = audit({"action_type": action_type, "payload": payload, "result": "ok"})
    return {"success": True, "audit_log_id": entry["audit_log_id"],
            "message": f"Processed {action_type} and wrote it to the audit trail."}


def _evidence_value(violations: list, key: str):
    """First non-None evidence[key] across violations, else None."""
    for v in violations:
        ev = v.get("evidence")
        if isinstance(ev, dict) and ev.get(key) is not None:
            return ev[key]
    return None


def _evidence_vendor(violations: list):
    """Vendor named by a violation — an evidence.vendor extra, else parsed
    out of a `signed_contracts[Name].*` brain_key."""
    vendor = _evidence_value(violations, "vendor")
    if vendor:
        return vendor
    for v in violations:
        ev = v.get("evidence")
        if isinstance(ev, dict):
            m = re.match(r"signed_contracts\[(.+?)\]",
                         str(ev.get("brain_key", "")))
            if m:
                return m.group(1)
    return None


def _contract_phone(brain: dict, vendor):
    """contact_phone for `vendor` from signed_contracts — the number on file."""
    if not vendor:
        return None
    for c in brain.get("signed_contracts", []):
        if isinstance(c, dict) and c.get("vendor_name") == vendor:
            return c.get("contact_phone")
    return None


def plan_actions(result: dict, brain: dict) -> list:
    """Suggest next actions for a /verify-context result — pure, no side effects.

    Every target comes from the brain (people.cfo, finance_approval_channel);
    nothing is hardcoded. Deduped by action type.
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
                 "UNAPPROVED_PAYMENT", "NEW_VENDOR_BANK_CHANGE",
                 "BANK_DETAILS_MISMATCH", "DUPLICATE_INVOICE"}
    if (crit_cats & hold_cats) or (cats & {"UNAPPROVED_PAYMENT",
                                         "NEW_VENDOR_BANK_CHANGE",
                                         "DUPLICATE_INVOICE"}):
        hold_payload = {"violations": violations}
        if invoice_refs:
            hold_payload["invoices"] = invoice_refs
            hold_payload["invoice"] = invoice_refs[0]  # dedupe key
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
               "NEW_VENDOR_BANK_CHANGE", "BANK_DETAILS_MISMATCH",
               "DUPLICATE_INVOICE"}:
        vendor = _evidence_vendor(violations)
        if not vendor and invoice_refs:
            ledger = {i.get("id"): i for i in
                      brain.get("finance", {}).get("invoices", [])
                      if isinstance(i, dict)}
            vendor = next((ledger[r]["counterparty"] for r in invoice_refs
                           if r in ledger and ledger[r].get("counterparty")),
                          None)
        payload = {"violations": violations}
        if vendor:
            payload["vendor"] = vendor
        phone = (_evidence_value(violations, "phone_on_file")
                 or _contract_phone(brain, vendor))
        if phone:
            payload["phone_on_file"] = phone
        plan["VERIFY_VENDOR"] = {
            "type": "VERIFY_VENDOR",
            "label": (f"Verify {vendor} on the number on file — never the email"
                      if vendor else "Verify vendor bank details out-of-band"),
            "target": vendor,
            "payload": payload}

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

    if "INVOICE_OVER_CONTRACT" in cats:
        if "HOLD_PAYMENT" not in plan:
            hold_payload = {"violations": violations}
            if invoice_refs:
                hold_payload["invoices"] = invoice_refs
                hold_payload["invoice"] = invoice_refs[0]
            plan["HOLD_PAYMENT"] = {"type": "HOLD_PAYMENT",
                                    "label": "Hold payment — do not pay",
                                    "target": invoice_refs[0] if invoice_refs
                                    else None,
                                    "payload": hold_payload}
        delta = _evidence_value(violations, "delta_gbp")
        if delta is None:
            delta = _evidence_value(violations, "delta_gbp_per_hr")
        vendor = _evidence_vendor(violations)
        label = (f"Request credit note for £{delta:g} overage"
                 if isinstance(delta, (int, float))
                 else "Request credit note for the overage")
        plan["REQUEST_CREDIT_NOTE"] = {
            "type": "REQUEST_CREDIT_NOTE",
            "label": label,
            "target": vendor,
            "payload": {"delta_gbp": delta, "vendor": vendor,
                        "violations": violations}}

    if (cats & {"INVOICE_OVER_CONTRACT", "HIDDEN_CLAUSE",
               "TERMS_MISMATCH"}) and "REQUEST_APPROVAL" not in plan:
        import rules  # lazy — keeps actions.py importable without rules
        amount = max((v["evidence"]["amount_gbp"] for v in violations
                      if isinstance(v.get("evidence"), dict)
                      and isinstance(v["evidence"].get("amount_gbp"),
                                     (int, float))), default=None)
        tier = rules.spend_tier(amount, brain) if amount is not None else None
        approvers = None
        if tier and "self" not in tier.get("approver_roles", []):
            approvers = " + ".join(tier.get("approvers") or [])
        channel = people.get("finance_approval_channel")
        target = approvers or channel
        plan["REQUEST_APPROVAL"] = {
            "type": "REQUEST_APPROVAL",
            "label": (f"Request approval from {approvers}" if approvers
                      else f"Request approval in {channel}" if channel
                      else "Request approval"),
            "target": target,
            "payload": {"violations": violations, "target": target}}

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

    return list(plan.values())
