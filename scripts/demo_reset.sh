#!/usr/bin/env bash
# One-command demo reset:
#   1. blank learned_rules + learned_exceptions in company_brain.json
#      (surgical edit — every other byte of the file stays identical)
#   2. clear feed_log.jsonl
#   3. reseed the audit log (seed_audit.py --reset)
#   4. run smoke_test.py -> print READY or FAIL
set -uo pipefail

cd "$(dirname "$0")/../backend" || exit 1

uv run python - <<'PY'
import re
from pathlib import Path

p = Path("company_brain.json")
src = p.read_text()

def blank_array(text, key):
    """Replace key's top-level [ ... ] with [] without touching anything else."""
    m = re.search(rf'"{key}"\s*:\s*\[', text)
    if not m:
        raise SystemExit(f"FAIL: '{key}' not found in company_brain.json")
    i = m.end() - 1  # position of the opening '['
    depth, in_str, esc = 0, False, False
    for j in range(i, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[:i] + "[]" + text[j + 1:]
    raise SystemExit(f"FAIL: unbalanced array for '{key}'")

for key in ("learned_rules", "learned_exceptions"):
    src = blank_array(src, key)

# riyansh/chaser: clear every invoice chase_log and undo chaser-marked
# 'paid' statuses (chase_paid_from holds the status to restore). Surgical
# when invoices are single-line objects (the committed style); falls back
# to a normalised rewrite if the file was already reserialised.
import json
lines = src.splitlines(keepends=True)
chaser_state = False
surgical = True
for _n, _l in enumerate(lines):
    if '"kind": "receivable"' not in _l:
        continue
    try:
        obj = json.loads(_l.strip().rstrip(","))
    except Exception:
        surgical = False
        break
    if not isinstance(obj, dict) or "id" not in obj:
        continue
    if "chase_paid_from" in obj or obj.get("chase_log"):
        chaser_state = True
        if "chase_paid_from" in obj:
            obj["status"] = obj.pop("chase_paid_from")
        obj["chase_log"] = []
        trailing = "," if _l.rstrip().endswith(",") else ""
        nl = "\n" if _l.endswith("\n") else ""
        ind = _l[:len(_l) - len(_l.lstrip())]
        lines[_n] = ind + json.dumps(obj, ensure_ascii=False) + trailing + nl
if surgical:
    src = "".join(lines)
else:
    data = json.loads(src)
    for inv in data.get("finance", {}).get("invoices", []):
        if "chase_paid_from" in inv:
            inv["status"] = inv.pop("chase_paid_from")
            chaser_state = True
        if inv.get("chase_log"):
            inv["chase_log"] = []
            chaser_state = True
    if chaser_state:
        src = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
if chaser_state:
    print("brain: invoice chase_log cleared, chaser 'paid' statuses restored")

p.write_text(src)
print("brain: learned_rules + learned_exceptions reset to []")
PY
[ $? -ne 0 ] && exit 1

uv run python - <<'PY'
from pathlib import Path

log = Path("brain_changelog.jsonl")
props = Path("brain_proposals.json")
try:
    import brain_store
    res = brain_store.revert_all()  # restores patched values + empties changelog
    print(f"brain: reverted patches {res.get('reverted') or 'none'}")
except Exception as e:
    print(f"brain: revert skipped ({type(e).__name__}: {e})")
for p in (log, props):
    try:
        p.unlink()
        print(f"{p.name} cleared")
    except FileNotFoundError:
        pass
PY
[ $? -ne 0 ] && exit 1

rm -f feed_log.jsonl
echo "feed_log.jsonl cleared"

uv run python seed_audit.py --reset || exit 1

if uv run python smoke_test.py > /tmp/demo_reset_smoke.log 2>&1; then
    tail -1 /tmp/demo_reset_smoke.log
    echo "READY"
else
    cat /tmp/demo_reset_smoke.log
    echo "FAIL"
    exit 1
fi
