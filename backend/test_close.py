"""Month-end close unit tests — offline, no server, no API key needed.

  uv run python test_close.py

Reads the real company_brain.json but never writes to it. Exits 1 and
prints every failure.
"""
import json
import os
import sys
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)  # force the deterministic path

import close  # noqa: E402
import slack_feed  # noqa: E402
import main  # noqa: E402  (COMPANY_BRAIN loaded once, like the server)

BASE = Path(__file__).parent
BRAIN = json.loads((BASE / "company_brain.json").read_text())
STEPS = BRAIN["finance"]["month_end_close"]["steps"]

failures = []


def check(name, cond, detail=""):
    print(f"  {name:<34} {'PASS' if cond else 'FAIL'} {detail}")
    if not cond:
        failures.append(name)


print("== close_status ==")
s = close.close_status(BRAIN)
check("period", s["period"] == "2026-10")
check("counts", s["total_steps"] == 7 and s["reconciled"] == 3
      and s["percent_done"] == 43, str(s["percent_done"]))
check("outstanding split", len(s["outstanding"]) == 4
      and len(s["missing"]) == 2 and len(s["in_progress"]) == 2)
by_id = {o["id"]: o for o in s["outstanding"]}
check("owner + blocker", by_id["ar-review"]["owner"] == "Riyansh"
      and "overdue" in (by_id["ar-review"]["blocker"] or ""))
check("no reconciled in outstanding",
      all(o["status"] != "reconciled" for o in s["outstanding"]))
check("cites", "finance.month_end_close" in s["cites"])

print("== due_out ==")
d = close.due_out(BRAIN, "2026-10")
check("invoice payables",
      {i["id"] for i in d["invoice_payables"]}
      == {"INV-1043", "INV-1044", "INV-1037"},
      str([i["id"] for i in d["invoice_payables"]]))
check("paid + next-month excluded",
      all(i["status"] != "paid" for i in d["invoice_payables"]))
check("bills", {p["supplier"] for p in d["bills"]}
      == {"WeWork City Road", "GitHub Enterprise"})
check("payroll", d["payroll_gbp"] == 38000 and d["pay_day"] == "2026-10-28")
check("total", d["total_gbp"] == 6200 + 3200 + 4200 + 2800 + 450 + 38000,
      str(d["total_gbp"]))
d2 = close.due_out(BRAIN, "2026-11")
check("nov month", {i["id"] for i in d2["invoice_payables"]} == {"INV-1046"}
      and {p["supplier"] for p in d2["bills"]} == {"Notion"}
      and d2["payroll_gbp"] is None, str(d2["total_gbp"]))

print("== runway ==")
r = close.runway(BRAIN)
check("runway maths", r["runway_months"] == round(820000 / 95000, 1) == 8.6
      and r["balance_gbp"] == 820000 and r["monthly_burn_gbp"] == 95000)
empty = close.runway({"finance": {}})
check("runway missing data -> error", "error" in empty)

print("== draft_close_nudge ==")
n = close.draft_close_nudge(BRAIN)
check("drafts per owner", {x["to"] for x in n["drafts"]}
      == {"Riyansh", "Pranali", "Darsh"}, str([x["to"] for x in n["drafts"]]))
check("draft_only", n["draft_only"] is True)
riy = next(x for x in n["drafts"] if x["to"] == "Riyansh")
check("nudge cites step", "AR / receivables review" in riy["text"]
      and "2026-10-24" in riy["text"], riy["text"][:80])
check("nudge owner filter",
      len(close.draft_close_nudge(BRAIN, owner="pranali")["drafts"]) == 1)
check("unknown owner -> error",
      "error" in close.draft_close_nudge(BRAIN, owner="Nobody"))
_done = {"finance": {"month_end_close": {"period": "2026-10", "steps": [
    dict(x, status="reconciled") for x in STEPS]}}}
check("all reconciled -> no drafts",
      close.draft_close_nudge(_done)["drafts"] == [])
check("no send fns", not any(hasattr(close, n_) for n_ in
                             ("send", "send_email", "send_slack",
                              "post_message")))

print("== ask router ==")
a = close.ask("what's blocking close", BRAIN)
check("blocking close matched", a["matched"] and "AR / receivables review"
      in a["answer"], a["answer"][:80])
a = close.ask("how do we close the month", BRAIN)
check("close status matched", a["matched"] and "43%" in a["answer"],
      a["answer"][:80])
a = close.ask("what's our runway", BRAIN)
check("runway ask", a["matched"] and "8.6 months" in a["answer"]
      and any(s["brain_key"] == "finance.bank.balance_gbp"
              for s in a["sources"]), a["answer"])
a = close.ask("what's due out this month", BRAIN)
check("due-out ask", a["matched"] and "54,850" in a["answer"],
      a["answer"][:100])
a = close.ask("chase close", BRAIN)
check("chase close -> drafts", a["matched"] and "Riyansh" in a["answer"]
      and "never sent" in a["answer"], a["answer"][:100])
check("non-close -> None",
      close.ask("what's the discount cap", BRAIN) is None)

print("== main routing ==")
out = main._ask_brain("what's blocking close")
check("_ask_brain close", out["matched"] and "close" in out["answer"].lower())
out = main._ask_brain("what's our runway")
check("_ask_brain runway", out["matched"]
      and any(s["brain_key"].startswith("finance.bank")
              for s in out["sources"]))
out = main._ask_brain("who owes us money")
check("_ask_brain owes still chaser", out["matched"]
      and "outstanding" in out["answer"])
out = main._ask_brain("what's the discount cap")
check("_ask_brain falls through", out["matched"]
      and "10%" in out["answer"], out["answer"][:60])

print("== slack commands ==")
check("close status cmd",
      slack_feed._close_command_text("close status") == "close status")
check("chase close cmd",
      slack_feed._close_command_text("Chase Close") == "Chase Close")
check("blocking close cmd",
      slack_feed._close_command_text("what's blocking close?") is not None)
check("not a cmd", slack_feed._close_command_text("close the deal") is None)
check("chase close not invoice chase",
      slack_feed._parse_chase("chase close") is None
      and slack_feed._parse_chase("chase INV-1048") == "INV-1048")
slack_feed._ask = main._ask_brain  # injected by start() under a real server
item = slack_feed._push("close status", "manual")
check("feed close status item", item["kind"] == "question"
      and item["matched"] and "close" in item["answer"].lower(),
      item["answer"][:80])
item = slack_feed._push("chase close", "manual")
check("feed chase close item", item["kind"] == "question"
      and "Riyansh" in item["answer"], item["answer"][:80])

print()
if failures:
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print("ALL PASS")
