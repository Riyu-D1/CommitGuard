"""Live message feed: Slack monitor + simulated fallback (owner: Riyansh).

A daemon thread started on FastAPI startup polls conversations.history when
SLACK_BOT_TOKEN + SLACK_CHANNEL_ID are set; otherwise it cycles
backend/scenarios.json so the demo works fully offline. Every message runs
through the same _verify() pipeline as POST /verify-context, lands in the
in-memory feed (last 200) and feed_log.jsonl, and is written to the audit
trail via actions.audit(). All failures are fail-open.

Env vars are read from the real environment first, then backend/.env via a
tiny stdlib parser (no dependency). With SLACK_REPLY=1 a flagged message
also gets one threaded Block Kit warning and a clean message a single ✅
reaction; bot/subtype/own messages are ignored so the monitor never loops
on its own posts. The token value is never logged or returned — only the
string "set" or "missing".
"""

import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import actions

BASE = Path(__file__).parent
FEED_LOG_PATH = BASE / "feed_log.jsonl"
BRAIN_PATH = BASE / "company_brain.json"
ENV_PATH = BASE / ".env"


def _load_env_file(path=ENV_PATH):
    """Minimal .env loader — stdlib only. KEY=value lines, '#' comments,
    optional surrounding quotes, optional 'export ' prefix. Real environment
    variables always win (setdefault); missing file is silently fine."""
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key:
            os.environ.setdefault(key, val)


_load_env_file()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
SLACK_REPLY = os.environ.get("SLACK_REPLY") == "1"
MODE = "slack" if (SLACK_BOT_TOKEN and SLACK_CHANNEL_ID) else "simulated"

POLL_SECONDS = 3
SIM_SECONDS = 8
MAX_FEED = 200

log = logging.getLogger("commitguard.feed")

_lock = threading.Lock()
_feed = []          # append order; ids increase monotonically
_next_id = 1
_seen_ts = set()    # slack ts already consumed
_last_ts = "0"      # conversations.history oldest cursor
_last_poll_ts = None
_last_error = None
_sim_idx = 0
_verify = None      # injected by main at startup
_scenarios = []     # [(key, scenario_dict), ...]
_started = False
_bot_user_id = None  # from auth.test — our own messages are always ignored


def start(verify_fn, scenarios) -> None:
    """Called once from main's lifespan. Non-blocking: spawns a daemon thread."""
    global _verify, _scenarios, _started, _last_ts
    if _started:
        return
    _started = True
    _verify = verify_fn
    _scenarios = list(scenarios.items())
    if MODE == "slack":
        _last_ts = str(time.time())  # tail -f: only messages posted after startup
        threading.Thread(target=_slack_loop, daemon=True, name="cg-slack-poll").start()
        log.warning("commitguard feed: mode=slack channel=%s token=set reply=%s",
                    SLACK_CHANNEL_ID, "on" if SLACK_REPLY else "off")
    else:
        threading.Thread(target=_sim_loop, daemon=True, name="cg-sim-feed").start()
        missing = [k for k in ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID")
                   if not os.environ.get(k)]
        log.warning("commitguard feed: mode=simulated (%s missing — "
                    "set them in backend/.env to go live)", " + ".join(missing))


def _push(text, source, user=None, channel=None,
          context_type="slack_message", slack_ts=None) -> dict:
    """Run one message through the verify pipeline and record it as a feed item."""
    global _next_id
    res = _verify(text, context_type)
    item = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "channel": channel,
        "user": user,
        "text": text,
        "context_type": context_type,
        "status": res["status"],
        "risk_level": res["risk_level"],
        "violations": res["violations"],
        "suggested_rewrite": res["suggested_rewrite"],
        "advisories": res["advisories"],
        "meta": res["meta"],
    }
    if slack_ts:
        item["slack_ts"] = slack_ts
    with _lock:
        item["id"] = _next_id
        _next_id += 1
        _feed.append(item)
        del _feed[:-MAX_FEED]
        try:
            with FEED_LOG_PATH.open("a") as f:
                f.write(json.dumps(item) + "\n")
        except Exception as e:
            log.warning("feed_log write failed: %s", e)
    _audit(item)
    _maybe_reply(item)
    return item


def _audit(item: dict) -> None:
    try:
        actions.audit({
            "action_type": "FEED_CHECK",
            "payload": {
                "source": item["source"], "channel": item["channel"],
                "user": item["user"], "text": item["text"],
            },
            "result": item["status"].lower(),
            "risk_level": item["risk_level"],
            "categories": [v.get("category") for v in item["violations"]],
        })
    except Exception as e:
        log.warning("audit write failed: %s", e)


