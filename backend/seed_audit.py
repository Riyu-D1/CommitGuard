"""Seed audit_log.jsonl with realistic demo entries so the Inspector isn't empty.

--reset wipes audit_log.jsonl + round_staging_queue.json first (both are
gitignored local state — safe to delete on any machine).
"""
import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent
AUDIT_PATH = BASE / "audit_log.jsonl"
STAGING_PATH = BASE / "round_staging_queue.json"

# (minutes_ago, action_type, payload, result) — oldest first, spread over ~2h.
# result strings match what actions.py writes; payloads that represent a block
# carry "violations" with real brain keys (the Inspector sums them).
SEEDS = [
    (115, "SEND_APPROVED",
     {"text": "Hi John — Net-30 terms, 10% discount, monthly billing confirmed.",
      "context_type": "outgoing_email"},
     "ok"),
    (95, "APPLY_REWRITE_AND_LOG",
     {"text": "Net-60 → Net-30, 15% → 10% discount, quarterly → monthly.",
      "context_type": "outgoing_email",
      "violations": [
          {"category": "FINANCIAL_POLICY", "severity": "HIGH",
           "evidence": {"brain_key": "financial_rules.max_payment_terms",
                        "expected": "Net-30", "found": "Net-60"}},
          {"category": "MARGIN_BREACH", "severity": "HIGH",
           "evidence": {"brain_key": "financial_rules.max_unapproved_discount_percent",
                        "expected": "<= 10%", "found": "15%"}},
      ]},
     "ok"),
    (70, "APPROVE_OVERRIDE",
     {"reason": "client deadline tomorrow — CFO aware via slack",
      "context_type": "slack_message"},
     "ok"),
    (40, "STAGE_INVOICE",
     {"invoice": "CS-1187", "vendor": "CloudScale Ltd", "amount": 9600,
      "context_type": "incoming_invoice",
      "violations": [
          {"category": "CONTRACT_OVERAGE", "severity": "HIGH",
           "evidence": {"brain_key": "signed_contracts[CloudScale Ltd].approved_monthly_retainer_gbp",
                        "expected": 5000, "found": 6200}},
      ]},
     "staged_in_round_queue"),
    (10, "ESCALATE_FRAUD",
     {"invoice": "CS-1187", "vendor": "CloudScale Ltd",
      "context_type": "incoming_invoice",
      "violations": [
          {"category": "PAYMENT_REDIRECTION", "severity": "CRITICAL",
           "evidence": {"brain_key": "signed_contracts[CloudScale Ltd].bank_iban",
                        "expected": "GB29REVOLUT12345689",
                        "found": "GB22BARC99887766554"}},
      ]},
     "escalated_to_cfo"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                        help="wipe audit_log.jsonl + round_staging_queue.json first")
    args = parser.parse_args()

    if args.reset:
        AUDIT_PATH.unlink(missing_ok=True)
        STAGING_PATH.unlink(missing_ok=True)
        print("reset: removed audit_log.jsonl + round_staging_queue.json")

    now = datetime.now(timezone.utc)
    with AUDIT_PATH.open("a") as f:
        for minutes_ago, action_type, payload, result in SEEDS:
            when = now - timedelta(minutes=minutes_ago)
            entry = {"action_type": action_type, "payload": payload,
                     "result": result,
                     "audit_log_id": f"log_{uuid.uuid4().hex[:8]}",
                     "ts": when.isoformat(),
                     "epoch_ms": int(when.timestamp() * 1000)}
            f.write(json.dumps(entry) + "\n")
            print(entry["audit_log_id"], action_type)
    print(f"\nseeded {len(SEEDS)} entries -> backend/audit_log.jsonl")


if __name__ == "__main__":
    main()
