"""Unit-style check for the Slack Block Kit payload — no server, no Slack.

Builds the blocks for the vendor_invoice verify result and asserts the
payload is valid JSON with fewer than 50 blocks (Slack's hard limit).

Run from the repo root:
    python3 scripts/test_slack_blocks.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import main         # noqa: E402
import slack_feed   # noqa: E402

VALID_BLOCK_TYPES = {"header", "section", "context", "divider", "actions",
                     "image", "input", "rich_text", "video", "file"}

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          f"{(' — ' + str(detail)) if detail != '' else ''}")
    if not ok:
        failures.append(name)


sc = main.SCENARIOS["vendor_invoice"]
res = main.verify_context(main.VerifyRequest(text=sc["text"],
                                             context_type=sc["context_type"]))
print(f"vendor_invoice → {res['status']} "
      f"({len(res['violations'])} violations, risk={res['risk_level']})")

payload = {
    "channel": "C0123456789",
    "thread_ts": "1761300000.000100",
    "text": "CommitGuard alert",
    "blocks": slack_feed.build_blocks(res),
}

# 1. the whole payload must round-trip through JSON
encoded = json.dumps(payload)
decoded = json.loads(encoded)
check("payload is valid JSON", isinstance(decoded["blocks"], list))

blocks = decoded["blocks"]
print(f"blocks: {len(blocks)}")
check("fewer than 50 blocks", len(blocks) < 50, f"{len(blocks)} blocks")
check("all block types are valid Slack types",
      all(b.get("type") in VALID_BLOCK_TYPES for b in blocks),
      sorted({b.get("type") for b in blocks}))

# 2. header says what was caught (🛑 if any CRITICAL violation, else ⚠️)
hdr = blocks[0]
check("first block is a header", hdr.get("type") == "header")
icon = "🛑" if any(v["severity"] == "CRITICAL"
                   for v in res["violations"]) else "⚠️"
check("header text names the count",
      hdr["text"]["text"] == f"{icon} CommitGuard caught "
                             f"{len(res['violations'])} issue"
                             f"{'s' if len(res['violations']) != 1 else ''}",
      hdr["text"]["text"])

# 3. every violation got a section + a context evidence line
secs = [b for b in blocks if b["type"] == "section"]
ctxs = [b for b in blocks if b["type"] == "context"]
ev_ctxs = [b for b in ctxs
           if all("Brain says:" in e["text"] for e in b["elements"])]
check("one+ section per violation", len(secs) >= len(res["violations"]),
      f"{len(secs)} sections / {len(res['violations'])} violations")
check("one evidence context block per violation",
      len(ev_ctxs) == len(res["violations"]))
check("every context cites Brain says/Found",
      all("Brain says:" in e["text"] and "Found:" in e["text"]
          for b in ev_ctxs for e in b["elements"]))

# 3b. the verify result carries the actions plan, and the reply ends with a
# '🤖 Actions: <label> · <label>' context line (labels carry brain targets)
check("verify result carries actions plan",
      isinstance(res.get("actions"), list)
      and {a["type"] for a in res["actions"]} >= {"HOLD_PAYMENT", "ESCALATE"},
      [a.get("type") for a in res.get("actions") or []])
act_lines = [e["text"] for b in ctxs for e in b["elements"]
             if e["text"].startswith("🤖 Actions:")]
check("actions context line present", len(act_lines) == 1, act_lines)
joined = " · ".join(a.get("label") or a.get("type", "")
                    for a in res.get("actions") or [])
check("actions line joins the plan labels",
      bool(act_lines) and act_lines[0] == f"🤖 Actions: {joined}",
      act_lines)
check("actions line names hold + escalate targets",
      bool(act_lines) and "Hold payment" in act_lines[0]
      and "Escalate to" in act_lines[0], act_lines)

# 4. clean input produces no reply payload (caller skips posting)
clean = main.verify_context(main.VerifyRequest(
    text=main.SCENARIOS["clean_email"]["text"],
    context_type=main.SCENARIOS["clean_email"]["context_type"]))
check("clean_email stays CLEAN (reaction only, no blocks)",
      clean["status"] == "CLEAN" and not clean["violations"])

# 5. question items get an answer payload: header + answer section +
# one 'Source: <brain_key> = <value>' context line per source
qres = main.ask(main.AskRequest(question="can I give a 20% discount?"))
print(f"/ask discount → matched={qres['matched']} "
      f"({len(qres['sources'])} sources)")
qitem = {"question": "can I give a 20% discount?", **qres}

qpayload = {
    "channel": "C0123456789",
    "thread_ts": "1761300000.000200",
    "text": qres["answer"],
    "blocks": slack_feed.build_question_blocks(qitem),
}
qblocks = json.loads(json.dumps(qpayload))["blocks"]
check("question payload is valid JSON", isinstance(qblocks, list))
check("question: fewer than 50 blocks", len(qblocks) < 50,
      f"{len(qblocks)} blocks")
check("question: all block types are valid Slack types",
      all(b.get("type") in VALID_BLOCK_TYPES for b in qblocks),
      sorted({b.get("type") for b in qblocks}))
check("question: first block is a header", qblocks[0].get("type") == "header")
qsecs = [b for b in qblocks if b["type"] == "section"]
check("question: answer is a section block",
      len(qsecs) == 1 and qsecs[0]["text"]["text"] == qres["answer"])
qctx = [e["text"] for b in qblocks if b["type"] == "context"
        for e in b["elements"]]
check("question: one Source: context line per source",
      len([t for t in qctx if t.startswith("Source: `")])
      == len(qres["sources"]), qctx)
check("question: every cited brain_key appears",
      all(any(s["brain_key"] in t for t in qctx) for s in qres["sources"]),
      [s["brain_key"] for s in qres["sources"]])

# 6. an unmatched question says it's not in the brain yet
ures = main.ask(main.AskRequest(question="what's our office wifi?"))
check("/ask unknown → matched=false", ures["matched"] is False)
ublocks = slack_feed.build_question_blocks(
    {"question": "what's our office wifi?", **ures})
utext = " ".join(e.get("text", "") for b in ublocks
                 for e in ([b.get("text", {})] + b.get("elements", [])))
check("unmatched question says it's not in the brain",
      "not in the company brain" in utext.lower(), utext[:120])

# 7. rule-CLEAN but advisory-carrying items get a soft '💡 Worth a check'
# thread reply — never framed as a rule violation
adv_item = {
    "violations": [],
    "advisories": [{"category": "LLM_NOTE", "severity": "LOW",
                    "issue": "Wording sounds over-committed.",
                    "correction": "Soften the promise.",
                    "suggested_rewrite": "We expect to ship it soon.",
                    "source": "llm"}],
    "actions": [],
}
ablocks = json.loads(json.dumps(slack_feed.build_advisory_blocks(adv_item)))
check("advisory payload is valid JSON", isinstance(ablocks, list))
check("advisory: all block types are valid Slack types",
      all(b.get("type") in VALID_BLOCK_TYPES for b in ablocks),
      sorted({b.get("type") for b in ablocks}))
check("advisory: header says Worth a check",
      ablocks[0].get("type") == "header"
      and ablocks[0]["text"]["text"] == "💡 Worth a check",
      ablocks[0])
atext = json.dumps(ablocks)
check("advisory: includes the issue and suggested rewrite",
      "over-committed" in atext and "We expect to ship it soon" in atext)
check("advisory: never claims a violation was caught",
      "caught" not in ablocks[0]["text"]["text"].lower())

# 8. thread commands: 'missed: <phrase>' teaches a rule; 'fine' marks the
# flagged item a false positive (learned exception)
check("parse 'missed: rebate'",
      slack_feed._parse_thread_command("missed: rebate")
      == ("missed", "rebate"))
check("parse 'Missed:  Net-90 '",
      slack_feed._parse_thread_command("Missed:  Net-90 ")
      == ("missed", "Net-90"))
check("parse 'fine'",
      slack_feed._parse_thread_command("fine") == ("false_positive", None))
check("parse 'Fine.'",
      slack_feed._parse_thread_command("Fine.") == ("false_positive", None))
check("plain chat is not a command",
      slack_feed._parse_thread_command("looks fine to me") is None)
check("'missed:' without a phrase is not a command",
      slack_feed._parse_thread_command("missed:") is None)
check("empty text is not a command",
      slack_feed._parse_thread_command("") is None)

print()
if failures:
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print("ALL PASS")