def _ssl_context():
    """CA bundle for Slack calls — uv-managed Pythons ship without one.
    Order: certifi (if present), $SSL_CERT_FILE, macOS /etc/ssl/cert.pem,
    else the stdlib default (which may still work)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for cafile in (os.environ.get("SSL_CERT_FILE"), "/etc/ssl/cert.pem"):
        if cafile and Path(cafile).exists():
            return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


_SSL = _ssl_context()


def _slack_request(path, params=None, payload=None, timeout=5, retries=2) -> dict:
    """One Slack Web API call. Honors the 429 Retry-After header with up to
    `retries` re-tries, then raises."""
    url = f"https://slack.com/api/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                wait = float(e.headers.get("Retry-After") or 5)
                log.warning("slack 429 on %s — Retry-After %.0fs", path, wait)
                time.sleep(wait)
                continue
            raise


def _slack_loop() -> None:
    global _last_ts, _last_poll_ts, _last_error, _bot_user_id
    try:
        auth = _slack_request("auth.test")
        if auth.get("ok"):
            _bot_user_id = auth.get("user_id")
            log.warning("slack auth.test ok: user=%s team=%s",
                        auth.get("user"), auth.get("team"))
        else:
            log.warning("slack auth.test not ok: %s", auth.get("error"))
    except Exception as e:
        log.warning("slack auth.test failed (monitoring anyway): %s", e)
    while True:
        try:
            data = _slack_request(
                "conversations.history",
                params={"channel": SLACK_CHANNEL_ID, "oldest": _last_ts, "limit": "100"})
            _last_poll_ts = datetime.now(timezone.utc).isoformat()
            if data.get("ok"):
                _last_error = None
                for m in sorted(data.get("messages", []),
                                key=lambda m: float(m.get("ts", "0"))):
                    ts = m.get("ts")
                    if not ts or ts in _seen_ts:
                        continue
                    _seen_ts.add(ts)
                    if len(_seen_ts) > 1000:
                        _seen_ts.intersection_update(
                            {t for t in _seen_ts if float(t) >= float(_last_ts)})
                    if float(ts) > float(_last_ts):
                        _last_ts = ts
                    # never loop: skip bot messages, any subtype (joins,
                    # edits, thread broadcasts…), and our own user id
                    if m.get("subtype") or m.get("bot_id"):
                        continue
                    if _bot_user_id and m.get("user") == _bot_user_id:
                        continue
                    text = (m.get("text") or "").strip()
                    if text:
                        _push(text, "slack", user=m.get("user"),
                              channel=SLACK_CHANNEL_ID, slack_ts=ts)
            else:
                _last_error = f"slack api: {data.get('error')}"
                log.warning("conversations.history not ok: %s", data.get("error"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = float(e.headers.get("Retry-After") or 5)
                log.warning("slack rate limited - sleeping %.0fs", wait)
                time.sleep(wait)
            else:
                _last_error = f"slack http {e.code}"
                log.warning("slack http error %s", e.code)
        except Exception as e:
            _last_error = f"{type(e).__name__}: {e}"
            log.warning("slack poll failed: %s", e)
        time.sleep(POLL_SECONDS)


def _alert_icon(item: dict) -> str:
    """🛑 when any violation is CRITICAL, else ⚠️. (risk_level tops out at
    HIGH, so severity must come off the violations themselves.)"""
    return "🛑" if any(v.get("severity") == "CRITICAL"
                       for v in item.get("violations") or []) else "⚠️"


def build_blocks(item: dict) -> list:
    """Block Kit payload for one flagged message: a header, then per
    violation a section with the issue, a context line citing the brain
    evidence, and a quote with the fix."""
    violations = item.get("violations") or []
    n = len(violations)
    icon = _alert_icon(item)
    blocks = [{
        "type": "header",
        "text": {"type": "plain_text", "emoji": True,
                 "text": f"{icon} CommitGuard caught {n} issue{'s' if n != 1 else ''}"},
    }]
    for v in violations:
        ev = v.get("evidence") or {}
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text":
            f"*[{v.get('severity')}] {v.get('category')}* — {v.get('issue')}"}})
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
            f"Brain says: {ev.get('expected', '—')} · "
            f"Found: {ev.get('found', '—')}"}]})
        fix = v.get("suggested_rewrite") or v.get("correction")
        if fix:
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                                                       "text": f">{fix}"}})
    return blocks


def _post_reply(item: dict) -> None:
    n = len(item["violations"])
    icon = _alert_icon(item)
    fallback = f"{icon} CommitGuard caught {n} issue{'s' if n != 1 else ''}"
    data = _slack_request("chat.postMessage", payload={
        "channel": item["channel"], "thread_ts": item["slack_ts"],
        "text": fallback, "blocks": build_blocks(item)})
    if not data.get("ok"):
        log.warning("chat.postMessage failed: %s", data.get("error"))


def _react_clean(item: dict) -> None:
    """✅ on a clean message. missing_scope (no reactions:write) and every
    other failure are silent — a check-mark is never worth noise."""
    try:
        data = _slack_request("reactions.add", payload={
            "channel": item["channel"], "timestamp": item["slack_ts"],
            "name": "white_check_mark"})
        if not data.get("ok") and data.get("error") not in (
                "missing_scope", "already_reacted"):
            log.warning("reactions.add failed: %s", data.get("error"))
    except Exception:
        pass


def _maybe_reply(item: dict) -> None:
    """Active mode (SLACK_REPLY=1, slack-sourced items only): a flagged
    message gets one threaded Block Kit warning; a clean message gets only
    a ✅ reaction — never a thread reply, so the channel isn't spammed."""
    if not (SLACK_REPLY and item.get("source") == "slack" and item.get("slack_ts")):
        return
    try:
        if item["status"] == "VIOLATION_DETECTED" and item["violations"]:
            _post_reply(item)
        else:
            _react_clean(item)
    except Exception as e:
        log.warning("slack reply/react failed: %s", e)


