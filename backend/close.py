"""Month-end close — what's reconciled, what's missing, who to chase.

Reads finance.month_end_close / finance.payables / finance.payroll /
finance.invoices / finance.bank from the brain (all clearly-labelled SAMPLE
data). Nudges are DRAFT ONLY — nothing is ever sent.

Pure functions, no I/O, no server state — same contract as chaser.py:
main.py injects COMPANY_BRAIN, slack_feed asks via _ask_brain.
"""
import re
from datetime import datetime, timezone
from typing import Optional


def _money(n) -> str:
    try:
        return f"£{float(n):,.0f}"
    except (TypeError, ValueError):
        return "£?"


def _month(month: Optional[str] = None) -> str:
    return month or datetime.now(timezone.utc).strftime("%Y-%m")


def _fin(brain: dict) -> dict:
    return brain.get("finance", {}) or {}


def _close(brain: dict) -> dict:
    return _fin(brain).get("month_end_close", {}) or {}


def _steps(brain: dict) -> list:
    return _close(brain).get("steps", []) or []


def outstanding_steps(brain: dict) -> list:
    """Steps not yet reconciled — 'missing' or 'in_progress'."""
    return [s for s in _steps(brain) if s.get("status") != "reconciled"]


def close_status(brain: dict) -> dict:
    """% done + which steps are missing/in-progress, with owner + blocker."""
    steps = _steps(brain)
    done = [s for s in steps if s.get("status") == "reconciled"]
    out = [{
        "id": s.get("id"),
        "name": s.get("name"),
        "owner": s.get("owner"),
        "status": s.get("status"),
        "due": s.get("due"),
        "blocker": s.get("blocker"),
    } for s in outstanding_steps(brain)]
    total = len(steps)
    return {
        "period": _close(brain).get("period"),
        "total_steps": total,
        "reconciled": len(done),
        "percent_done": round(100 * len(done) / total) if total else None,
        "outstanding": out,
        "missing": [s for s in out if s["status"] == "missing"],
        "in_progress": [s for s in out if s["status"] == "in_progress"],
        "cites": ["finance.month_end_close"],
    }


def due_out(brain: dict, month: Optional[str] = None) -> dict:
    """Everything due OUT this month: unpaid payable invoices + recurring
    bills (finance.payables) + payroll. Total + line items."""
    m = _month(month)
    fin = _fin(brain)
    inv_due = [i for i in fin.get("invoices", [])
               if i.get("kind") == "payable" and i.get("status") != "paid"
               and str(i.get("due_date", "")).startswith(m)]
    bills = [p for p in fin.get("payables", [])
             if str(p.get("due_date", "")).startswith(m)]
    payroll = fin.get("payroll", {}) or {}
    pay_gbp = (payroll.get("monthly_gbp")
               if str(payroll.get("pay_day", "")).startswith(m) else None)
    total = (sum(i.get("amount_gbp") or 0 for i in inv_due)
             + sum(p.get("amount_gbp") or 0 for p in bills)
             + (pay_gbp or 0))
    return {
        "month": m,
        "invoice_payables": inv_due,
        "bills": bills,
        "payroll_gbp": pay_gbp,
        "pay_day": payroll.get("pay_day") if pay_gbp else None,
        "total_gbp": total,
        "cites": ["finance.invoices", "finance.payables", "finance.payroll"],
    }


def runway(brain: dict) -> dict:
    """cash / monthly burn, with the figures cited — never a stored number."""
    bank = _fin(brain).get("bank", {}) or {}
    bal, burn = bank.get("balance_gbp"), bank.get("monthly_burn_gbp")
    if bal is None or not burn:
        return {"error": "finance.bank.balance_gbp / monthly_burn_gbp "
                         "not in the brain yet",
                "cites": ["finance.bank"]}
    return {
        "balance_gbp": bal,
        "monthly_burn_gbp": burn,
        "runway_months": round(bal / burn, 1),
        "cites": ["finance.bank.balance_gbp", "finance.bank.monthly_burn_gbp"],
    }


def _nudge_text(brain: dict, owner: str, steps: list) -> str:
    st = close_status(brain)
    items = "; ".join(
        f"{s['name']} (due {s.get('due', '?')}"
        + (f", blocker: {s['blocker']}" if s.get("blocker") else "")
        + ")" for s in steps)
    channel = (brain.get("people", {}) or {}).get(
        "finance_approval_channel", "#finance-approvals")
    return (f"Hi {owner} — month-end close {st.get('period') or ''} is "
            f"{st.get('percent_done')}% done and these steps are still on "
            f"your plate: {items}. Can you update {channel} once they're "
            "reconciled?")


