"""Round Treasury payment queue (owner: Riyansh).

Every checked incoming invoice landing on the feed is sorted into a mock
payment queue: ready-to-pay when the planned actions stage it with no hold,
held when HOLD_PAYMENT / VERIFY_VENDOR / ESCALATE appear, with the reason
and the brain_key it cites. Persisted to treasury_queue.json (gitignored).

Nothing is ever paid — every entry is "staged for Round Treasury (sample
data, no money moves)". Approve/release only move labels around.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import audit_trace
import rules

BASE = Path(__file__).parent
STATUS_LABEL = "staged for Round Treasury (sample data, no money moves)"
HOLD_ACTIONS = {"HOLD_PAYMENT", "VERIFY_VENDOR", "ESCALATE", "ESCALATE_FRAUD"}
MAX_QUEUE = 200

_lock = threading.Lock()
_mem = None  # lazily loaded list of entry dicts


def _path() -> Path:
    override = os.environ.get("TREASURY_QUEUE_PATH")
    return Path(override) if override else BASE / "treasury_queue.json"


def _load() -> list:
    global _mem
    if _mem is not None:
        return _mem
    try:
        data = json.loads(_path().read_text())
        _mem = data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        _mem = []
    return _mem


def _save() -> None:
    try:
        _path().write_text(json.dumps(_mem or [], indent=2))
    except OSError:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reason(item: dict) -> dict:
    """Why an invoice is held — first violation's issue + cited brain_key."""
    for v in item.get("violations") or []:
        ev = v.get("evidence")
        return {
            "category": v.get("category"),
            "severity": v.get("severity"),
            "issue": v.get("issue"),
            "brain_key": (ev or {}).get("brain_key"),
            "expected": (ev or {}).get("expected"),
            "found": (ev or {}).get("found"),
        }
    types = [a.get("type") for a in item.get("actions") or []
             if a.get("type") in HOLD_ACTIONS]
    return {"category": None, "severity": item.get("risk_level"),
            "issue": f"held pending: {', '.join(types) or 'review'}",
            "brain_key": None, "expected": None, "found": None}


def _entry(item: dict, brain: dict) -> dict:
    text = item.get("text") or ""
    p = audit_trace.parse_invoice(text)
    vendor = p.get("vendor") or {}
    invoice_no = p.get("invoice_no")
    amount = max((v for _m, v in p.get("amounts") or []), default=None)

    ledger = {i.get("id"): i for i in
              brain.get("finance", {}).get("invoices", [])
              if isinstance(i, dict) and i.get("kind") == "payable"}
    payee = vendor.get("vendor_name")
    due_date = None
    for inv in ledger.values():
        if invoice_no and inv.get("id") == invoice_no:
            payee = payee or inv.get("counterparty")
            due_date = inv.get("due_date")
            amount = amount if amount is not None else inv.get("amount_gbp")
            break
    if not due_date and payee:
        match = next((i for i in ledger.values()
                      if i.get("counterparty") == payee
                      and i.get("status") != "paid"), None)
        if match:
            invoice_no = invoice_no or match.get("id")
            due_date = match.get("due_date")
            amount = amount if amount is not None else match.get("amount_gbp")
    payee = payee or "unknown vendor"

    tier = rules.spend_tier(amount, brain) if isinstance(amount, (int, float)) \
        else None
    action_types = {a.get("type") for a in item.get("actions") or []}
    hold_types = sorted(action_types & HOLD_ACTIONS)
    held = bool(hold_types)

    return {
        "id": f"TQ-{item.get('id')}",
        "feed_id": item.get("id"),
        "invoice_no": invoice_no,
        "payee": payee,
        "amount_gbp": amount,
        "due_date": due_date,
        "tier": (tier or {}).get("tier"),
        "approver": " + ".join(tier["approvers"]) if tier else None,
        "state": "held" if held else "ready",
        "status_label": STATUS_LABEL,
        "hold_actions": hold_types,
        "reason": _reason(item) if held else None,
        "violations": [{"category": v.get("category"),
                        "severity": v.get("severity"),
                        "issue": v.get("issue"),
                        "brain_key": (v.get("evidence") or {}).get("brain_key")}
                       for v in item.get("violations") or []],
        "approved_by": None,
        "approved_at": None,
        "released_by": None,
        "released_at": None,
        "source": item.get("source"),
        "user": item.get("user"),
        "created_at": _now(),
        "updated_at": _now(),
    }


