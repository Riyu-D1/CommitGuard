#!/usr/bin/env python3
"""Lightfern live check — prove the file bridge end-to-end against a REAL
CommitGuard server started from this checkout.

    uv run python scripts/lightfern_live_check.py          # or: python3 ...

What it does:
  1. Copies lightfern/CommitGuard Brain/ into a fresh temp dir (never the
     repo copy), starts `uvicorn main:app` on 127.0.0.1:8008 with
     SLACK_BOT_TOKEN=disabled SLACK_REPLY=0 SLACK_CHANNEL_ID= and
     LIGHTFERN_APP_DIR=<the temp copy>.
  2. Asserts over HTTP + files (see STEPS below).
  3. Kills the server, restarts it against the same app copy, and asserts
     feed history + learned rules survive the restart.
  4. Restores backend/company_brain.json (learn commands write learned
     rules into it) and kills the server.

Prints `PASS name  detail` / `FAIL name  detail` per step and
`LIGHTFERN READY` when every step passed; exits non-zero otherwise.
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
APP_SRC = ROOT / "lightfern" / "CommitGuard Brain"
BRAIN_DISK = BACKEND / "company_brain.json"
STATE_FILES = [BACKEND / "audit_log.jsonl", BACKEND / "feed_log.jsonl"]

PORT = 8008
BASE_URL = f"http://127.0.0.1:{PORT}"
LOG_PATH = Path("/tmp/lightfern-live-check-server.log")

STARTUP_S = 20
FEED_S = 2.0
HEARTBEAT_S = 6.5       # heartbeat must refresh at least every 5s, even idle
INBOX_S = 3.0
EXPORT_S = 5.0
ANSWER_S = 5.0
IMPORT_S = 6.0
RESTART_S = 20

MARKER = f"lc-{int(time.time())}"
LEARN_PHRASE = f"wire-to-{MARKER}"            # 3-120 chars, unique per run
LEARN_CAT = "LIVECHECK_RULE"
FINE_PHRASE = f"approved-{MARKER}"
ASK_ID = f"ask-{MARKER}"
DISCOUNT_KEY = ("financial_rules", "max_unapproved_discount_percent")
DISCOUNT_EDITED = 37

_results = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    line = f"{tag}  {name}"
    if detail:
        line += f"  {detail}"
    print(line, flush=True)
    _results.append((name, bool(ok)))
    return bool(ok)


def req(method, path, payload=None, timeout=5):
    r = urllib.request.Request(
        BASE_URL + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None)
    if payload is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception:
        return None, {}


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def wait_for(fn, timeout, interval=0.25):
    """Poll fn() until truthy; returns (value, elapsed)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            v = fn()
        except Exception:
            v = None
        if v:
            return v, time.time() - t0
        time.sleep(interval)
    return None, time.time() - t0


def feed_entries(app):
    doc = read_json(app / "live" / "feed.json", {})
    return doc.get("entries") or []


def feed_has(app, needle):
    return any(needle in (e.get("text") or "") for e in feed_entries(app))


def status_doc(app):
    return read_json(app / "live" / "status.json", {}) or {}


def write_inbox(app, name, cmd):
    (app / "inbox" / name).write_text(json.dumps(cmd))


def inbox_done(app, name):
    return (app / "inbox" / "done" / name).exists()


def free_port(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_server(app_dir):
    env = {k: v for k, v in os.environ.items()
           if k not in ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID", "SLACK_REPLY",
                        "LIGHTFERN_APP_DIR")}
    env.update({
        "SLACK_BOT_TOKEN": "disabled",
        "SLACK_REPLY": "0",
        "SLACK_CHANNEL_ID": "",
        "LIGHTFERN_APP_DIR": str(app_dir),
    })
    log = open(LOG_PATH, "ab")
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
    ok, _ = wait_for(
        lambda: proc.poll() is None and req("GET", "/health")[0] == 200,
        STARTUP_S)
    return proc, log, bool(ok)


def stop_server(proc, log):
    if proc.poll() is None:
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
    log.close()


def parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def main():
    if not APP_SRC.is_dir():
        print(f"FAIL  setup  app folder missing: {APP_SRC}")
        sys.exit(1)
    if not free_port(PORT):
        print(f"FAIL  setup  127.0.0.1:{PORT} already in use — free it first")
        sys.exit(1)

    tmp = Path(tempfile.mkdtemp(prefix="lf-live-"))
    app = tmp / "CommitGuard Brain"
    shutil.copytree(APP_SRC, app)
    # scrub runtime leftovers from the copy so it is truly fresh
    for p in (app / "inbox").glob("*.json"):
        if p.name != ".gitkeep":
            p.unlink()
    for p in (app / "live" / "answers").glob("*.json"):
        p.unlink()

    brain_backup = BRAIN_DISK.read_bytes()
    state_backups = {p: p.read_bytes() if p.exists() else None
                     for p in STATE_FILES}

    proc = log = None
    try:
        proc, log, up = start_server(app)
        if not check("server up", up,
                     f"uvicorn on 127.0.0.1:{PORT}, log at {LOG_PATH}"):
            print(LOG_PATH.read_text()[-2000:] if LOG_PATH.exists() else "")
            return

        # -- 1. POST a check -> it lands in live/feed.json within 2s --------
        text = (f"quick note {MARKER} — Net-30 terms and a 5% discount, "
                "all standard.")
        code, res = req("POST", "/verify-context",
                        {"text": text, "context_type": "outgoing_email"})
        found, dt = wait_for(lambda: feed_has(app, MARKER), FEED_S)
        check("check -> live/feed.json",
              code == 200 and res.get("status") and bool(found),
              f"POST /verify-context {code}, feed entry in {dt:.2f}s")

        # -- 2. heartbeat refreshes while idle ------------------------------
        hb0 = status_doc(app).get("heartbeat_ts") or status_doc(app).get("ts")
        t0 = time.time()
        hb1, dt = wait_for(
            lambda: (status_doc(app).get("heartbeat_ts")
                     or status_doc(app).get("ts")) != hb0
                    and (status_doc(app).get("heartbeat_ts")
                         or status_doc(app).get("ts")),
            HEARTBEAT_S)
        fresh = hb1 and (time.time() - parse_ts(hb1)) < 5.0
        check("status.json heartbeat while idle",
              bool(hb1) and dt <= 5.5 and fresh,
              f"heartbeat advanced in {dt:.2f}s (limit 5s)")

        # -- 3. inbox learn -> done + re-exported brain + flagged recheck ---
        fname = f"{int(time.time() * 1000)}-learn-livecheck.json"
        write_inbox(app, fname, {
            "cmd": "learn", "phrase": LEARN_PHRASE, "category": LEARN_CAT,
            "severity": "HIGH",
            "issue": "live check rule — should have been flagged",
            "correction": "remove or escalate"})
        moved, dt = wait_for(lambda: inbox_done(app, fname), INBOX_S)
        check("learn cmd processed to inbox/done", bool(moved),
              f"in {dt:.2f}s (limit 3s)")

        def brain_has_rule():
            b = read_json(app / "brain" / "company_brain.json", {})
            return any(LEARN_PHRASE in (r.get("phrase") or "")
                       for r in (b.get("learned_rules") or []))
        in_file, _ = wait_for(brain_has_rule, EXPORT_S)
        code, learned = req("GET", "/brain/learned")
        in_api = any(LEARN_PHRASE in (r.get("phrase") or "")
                     for r in (learned.get("rules") or []))
        check("learned rule in app brain + /brain/learned",
              bool(in_file) and code == 200 and in_api)

        code, res = req("POST", "/verify-context", {
            "text": f"please action the {LEARN_PHRASE} account today",
            "context_type": "slack_message"})
        cats = [v.get("category") for v in (res.get("violations") or [])]
        check("learned rule flags a new check",
              code == 200 and res.get("status") == "VIOLATION_DETECTED"
              and LEARN_CAT in cats,
              f"violations={cats}")

        # -- 4. override 'fine' -> learned exception -------------------------
        fname = f"{int(time.time() * 1000)}-fine-livecheck.json"
        write_inbox(app, fname, {
            "cmd": "override", "decision": "false_positive",
            "phrase": FINE_PHRASE, "category": "PRICE_FLOOR",
            "note": "live check exception"})
        moved, dt = wait_for(lambda: inbox_done(app, fname), INBOX_S)
        code, learned = req("GET", "/brain/learned")
        has_exc = any(FINE_PHRASE in (x.get("phrase") or "")
                      and x.get("category") == "PRICE_FLOOR"
                      for x in (learned.get("exceptions") or []))
        check("override fine -> learned exception",
              bool(moved) and code == 200 and has_exc,
              f"inbox/done in {dt:.2f}s")

        # -- 5. ask cmd -> live/answers/<id>.json ----------------------------
        write_inbox(app, f"{ASK_ID}.json", {
            "cmd": "ask", "id": ASK_ID,
            "question": "who approves spend over 5000 pounds?"})
        ans, dt = wait_for(
            lambda: read_json(app / "live" / "answers" / f"{ASK_ID}.json"),
            ANSWER_S)
        check("ask -> live/answers/<id>.json",
              bool(ans and ans.get("ok") and ans.get("answer")),
              f"in {dt:.2f}s — {(ans or {}).get('answer', '')[:60]}")

        # -- 6. edit brain inside the app -> backend reloads -----------------
        bfile = app / "brain" / "company_brain.json"
        brain = read_json(bfile, {})
        section = brain.get(DISCOUNT_KEY[0]) or {}
        orig = section.get(DISCOUNT_KEY[1])
        section[DISCOUNT_KEY[1]] = DISCOUNT_EDITED
        bfile.write_text(json.dumps(brain, indent=2) + "\n")

        def edited_live():
            c, b = req("GET", "/brain")
            return c == 200 and \
                (b.get(DISCOUNT_KEY[0]) or {}).get(DISCOUNT_KEY[1]) \
                == DISCOUNT_EDITED
        ok, dt = wait_for(edited_live, IMPORT_S)
        check("edited brain re-imported", bool(ok),
              f"{DISCOUNT_KEY[1]} {orig} -> {DISCOUNT_EDITED} in {dt:.2f}s")

        # -- 7. corrupt brain -> old brain kept, error in status.json --------
        bfile.write_text("{ this is not json")
        def import_failed():
            errs = status_doc(app).get("errors") or []
            return any("import" in e or "brain" in e for e in errs)
        flagged, dt = wait_for(import_failed, IMPORT_S)
        code, b = req("GET", "/brain")
        kept = (b.get(DISCOUNT_KEY[0]) or {}).get(DISCOUNT_KEY[1]) \
            == DISCOUNT_EDITED
        check("corrupt brain rejected, old brain kept",
              bool(flagged) and code == 200 and kept,
              f"error logged in {dt:.2f}s")

        # restore a valid brain file so the restart proof starts clean —
        # the bytes are identical to the bridge's last export, so the mtime
        # watcher treats them as its own write and skips re-import.
        bfile.write_text(json.dumps(brain, indent=2) + "\n")

        # -- 8. kill + restart -> feed history and learned rules survive -----
        entries_before = feed_entries(app)
        stop_server(proc, log)
        check("server stopped", proc.poll() is not None,
              f"exit code {proc.returncode}")
        proc, log, up = start_server(app)
        if not check("server restarted", up):
            print(LOG_PATH.read_text()[-2000:] if LOG_PATH.exists() else "")
            return
        feed_ok = feed_has(app, MARKER) and len(feed_entries(app)) >= 1
        code, learned = req("GET", "/brain/learned")
        rules_ok = any(LEARN_PHRASE in (r.get("phrase") or "")
                       for r in (learned.get("rules") or []))
        check("restart: feed history + learned rules survive",
              feed_ok and code == 200 and rules_ok,
              f"{len(feed_entries(app))} entries kept "
              f"(was {len(entries_before)}), rule still learned")
    finally:
        if proc is not None:
            stop_server(proc, log)
        BRAIN_DISK.write_bytes(brain_backup)
        for p, data in state_backups.items():
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(data)

    failed = [n for n, ok in _results if not ok]
    print("-" * 60)
    if failed:
        print(f"LIGHTFERN NOT READY — {len(failed)} failed: {', '.join(failed)}")
        sys.exit(1)
    print(f"LIGHTFERN READY — {len(_results)} checks passed")


if __name__ == "__main__":
    main()