def draft_close_nudge(brain: dict, owner: Optional[str] = None) -> dict:
    """DRAFT Slack nudge(s) to whoever holds a missing/in-progress step.
    owner=None drafts one per owner with outstanding steps. Never sends."""
    out = outstanding_steps(brain)
    if owner:
        out = [s for s in out
               if (s.get("owner") or "").lower() == owner.strip().lower()]
        if not out:
            return {"error": f"no outstanding close steps owned by '{owner}'",
                    "draft_only": True,
                    "cites": ["finance.month_end_close"]}
    if not out:
        return {"drafts": [], "draft_only": True,
                "note": "nothing outstanding — close is fully reconciled",
                "cites": ["finance.month_end_close"]}
    by_owner = {}
    for s in out:
        by_owner.setdefault(s.get("owner") or "unassigned", []).append(s)
    drafts = [{"to": o,
               "text": _nudge_text(brain, o, steps),
               "steps": [s["id"] for s in steps],
               "channel_hint": "slack_dm"}
              for o, steps in by_owner.items()]
    return {"drafts": drafts, "draft_only": True,
            "period": _close(brain).get("period"),
            "cites": ["finance.month_end_close"]}


_DUE_RE = re.compile(r"(?i)due\s+out|due\s+this\s+month|what'?s\s+due|"
                     r"whats\s+due|going\s+out|payment\s+run|pay\s+run|"
                     r"when\s+do\s+we\s+pay")


def ask(question: str, brain: dict) -> Optional[dict]:
    """/ask-shaped answer ({answer, sources, matched}) for month-end close,
    runway and 'what's due out' questions; None if it's not ours so the
    caller falls through to explain_policy."""
    q = (question or "").lower()
    if not q:
        return None

    def _ans(answer, *sources):
        return {"answer": answer,
                "sources": [{"brain_key": k, "value": v} for k, v in sources],
                "matched": True}

    if "chase" in q or "nudge" in q:
        res = draft_close_nudge(brain)
        drafts = res.get("drafts") or []
        if not drafts:
            return _ans(res.get("note") or res.get("error")
                        or "No close nudges to draft.",
                        ("finance.month_end_close", _steps(brain)))
        listing = " | ".join(f"to {d['to']}: {d['text']}" for d in drafts)
        return _ans(f"Draft nudges (never sent): {listing}",
                    ("finance.month_end_close",
                     outstanding_steps(brain)))

    if "runway" in q or ("burn" in q and "rate" not in q):
        r = runway(brain)
        if r.get("error"):
            return _ans("Bank balance and monthly burn aren't in the brain "
                        "yet.", ("finance.bank", _fin(brain).get("bank", {})))
        return _ans(f"{_money(r['balance_gbp'])} in the bank ÷ "
                    f"{_money(r['monthly_burn_gbp'])}/month burn ≈ "
                    f"{r['runway_months']} months of runway.",
                    ("finance.bank.balance_gbp", r["balance_gbp"]),
                    ("finance.bank.monthly_burn_gbp",
                     r["monthly_burn_gbp"]))

    if _DUE_RE.search(q):
        d = due_out(brain)
        parts = [f"{i.get('id')} {i.get('counterparty')} "
                 f"{_money(i.get('amount_gbp'))} ({i.get('status')}, due "
                 f"{i.get('due_date')})" for i in d["invoice_payables"]]
        parts += [f"{p.get('supplier')} {_money(p.get('amount_gbp'))} "
                  f"(due {p.get('due_date')})" for p in d["bills"]]
        if d.get("payroll_gbp"):
            parts.append(f"payroll {_money(d['payroll_gbp'])} "
                         f"(pay day {d.get('pay_day')})")
        answer = (f"Due out {d['month']}: " + "; ".join(parts)
                  + f". Total ≈ {_money(d['total_gbp'])}."
                  if parts else f"Nothing due out in {d['month']}.")
        return _ans(answer, ("finance.invoices", d["invoice_payables"]),
                    ("finance.payables", d["bills"]),
                    ("finance.payroll", _fin(brain).get("payroll", {})))

    if any(k in q for k in ("close", "closing", "month-end", "month end",
                            "monthend", "reconcil", "blocking")):
        s = close_status(brain)
        if not s["total_steps"]:
            return _ans("No month-end close checklist in the brain yet.",
                        ("finance.month_end_close", {}))
        if not s["outstanding"]:
            return _ans(f"Close {s['period']} is fully reconciled — "
                        f"{s['reconciled']}/{s['total_steps']} steps done.",
                        ("finance.month_end_close", _steps(brain)))
        items = "; ".join(
            f"{o['name']} — {o['status']}, owner {o['owner']}"
            + (f" (blocker: {o['blocker']})" if o.get("blocker") else "")
            for o in s["outstanding"])
        return _ans(f"Close {s['period']} is {s['percent_done']}% done "
                    f"({s['reconciled']}/{s['total_steps']}). Outstanding: "
                    f"{items}.",
                    ("finance.month_end_close", _steps(brain)))

    return None
