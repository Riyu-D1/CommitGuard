"""Onboarding helper — 'Day 1 rules' doc + ask-the-brain answers.

  uv run python onboarding.py                          -> writes demo/ONBOARDING.md
  uv run python onboarding.py --finance                -> answers the finance questions
  uv run python onboarding.py "can I give a 20% discount?" -> answer + sources
"""
import json
import sys
from pathlib import Path

import rules

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"
OUT_PATH = BASE.parent / "demo" / "ONBOARDING.md"

# Canonical finance questions every new ops/finance hire asks — answered from
# the same explain_policy the /ask endpoint uses, each citing its brain_key.
FINANCE_QUESTIONS = [
    "who approves spend over £5k?",
    "what's due out this month?",
    "what's our runway?",
    "which invoices are overdue?",
]


def load_brain() -> dict:
    return json.loads(BRAIN_PATH.read_text())


def ask(brain: dict, question: str) -> dict:
    out = rules.explain_policy(question, brain)
    print(f"Q: {question}")
    print(f"A: {out['answer']}")
    print(f"matched={out['matched']}")
    for s in out["sources"]:
        print(f"  source: {s['brain_key']} = {s['value']}")
    return out


def write_doc(brain: dict) -> None:
    lines = [
        "# Day 1 rules — what CommitGuard enforces",
        "",
        "_Generated from `company_brain.json` — every rule cites its source._",
        "",
    ]
    for card in rules.policy_cards(brain):
        lines.append(f"## {card['title']}")
        lines.append(card["rule"])
        lines.append(f"- Source: `{card['brain_key']}`")
        lines.append(f"- Trips on: {card['example_violation']}")
        lines.append("")
    OUT_PATH.write_text("\n".join(lines))
    print(f"wrote {OUT_PATH} ({len(rules.policy_cards(brain))} policy cards)")


def main() -> None:
    brain = load_brain()
    if len(sys.argv) > 1:
        if sys.argv[1] == "--finance":
            for q in FINANCE_QUESTIONS:
                ask(brain, q)
                print()
            return
        ask(brain, " ".join(sys.argv[1:]))
        return
    write_doc(brain)


if __name__ == "__main__":
    main()
