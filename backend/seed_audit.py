"""Seed audit_log.jsonl with realistic demo entries so the Inspector isn't empty."""
import actions

SEEDS = [
    ("SEND_APPROVED", {"text": "Hi John, Net-30 terms with 10% discount confirmed...",
                       "context_type": "outgoing_email"}, "sent"),
    ("APPLY_REWRITE_AND_LOG", {"text": "Net-60 -> Net-30, 15% -> 10% discount",
                               "context_type": "outgoing_email",
                               "violations": [{"category": "FINANCIAL_POLICY"},
                                              {"category": "MARGIN_BREACH"}]}, "rewrite_applied"),
    ("APPROVE_OVERRIDE", {"reason": "client deadline tomorrow - CFO aware via slack",
                          "context_type": "slack_message"}, "override_approved"),
    ("STAGE_INVOICE", {"invoice": "CS-1187", "context_type": "incoming_invoice"},
     "staged_in_round_queue"),
    ("ESCALATE_FRAUD", {"invoice": "CS-1187",
                        "violations": [{"category": "PAYMENT_REDIRECTION",
                                        "severity": "CRITICAL"}]}, "escalated_to_cfo"),
]


def main():
    for action_type, payload, result in SEEDS:
        entry = actions.audit({"action_type": action_type, "payload": payload,
                               "result": result})
        print(entry["audit_log_id"], action_type)
    print(f"\nseeded {len(SEEDS)} entries -> backend/audit_log.jsonl")


if __name__ == "__main__":
    main()