def _sim_loop() -> None:
    global _sim_idx, _last_poll_ts, _last_error
    while True:
        try:
            if _scenarios:
                key, sc = _scenarios[_sim_idx % len(_scenarios)]
                _sim_idx += 1
                _push(sc["text"], "simulated", user=sc.get("label") or key,
                      context_type=sc.get("context_type", "slack_message"))
            _last_poll_ts = datetime.now(timezone.utc).isoformat()
            _last_error = None
        except Exception as e:
            _last_error = f"{type(e).__name__}: {e}"
            log.warning("simulated feed tick failed: %s", e)
        time.sleep(SIM_SECONDS)


def inject(text, user=None):
    """POST /feed/inject path — same pipeline, source 'manual'."""
    if _verify is None:
        return None
    return _push(text, "manual", user=user)


def get_feed(since=None, limit=50) -> list:
    with _lock:
        items = [i for i in _feed if since is None or i["id"] > since]
    return items[::-1][:limit]


def get_item(feed_id) -> dict:
    """One live feed item by id (None if it has rotated out or never existed)."""
    with _lock:
        for i in _feed:
            if i["id"] == feed_id:
                return i
    return None


def update_item(feed_id, res: dict) -> dict:
    """Overwrite a feed item's verdict fields from a fresh verify result —
    used after /feed/{id}/override learns a rule so the item visibly flips
    from CLEAN to caught."""
    with _lock:
        for i in _feed:
            if i["id"] == feed_id:
                for k in ("status", "risk_level", "violations",
                          "suggested_rewrite", "advisories", "meta"):
                    i[k] = res[k]
                return i
    return None


def record_override(feed_id, decision, phrase=None, note=None, rule_id=None) -> dict:
    """Append a human-override record to feed_log.jsonl and the audit trail."""
    rec = {
        "type": "override",
        "ts": datetime.now(timezone.utc).isoformat(),
        "feed_id": feed_id,
        "decision": decision,
        "phrase": phrase,
        "note": note,
        "rule_id": rule_id,
    }
    with _lock:
        try:
            with FEED_LOG_PATH.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as e:
            log.warning("feed_log override write failed: %s", e)
    try:
        actions.audit({
            "action_type": "FEED_OVERRIDE",
            "payload": {"feed_id": feed_id, "decision": decision,
                        "phrase": phrase, "note": note},
            "result": "learned" if decision == "missed" else "false_positive",
        })
    except Exception as e:
        log.warning("audit write failed: %s", e)
    return rec


def _learned_rules_count() -> int:
    try:
        brain = json.loads(BRAIN_PATH.read_text())
        return len(brain.get("learned_rules") or [])
    except Exception:
        return 0


def get_stats() -> dict:
    with _lock:
        items = list(_feed)
    by_category = {}
    flagged = critical = clean = 0
    for i in items:
        if i["status"] == "VIOLATION_DETECTED":
            flagged += 1
        else:
            clean += 1
        if any(v.get("severity") == "CRITICAL" for v in i["violations"]):
            critical += 1
        for v in i["violations"]:
            by_category[v["category"]] = by_category.get(v["category"], 0) + 1
    return {"total": len(items), "flagged": flagged, "critical": critical,
            "clean": clean, "by_category": by_category,
            "last_ts": items[-1]["ts"] if items else None, "mode": MODE,
            "learned": _learned_rules_count()}


def slack_status() -> dict:
    """GET /slack/status payload — the token is reported only as
    "set" | "missing", never its value."""
    return {
        "mode": MODE,
        "channel": SLACK_CHANNEL_ID if MODE == "slack" else None,
        "token": "set" if SLACK_BOT_TOKEN else "missing",
        "reply_enabled": SLACK_REPLY,
        "last_poll_ts": _last_poll_ts,
        "last_error": _last_error,
    }


def health_info() -> dict:
    info = {"mode": MODE, "channel": SLACK_CHANNEL_ID if MODE == "slack" else None,
            "last_poll_ts": _last_poll_ts}
    if _last_error:
        info["error"] = _last_error
    return info
