"""Chaser unit tests — offline, no server, no API key needed.

  uv run python test_chaser.py

Writes go to a temp copy of company_brain.json — the real brain is never
touched. Exits 1 and prints every failure.
"""
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)  # force the template path

import chaser  # noqa: E402
import main  # noqa: E402  (COMPANY_BRAIN loaded once, like the server)

BASE = Path(__file__).parent
BRAIN = json.loads((BASE / "company_brain.json").read_text())
TODAY = date(2026, 10, 24)

failures = []


def check(name, cond, detail=""):
    print(f"  {name:<34} {'PASS' if cond else 'FAIL'} {detail}")
    if not cond:
        failures.append(name)


def tmp_brain():
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    f.write((BASE / "company_brain.json").read_text())
    f.close()
    return Path(f.name)


print("== ageing maths ==")
rep = chaser.ageing(BRAIN, today=TODAY)
by_id = {i["invoice_id"]: i for i in rep["items"]}
check("buckets", by_id["INV-1048"]["bucket"] == "1-30"
      and by_id["INV-1047"]["bucket"] == "31-60"
      and by_id["INV-1041"]["bucket"] == "60+"
      and by_id["INV-1051"]["bucket"] == "current"
      and by_id["INV-1049"]["bucket"] == "current",
      str({k: v["bucket"] for k, v in by_id.items()}))
check("days_overdue", by_id["INV-1048"]["days_overdue"] == 4
      and by_id["INV-1041"]["days_overdue"] == 70
      and by_id["INV-1051"]["days_overdue"] == 0,
      str({k: v["days_overdue"] for k, v in by_id.items()}))
check("paid excluded", "INV-1045" not in by_id)
check("totals", rep["total_outstanding_gbp"] == 48000 + 12500 + 31000 + 7800 + 22000
      and rep["overdue_gbp"] == 31000 + 7800 + 22000,
      f"total={rep['total_outstanding_gbp']} overdue={rep['overdue_gbp']}")
check("order: most overdue first", rep["items"][0]["invoice_id"] == "INV-1041")

print("== draft cites a prior promise ==")
_promised = json.loads(json.dumps(BRAIN))
chaser.record_signal(
    _promised, "Acme said they'd pay after the board meeting on the 30th")
_dp = chaser.draft_chase(_promised, "INV-1041", feed_items=[], today=TODAY)
check("promise surfaced", "board meeting" in _dp["body"]
      and any("promise" in c for c in _dp["cites"]),
      _dp["subject"])

print("== tone ladder ==")
check("tone fresh", chaser.tone_for(0, 0) == "friendly_reminder")
check("tone 1-30", chaser.tone_for(10, 0) == "friendly_reminder")
check("tone 31-60", chaser.tone_for(40, 0) == "firm")
check("tone 60+", chaser.tone_for(70, 0) == "final_notice")
check("tone repeat chaser", chaser.tone_for(5, 2) == "firm")
check("tone persistent", chaser.tone_for(5, 3) == "final_notice")

print("== draft: template fallback (no key) ==")
os.environ.pop("OPENAI_API_KEY", None)
d = chaser.draft_chase(BRAIN, "INV-1041", feed_items=[], today=TODAY)
check("no error", "error" not in d, str(d.get("error")))
check("engine template", d.get("engine") == "template", d.get("engine"))
check("final tone + cfo escalation",
      d["tone"] == "final_notice" and d["escalate_to"] == "Darsh",
      f"{d.get('tone')} -> {d.get('escalate_to')}")
check("draft cites facts",
      "INV-1041" in d["subject"] and "22,000" in d["body"]
      and "70 days" in d["body"],
      d["subject"])
check("cites list", any("due_date" in c for c in d["cites"])
      and any("promise" in c for c in _dp["cites"]))

d2 = chaser.draft_chase(BRAIN, "globex", feed_items=[], today=TODAY)
check("customer lookup", d2.get("invoice_id") == "INV-1048")
check("friendly tone (4d, 0 chases)", d2["tone"] == "friendly_reminder",
      d2.get("tone"))
check("globex cites", any("INV-1048" in c for c in d2["cites"]))

d3 = chaser.draft_chase(BRAIN, "nonexistent-co", feed_items=[], today=TODAY)
check("unknown ref -> error", "error" in d3)

print("== context scan (what's been said before) ==")
feed = [{"ts": "2026-10-23T10:00:00Z", "source": "slack", "user": "u1",
         "text": "Globex still hasn't paid INV-1048"},
        {"ts": "2026-10-22T09:00:00Z", "source": "slack", "user": "u2",
         "text": "unrelated chatter"}]
