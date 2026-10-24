"""End-to-end test for the Lightfern file bridge — no server, no Lightfern.

Uses a temp app dir exactly as the desktop would: a check lands in
live/feed.json, an inbox learn command updates + re-exports the brain, an
"ask" produces live/answers/<id>.json, a corrupted brain/company_brain.json
keeps the old brain (and logs it), and a valid edit inside the app folder
is imported back into the backend brain.

All brain writes are redirected to a temp file (main.BRAIN_PATH and the
rules.add_learned_* defaults are patched), so the repo's real
company_brain.json is never touched. Exits 1 on the first failure list,
prints ALL PASS when clean.

    uv run python test_lightfern_bridge.py
"""

import json
import sys
import tempfile
import time
from pathlib import Path

import actions
import main
import rules
import slack_feed
import lightfern_bridge as lb

failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        failures.append(name)


def wait_for(desc, pred, timeout=6.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    print(f"  …timed out waiting for {desc}")
    return False


def main_test():
    real_brain_text = (main.BASE / "company_brain.json").read_text()

    orig_brain_path = main.BRAIN_PATH
    orig_brain = main.COMPANY_BRAIN
    orig_rule = rules.add_learned_rule
    orig_exc = rules.add_learned_exception
    orig_audit_fn = actions.audit

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        app = tmp / "CommitGuard Brain"
        tmp_brain = tmp / "company_brain.json"
        tmp_brain.write_text(real_brain_text)

        # Redirect every brain write/read to the temp file: real backend
        # brain stays byte-identical.
        main.BRAIN_PATH = tmp_brain
        rules.add_learned_rule = (
            lambda r, brain_path=None: orig_rule(r, brain_path=brain_path or tmp_brain))
        rules.add_learned_exception = (
            lambda r, brain_path=None: orig_exc(r, brain_path=brain_path or tmp_brain))

        # Keep audit/feed logs clean of test rows (they're gitignored local
        # state, but the suite shouldn't grow them either).
        audit_rows = []
        actions.audit = lambda e: audit_rows.append(e) or e
        feed_log = slack_feed.FEED_LOG_PATH
        feed_log_before = feed_log.read_text() if feed_log.exists() else None

        hooks = {
            "learn": main._learn,
            "exception": main._learn_exception,
            "override": main._apply_override,
            "ask": main._ask_brain,
            "import_brain": main._import_brain,
        }

        started = lb.start(app_dir=str(app), hooks=hooks, brain_path=tmp_brain)
        check("start() enables the bridge", started and lb.status()["enabled"])

        try:
            # ---- export on startup ------------------------------------
            exported = app / "brain" / "company_brain.json"
            check("brain exported", exported.exists())
            policies = list((app / "brain" / "policies").glob("*.md"))
            check("policies exported", len(policies) >= 10,
                  f"{len(policies)} files")
            check("policy md is readable",
                  policies and "**Rule.**" in policies[0].read_text())

            # ---- a check lands in live/feed.json ----------------------
            res = main._verify(
                "We can offer Net-60 terms and a 15% discount.", "outgoing_email")
            lb.record_api_check(
                "We can offer Net-60 terms and a 15% discount.",
                "outgoing_email", res)
            feed = json.loads((app / "live" / "feed.json").read_text())
            check("feed.json has the check",
                  len(feed.get("entries", [])) == 1
                  and feed["entries"][0]["status"] == "VIOLATION_DETECTED"
                  and feed["entries"][0]["feed_id"] is None,
                  f"{len(feed.get('entries', []))} entries")

            # a feed item (slack/simulated/manual path) lands too, with id
            lb.record_feed_item({
                "id": 77, "kind": "check", "ts": "2026-10-24T00:00:00+00:00",
                "source": "slack", "user": "U1", "text": "all good",
                "context_type": "slack_message", "status": "CLEAN",
                "risk_level": "LOW", "violations": [], "actions": [],
                "suggested_rewrite": None, "advisories": [], "meta": {}})
            feed = json.loads((app / "live" / "feed.json").read_text())
            check("feed item lands with feed_id",
                  len(feed["entries"]) == 2
                  and feed["entries"][0]["feed_id"] == 77
                  and feed["entries"][0]["source"] == "slack")

            # ---- learn command in inbox/ ------------------------------
            (app / "inbox" / "t1-learn.json").write_text(json.dumps({
                "cmd": "learn", "phrase": "kickback scheme",
                "severity": "CRITICAL"}))
            ok = wait_for("inbox learn processed", lambda: (
                app / "inbox" / "done" / "t1-learn.json").exists())
            check("learn command processed", ok)
            brain = json.loads(tmp_brain.read_text())
            learned = [r.get("phrase") for r in brain.get("learned_rules", [])]
            check("learned rule in backend brain",
                  "kickback scheme" in learned, str(learned))
            check("learned rule severity kept",
                  any(r.get("severity") == "CRITICAL"
                      for r in brain.get("learned_rules", [])
                      if r.get("phrase") == "kickback scheme"))
            exported_brain = json.loads(exported.read_text())
            check("brain re-exported with the rule",
                  "kickback scheme" in [
                      r.get("phrase") for r in
                      exported_brain.get("learned_rules", [])])
            policy_text = "\n".join(p.read_text() for p in
                                    (app / "brain" / "policies").glob("*.md"))
            check("learned rule became a policy file",
                  "kickback scheme" in policy_text)
            result = json.loads((app / "inbox" / "done" /
                                 "t1-learn.json.result.json").read_text())
            check("learn result recorded", result.get("ok") is True)

            # ---- ask command → live/answers/<id>.json -----------------
            (app / "inbox" / "t2-ask.json").write_text(json.dumps({
                "cmd": "ask", "id": "ask-t2",
                "question": "can I give a 20% discount?"}))
            ok = wait_for("ask answered", lambda: (
                app / "live" / "answers" / "ask-t2.json").exists())
            check("ask command answered", ok)
            if ok:
                ans = json.loads((app / "live" / "answers" /
                                  "ask-t2.json").read_text())
                check("answer cites the brain",
                      ans.get("matched") is True and bool(ans.get("sources")),
                      str(ans.get("sources")))

            # ---- 'fine' command with no feed_id → exception -----------
            (app / "inbox" / "t3-fine.json").write_text(json.dumps({
                "cmd": "override", "decision": "false_positive",
                "phrase": "£85/seat", "category": "PRICE_FLOOR"}))
            ok = wait_for("exception learned", lambda: (
                app / "inbox" / "done" / "t3-fine.json").exists())
            check("fine command processed", ok)
            brain = json.loads(tmp_brain.read_text())
            check("exception stored",
                  any(x.get("phrase") == "£85/seat"
                      and x.get("category") == "PRICE_FLOOR"
                      for x in brain.get("learned_exceptions", [])))

            # ---- override with feed_id → same path as HTTP ------------
            # push a real feed item so _apply_override can find id 42
            with slack_feed._lock:
                slack_feed._feed.append({
                    "id": 42, "kind": "check", "ts": "2026-10-24T00:00:00+00:00",
                    "source": "manual", "user": "t", "text": "totally fine msg",
                    "context_type": "slack_message", "status": "CLEAN",
                    "risk_level": "LOW", "violations": [],
                    "suggested_rewrite": None, "advisories": [],
                    "actions": [], "meta": {}})
            (app / "inbox" / "t4-missed.json").write_text(json.dumps({
                "cmd": "override", "decision": "missed", "feed_id": 42,
                "phrase": "totally fine"}))
            ok = wait_for("feed override processed", lambda: (
                app / "inbox" / "done" / "t4-missed.json").exists())
            check("feed override processed", ok)
            brain = json.loads(tmp_brain.read_text())
            check("missed override learned a rule",
                  "totally fine" in [r.get("phrase") for r in
                                     brain.get("learned_rules", [])])
            item = slack_feed.get_item(42)
            check("feed item rechecked to flagged",
                  item is not None
                  and item["status"] == "VIOLATION_DETECTED")
            feed = json.loads((app / "live" / "feed.json").read_text())
            e42 = next((e for e in feed["entries"]
                        if e.get("feed_id") == 42), None)
            check("flipped verdict mirrored to feed.json",
                  e42 is not None
                  and e42["status"] == "VIOLATION_DETECTED"
                  and e42.get("overridden_by") == "missed")

            # ---- bad brain edit inside the app keeps the old brain ----
            before = tmp_brain.read_text()
            exported.write_text("{ this is not json")
            ok = wait_for("bad-brain error logged", lambda: bool(
                json.loads((app / "live" / "status.json")
                           .read_text()).get("errors")), timeout=4)
            check("bad brain json logged to status.json", ok)
            check("old brain kept on bad json",
                  tmp_brain.read_text() == before)

            # ---- valid edit inside the app imports back ---------------
            edited = json.loads(before)
            edited["financial_rules"]["max_unapproved_discount_percent"] = 7
            exported.write_text(json.dumps(edited, indent=2))
            ok = wait_for("brain import", lambda: json.loads(
                tmp_brain.read_text())["financial_rules"]
                ["max_unapproved_discount_percent"] == 7)
            check("valid in-app edit imports into the backend brain", ok)
            ok = wait_for("import re-export settles", lambda: json.loads(
                exported.read_text())["financial_rules"]
                ["max_unapproved_discount_percent"] == 7)
            check("imported brain re-exported", ok)
            check("in-memory brain swapped",
                  main.COMPANY_BRAIN["financial_rules"]
                  ["max_unapproved_discount_percent"] == 7)

            # ---- status endpoint ---------------------------------------
            st = lb.status()
            check("/lightfern/status payload",
                  st["enabled"] is True and st["app_dir"] == str(app.resolve())
                  and st["checks_total"] >= 1 and st["inbox_processed"] >= 3,
                  str(st))

            check("real company_brain.json untouched",
                  (main.BASE / "company_brain.json").read_text()
                  == real_brain_text)
        finally:
            lb.stop()
            with slack_feed._lock:
                slack_feed._feed = [i for i in slack_feed._feed
                                    if i.get("id") != 42]
            if feed_log_before is None:
                feed_log.unlink(missing_ok=True)
            else:
                feed_log.write_text(feed_log_before)
            main.BRAIN_PATH = orig_brain_path
            main.COMPANY_BRAIN = orig_brain
            rules.add_learned_rule = orig_rule
            rules.add_learned_exception = orig_exc
            actions.audit = orig_audit_fn

    print()
    if failures:
        print("FAILURES:", ", ".join(failures))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
