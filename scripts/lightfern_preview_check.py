#!/usr/bin/env python3
"""Lightfern browser-preview check — hits a RUNNING CommitGuard server.

    uv run python scripts/lightfern_preview_check.py [base_url]
    # default http://127.0.0.1:8000  (use 8011 for the check server)

Asserts:
  1. GET /lightfern serves the preview page (200, mentions home.tsx).
  2. After POST /feed/inject, GET /lightfern/files/live/feed.json returns
     entries containing the injected marker — the same file home.tsx reads.
  3. Path traversal is rejected: /lightfern/files/../company_brain.json
     (encoded) and an absolute path both return 400.
  4. POST /lightfern/files/inbox/<ask>.json lands an ask command and the
     bridge answers at live/answers/<id>.json — the full round-trip the
     browser "Ask the brain" box performs.

Prints `LIGHTFERN PREVIEW READY` on success; exits non-zero otherwise.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
MARKER = f"lfp-{int(time.time())}"
ASK_ID = f"ask-{MARKER}"
TIMEOUT_S = 6

_results = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" +
          (f"  {detail}" if detail else ""), flush=True)
    _results.append(bool(ok))


def req(method, path, payload=None, raw=False):
    r = urllib.request.Request(
        BASE_URL + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None)
    if payload is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            body = resp.read()
            return resp.status, body if raw else _json(body)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, body if raw else _json(body)
    except Exception as e:
        return None, {"error": str(e)}


def _json(body):
    try:
        return json.loads(body)
    except Exception:
        return {}


def wait_for(fn, timeout=TIMEOUT_S, interval=0.3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v, time.time() - t0
        time.sleep(interval)
    return None, time.time() - t0


def main():
    code, html = req("GET", "/lightfern", raw=True)
    check("GET /lightfern",
          code == 200 and b"home.tsx" in html,
          f"http={code}")

    code, _ = req("POST", "/feed/inject", {
        "text": f"preview check {MARKER} — Net-30, 5% discount, all standard",
        "user": "preview_check"})
    check("POST /feed/inject", code == 200, f"http={code}")

    def feed_has_marker():
        c, doc = req("GET", "/lightfern/files/live/feed.json")
        if c != 200 or not isinstance(doc, dict):
            return None
        entries = doc.get("entries") or []
        return [e for e in entries if MARKER in (e.get("text") or "")]
    found, dt = wait_for(feed_has_marker)
    check("feed item via /lightfern/files/live/feed.json", bool(found),
          f"visible in {dt:.2f}s")

    for bad in ("..%2F..%2Fcompany_brain.json",
                "..%2F..%2F..%2Fetc%2Fpasswd",
                "%2Fetc%2Fpasswd",
                "brain%2F..%2F..%2F..%2Fsecret"):
        c, _ = req("GET", f"/lightfern/files/{bad}")
        if c != 400:
            check(f"traversal rejected ({bad})", False, f"http={c}")
            break
    else:
        check("traversal rejected (4 payloads)", True, "all http=400")

    code, _ = req("POST", f"/lightfern/files/inbox/{ASK_ID}.json",
                  {"content": json.dumps({
                      "cmd": "ask", "id": ASK_ID,
                      "question": "what is the maximum discount?"})})
    check("write inbox ask command", code == 200, f"http={code}")

    def answered():
        c, doc = req("GET", f"/lightfern/files/live/answers/{ASK_ID}.json")
        return doc if c == 200 and doc.get("ok") else None
    ans, dt = wait_for(answered)
    check("bridge answered ask via files API", bool(ans and ans.get("answer")),
          f"in {dt:.2f}s — {(ans or {}).get('answer', '')[:60]}")

    print("-" * 60)
    if all(_results) and _results:
        print(f"LIGHTFERN PREVIEW READY — {len(_results)} checks passed")
        sys.exit(0)
    print(f"LIGHTFERN PREVIEW NOT READY — {_results.count(False)} failed")
    sys.exit(1)


if __name__ == "__main__":
    main()