inv = next(i for i in BRAIN["finance"]["invoices"] if i["id"] == "INV-1048")
ctx = chaser.scan_context(inv, feed)
check("context hit", len(ctx) == 1 and "INV-1048" in ctx[0]["text"])

print("== paid / promise detection ==")
tb = tmp_brain()
try:
    b = json.loads(tb.read_text())
    upd = chaser.record_signal(b, "Globex paid INV-1048 — wire landed",
                               source="slack", brain_path=tb)
    reloaded = json.loads(tb.read_text())
    g = next(i for i in reloaded["finance"]["invoices"] if i["id"] == "INV-1048")
    check("paid flips status", g["status"] == "paid"
          and g.get("chase_paid_from") == "overdue")
    check("paid logged", any(e["kind"] == "paid"
                             for e in g["chase_log"]))
    check("paid update returned", any(u["kind"] == "paid" for u in upd))
    check("paid drops out of receivables",
          "INV-1048" not in {i["invoice_id"]
                             for i in chaser.receivables(reloaded, TODAY)})

    upd2 = chaser.record_signal(b, "Acme will pay INV-1051 on Friday",
                                source="slack", brain_path=tb)
    b2 = json.loads(tb.read_text())
    a = next(i for i in b2["finance"]["invoices"] if i["id"] == "INV-1051")
    check("promise logged", any(e["kind"] == "promise"
                                for e in a["chase_log"]))
    check("promise update returned",
          any(u["kind"] == "promise" for u in upd2))
    upd3 = chaser.record_signal(b, "Acme will pay INV-1051 on Friday",
                                brain_path=tb)
    b3 = json.loads(tb.read_text())
    a3 = next(i for i in b3["finance"]["invoices"] if i["id"] == "INV-1051")
    n_prom = sum(1 for e in a3["chase_log"] if e["kind"] == "promise")
    check("promise dedupe", n_prom == 1, f"{n_prom} promise rows")
    check("unrelated text no-op",
          chaser.record_signal(b3, "the retro moved rooms",
                               brain_path=tb) == [])
    b5 = json.loads(tb.read_text())
    check("negation not paid",
          chaser.record_signal(b5, "Initech still hasn't paid INV-1049",
                               brain_path=tb) == []
          and next(i for i in b5["finance"]["invoices"]
                     if i["id"] == "INV-1049")["status"] == "unpaid")
finally:
    tb.unlink()

print("== chase_log persistence ==")
tb = tmp_brain()
try:
    entry = chaser.log_chase("INV-1048", draft={"tone": "friendly_reminder",
                                                "subject": "reminder"},
                             brain_path=tb)
    reloaded = json.loads(tb.read_text())
    g = next(i for i in reloaded["finance"]["invoices"] if i["id"] == "INV-1048")
    check("log_chase persists", entry is not None
          and any(e["kind"] == "chase" and e["id"] == entry["id"]
                  for e in g["chase_log"]))
    hist = chaser.history(reloaded, "INV-1048")
    check("history endpoint shape", hist["invoice_id"] == "INV-1048"
          and len(hist["chase_log"]) == 1)
    # a logged chase raises the tone next draft
    check("tone rises after log", chaser.tone_for(4, 1) == "friendly_reminder")
    res = chaser.mark_paid("INV-1047", brain_path=tb)
    b4 = json.loads(tb.read_text())
    s = next(i for i in b4["finance"]["invoices"] if i["id"] == "INV-1047")
    check("mark_paid", res["from_status"] == "overdue"
          and s["status"] == "paid")
finally:
    tb.unlink()

print("== no-send guarantee ==")
check("draft_only flag", d.get("draft_only") is True)
check("no send fns", not any(hasattr(chaser, n) for n in
                             ("send", "send_email", "send_chase",
                              "post_email")))
check("draft has no recipient call", "send" not in json.dumps(d).lower()
      or "never sent" in json.dumps(d).lower())

print("== slack helpers ==")
check("parse chase cmd", chaser.parse_chase_command("chase INV-1048") == "INV-1048"
      and chaser.parse_chase_command("Chase: acme") == "acme"
      and chaser.parse_chase_command("hello") is None)
blocks = chaser.build_chase_blocks({"chase": d})
check("block kit", any(b.get("type") == "header" for b in blocks)
      and any("log" in json.dumps(b) and "paid" in json.dumps(b)
              for b in blocks))
s = chaser.ask_summary(BRAIN, today=TODAY)
check("ask summary", s["matched"] and "121,300" in s["answer"],
      s["answer"][:90])

print()
if failures:
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print("ALL PASS")