def ingest_feed_item(item: dict, brain: dict) -> dict:
    """slack_feed listener — fold one checked incoming_invoice feed item into
    the queue. Dedupes on invoice_no (then feed_id): re-verdicts update the
    existing row. Returns the entry, or None for non-invoice items."""
    if item.get("kind") != "check" or \
            item.get("context_type") != "incoming_invoice":
        return None
    entry = _entry(item, brain)
    with _lock:
        q = _load()
        existing = next(
            (e for e in q
             if (entry["invoice_no"] and
                 e.get("invoice_no") == entry["invoice_no"])
             or e.get("feed_id") == entry["feed_id"]), None)
        if existing:
            keep = {k: existing[k] for k in
                    ("approved_by", "approved_at", "released_by",
                     "released_at", "created_at", "id")
                    if existing.get(k) is not None}
            existing.update(entry)
            existing.update(keep)
            if existing["state"] == "held" and keep.get("released_by"):
                existing["state"] = "held"  # a fresh hold beats an old release
            entry = existing
        else:
            q.append(entry)
            del q[:-MAX_QUEUE]
        _save()
    return entry


def _find(qid: str):
    for e in _load():
        if e.get("id") == qid:
            return e
    return None


def list_queue() -> dict:
    """GET /treasury/queue payload — newest first."""
    items = list(reversed(_load()))
    ready = [e for e in items if e.get("state") in ("ready", "approved")]
    held = [e for e in items if e.get("state") == "held"]
    return {
        "items": items,
        "ready": len(ready),
        "held": len(held),
        "approved": sum(1 for e in items if e.get("state") == "approved"),
        "total_ready_gbp": sum(e.get("amount_gbp") or 0
                               for e in ready if e.get("state") == "ready"),
        "status_label": STATUS_LABEL,
        "sample_data": True,
    }


def approve(qid: str, by: str):
    """Mark a ready item approved by name — still no payment moves."""
    with _lock:
        e = _find(qid)
        if e is None:
            return None, f"queue item {qid} not found"
        if e.get("state") == "held":
            return None, (f"{qid} is held — release the hold first "
                          f"({(e.get('reason') or {}).get('category') or 'review'})")
        e["state"] = "approved"
        e["approved_by"] = (by or "api").strip() or "api"
        e["approved_at"] = _now()
        e["updated_at"] = e["approved_at"]
        _save()
        return e, None


def release_hold(qid: str, by: str):
    """Release a held item back to ready. The reason stays on the record."""
    with _lock:
        e = _find(qid)
        if e is None:
            return None, f"queue item {qid} not found"
        if e.get("state") != "held":
            return None, f"{qid} is not held"
        e["state"] = "ready"
        e["released_by"] = (by or "api").strip() or "api"
        e["released_at"] = _now()
        e["updated_at"] = e["released_at"]
        _save()
        return e, None


def ask_summary(brain: dict) -> dict:
    """'what's ready to pay' — /ask-compatible answer citing the queue."""
    items = _load()
    ready = [e for e in items if e.get("state") == "ready"]
    approved = [e for e in items if e.get("state") == "approved"]
    held = [e for e in items if e.get("state") == "held"]
    total = sum(e.get("amount_gbp") or 0 for e in ready)
    if not items:
        return {"matched": True,
                "answer": "Nothing in the Round Treasury queue yet — checked "
                          "incoming invoices land here automatically.",
                "sources": ["treasury.queue"]}
    bits = [f"{len(ready)} ready ({_gbp(total)}"
            + (f", {len(approved)} approved" if approved else "") + ")"]
    bits += [f"· {e.get('invoice_no') or e['id']} {e.get('payee')} "
             f"{_gbp(e.get('amount_gbp'))}"
             + (f" — approver {e['approver']}" if e.get("approver") else "")
             for e in ready[:5]]
    if held:
        bits.append(f"· {len(held)} HELD — " + "; ".join(
            f"{e.get('invoice_no') or e['id']}: "
            f"{(e.get('reason') or {}).get('category') or 'review'}"
            + (f" ({(e.get('reason') or {}).get('brain_key')})"
               if (e.get('reason') or {}).get('brain_key') else "")
            for e in held[:3]))
    bits.append("All staged for Round Treasury — sample data, no money moves.")
    return {"matched": True, "answer": "\n".join(bits),
            "sources": ["treasury.queue", "finance.spend_approvals"]}


def _gbp(x) -> str:
    return f"£{(x or 0):,.0f}"
