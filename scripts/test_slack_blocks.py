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
check("one+ section per violation", len(secs) >= len(res["violations"]),
      f"{len(secs)} sections / {len(res['violations'])} violations")
check("one context block per violation", len(ctxs) == len(res["violations"]))
check("every context cites Brain says/Found",
      all("Brain says:" in e["text"] and "Found:" in e["text"]
          for b in ctxs for e in b["elements"]))

# 4. clean input produces no reply payload (caller skips posting)
clean = main.verify_context(main.VerifyRequest(
    text=main.SCENARIOS["clean_email"]["text"],
    context_type=main.SCENARIOS["clean_email"]["context_type"]))
check("clean_email stays CLEAN (reaction only, no blocks)",
      clean["status"] == "CLEAN" and not clean["violations"])

print()
if failures:
    print("FAILURES:", ", ".join(failures))
    sys.exit(1)
print("ALL PASS")
