"""Treasury queue unit tests — offline, no server, no API key needed.

  uv run python test_treasury.py

Writes go to a temp treasury_queue.json (TREASURY_QUEUE_PATH) — the real
queue is never touched. Exits 1 and prints every failure.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)  # force the deterministic path
_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
_tmp.write("[]")
_tmp.close()
os.environ["TREASURY_QUEUE_PATH"] = _tmp.name

import treasury  # noqa: E402

BASE = Path(__file__).parent
BRAIN = json.loads((BASE / "company_brain.json").read_text())

failures = []


def check(name, cond, detail=""):
    print(f"  {name:<34} {'PASS' if cond else 'FAIL'} {detail}")
    if not cond:
        failures.append(name)


def item(i, text, actions=None, violations=None, status="CLEAN"):
    return {"id": i, "kind": "check", "context_type": "incoming_invoice",
            "text": text, "status": status, "risk_level": "LOW",
            "violations": violations or [], "actions": actions or [],
            "source": "simulated", "user": "test"}


CLEAN_INV = ("INVOICE INV-1043\nCloudScale Ltd\nMonthly retainer: £6,200\n"
             "Please pay to IBAN GB29REVOLUT12345689\nPayment terms: Net-30")
FRAUD_INV = ("INVOICE CS-1202\nCloudScale Ltd — £5,000 due\n"
             "Updated account: IBAN GB22BARC99887766554")
FRAUD_VIOL = [{"category": "PAYMENT_REDIRECTION", "severity": "CRITICAL",
               "issue": "IBAN does not match the signed contract",
               "evidence": {
                   "brain_key": "signed_contracts[CloudScale Ltd].bank_iban",
                   "expected": "GB29REVOLUT12345689",
                   "found": "GB22BARC99887766554"}}]

print("== ingest: ready vs held ==")
e = treasury.ingest_feed_item(item(1, CLEAN_INV), BRAIN)
check("clean invoice -> ready", e["state"] == "ready")
check("payee from contract", e["payee"] == "CloudScale Ltd", e["payee"])
check("invoice_no", e["invoice_no"] == "INV-1043")
check("amount", e["amount_gbp"] == 6200, str(e["amount_gbp"]))
check("due_date from ledger", e["due_date"] == "2026-10-28", str(e["due_date"]))
check("approver = CFO tier", e["tier"] == "cfo" and e["approver"] == "Darsh",
      f"{e['tier']}/{e['approver']}")
check("no-money label", "no money moves" in e["status_label"])

h = treasury.ingest_feed_item(
    item(2, FRAUD_INV, actions=[{"type": "HOLD_PAYMENT"},
                                {"type": "VERIFY_VENDOR"}],
         violations=FRAUD_VIOL, status="VIOLATION_DETECTED"), BRAIN)
check("hold actions -> held", h["state"] == "held")
check("reason cites brain_key",
      h["reason"]["brain_key"] == "signed_contracts[CloudScale Ltd].bank_iban",
      str(h["reason"]))
check("reason category", h["reason"]["category"] == "PAYMENT_REDIRECTION")

print("== non-invoice items are ignored ==")
check("slack_message ignored",
      treasury.ingest_feed_item(
          {"id": 3, "kind": "check", "context_type": "slack_message",
           "text": "hi", "actions": []}, BRAIN) is None)
check("question ignored",
      treasury.ingest_feed_item(
          {"id": 4, "kind": "question",
           "context_type": "incoming_invoice", "text": "?", "actions": []},
          BRAIN) is None)

print("== queue view ==")
q = treasury.list_queue()
check("counts", q["ready"] == 1 and q["held"] == 1, str(q))
check("total_ready", q["total_ready_gbp"] == 6200)
check("sample_data flag", q["sample_data"] is True)

print("== approve / release ==")
entry, err = treasury.approve(h["id"], "Darsh")
check("approve held -> refused", entry is None and "held" in (err or ""), err)
entry, err = treasury.release_hold(h["id"], "Darsh")
check("release_hold -> ready", err is None and entry["state"] == "ready"
      and entry["released_by"] == "Darsh", err)
check("reason kept after release",
      entry["reason"]["category"] == "PAYMENT_REDIRECTION")
entry, err = treasury.approve(h["id"], "Darsh")
check("approve ready -> approved", err is None
      and entry["state"] == "approved" and entry["approved_by"] == "Darsh", err)
entry, err = treasury.approve("TQ-999", "x")
check("approve missing -> 404 err", entry is None and "not found" in err)

print("== dedupe on invoice_no ==")
e2 = treasury.ingest_feed_item(item(5, CLEAN_INV), BRAIN)
check("re-ingest same invoice keeps one row",
      sum(1 for x in treasury.list_queue()["items"]
          if x.get("invoice_no") == "INV-1043") == 1 and e2["id"] == e["id"])

print("== persistence ==")
treasury._mem = None
check("reloads from disk",
      len(treasury.list_queue()["items"]) == 2
      and treasury.list_queue()["approved"] == 1)

print("== ask summary ==")
treasury.ingest_feed_item(
    item(6, "INVOICE PPD-441\nPinnacle Print & Design — £1,800\n"
            "Remit to sort code 40-11-22, account number 99887766",
         actions=[{"type": "HOLD_PAYMENT"}],
         violations=[{"category": "BANK_DETAILS_MISMATCH",
                      "severity": "CRITICAL",
                      "issue": "sort code does not match contract",
                      "evidence": {"brain_key":
                                   "signed_contracts[Pinnacle Print & Design].bank_sort_code",
                                   "expected": "30-00-11",
                                   "found": "40-11-22"}}],
         status="VIOLATION_DETECTED"), BRAIN)
s = treasury.ask_summary(BRAIN)
check("matched", s["matched"] is True)
check("mentions held", "HELD" in s["answer"], s["answer"][:60])
check("cites treasury source", "treasury.queue" in s["sources"])
check("no-money disclaimer", "no money moves" in s["answer"])

print("=" * 50)
if failures:
    print(f"{len(failures)} FAIL: {failures}")
    sys.exit(1)
print("ALL PASS")
