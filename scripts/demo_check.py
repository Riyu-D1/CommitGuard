#!/usr/bin/env python3
"""Live demo gate — hits a RUNNING CommitGuard server at 127.0.0.1:8000.

Checks /health, /feed/stats, /slack/status, injects every slack_demo_*
scenario through POST /feed/inject and verifies each gets its expected
categories (parsed from backend/smoke_test.py so expectations never drift).
If /ask exists it also asks 2 questions. A missing endpoint is SKIP, never a
crash. Exits non-zero if any row FAILs.
"""
import ast
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8000")
if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
    BASE_URL = sys.argv[1]
ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = ROOT / "backend" / "scenarios.json"
SMOKE_PATH = ROOT / "backend" / "smoke_test.py"


def _expected_map():
    """Pull the SLACK_DEMO + FINANCE_DEMO expected-category dicts out of
    smoke_test.py so expectations never drift."""
    tree = ast.parse(SMOKE_PATH.read_text())
    merged = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") in ("SLACK_DEMO", "FINANCE_DEMO")
                for t in node.targets):
            merged.update(ast.literal_eval(node.value))
    return merged


def _req(method, path, payload=None, timeout=5):
    req = urllib.request.Request(BASE_URL + path, method=method)
    data = json.dumps(payload).encode() if payload is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception as e:
        return None, {"error": str(e)}


def main():
    rows = []

    def row(name, status, detail=""):
        rows.append(status)
        print(f"  {name:<30} {status:<5} {detail}")

    print(f"demo_check — {BASE_URL}\n{'-' * 60}")

    code, health = _req("GET", "/health")
    if code == 200 and isinstance(health, dict) and health.get("ok"):
        row("GET /health", "PASS",
            f"engine={health.get('engine')} checks={health.get('checks')}")
    elif code == 200:
        row("GET /health", "FAIL", f"ok flag missing: {health}")
    else:
        row("GET /health", "FAIL", f"http={code} — is the server running?")

    code, stats = _req("GET", "/feed/stats")
    if code == 404:
        row("GET /feed/stats", "SKIP", "endpoint not implemented")
    elif code == 200 and isinstance(stats, dict):
        row("GET /feed/stats", "PASS", json.dumps(stats)[:70])
    else:
        row("GET /feed/stats", "FAIL", f"http={code}")

    code, st = _req("GET", "/slack/status")
    if code == 404:
        row("GET /slack/status", "SKIP", "endpoint not implemented")
    elif code == 200 and isinstance(st, dict):
        row("GET /slack/status", "PASS", json.dumps(st)[:70])
    else:
        row("GET /slack/status", "FAIL", f"http={code}")

    scenarios = json.loads(SCENARIOS_PATH.read_text())
    expected = _expected_map()
    print('-' * 60)
    for key, sc in scenarios.items():
        if key not in expected:
            continue
        code, item = _req("POST", "/feed/inject",
                          {"text": sc["text"], "user": "demo_check"})
        if code in (404, 405):
            row(f"inject {key}", "SKIP", f"http={code}")
            continue
        if code != 200 or not isinstance(item, dict):
            row(f"inject {key}", "FAIL", f"http={code}")
            continue
        cats = {v.get("category") for v in item.get("violations", [])}
        missing = set(expected[key]) - cats
        if missing:
            row(f"inject {key}", "FAIL", f"missing {sorted(missing)}")
        else:
            row(f"inject {key}", "PASS", f"got {sorted(cats) or 'CLEAN'}")

    print('-' * 60)
    for i, q in enumerate(["can I give a 20% discount?",
                           "who approves spend over £5k?",
                           "what's our runway?"], 1):
        code, res = _req("POST", "/ask", {"question": q})
        if code in (404, 405, 422):
            row(f"ask #{i}", "SKIP", f"http={code} (no /ask endpoint yet)")
        elif code == 200 and isinstance(res, dict) and res.get("answer"):
            row(f"ask #{i}", "PASS", str(res["answer"])[:60])
        else:
            row(f"ask #{i}", "FAIL", f"http={code}")

    print('-' * 60)
    fails = rows.count("FAIL")
    print(f"{len(rows)} checks: {rows.count('PASS')} PASS · "
          f"{rows.count('SKIP')} SKIP · {fails} FAIL")
    print("DEMO READY" if fails == 0 else "DEMO NOT READY")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
