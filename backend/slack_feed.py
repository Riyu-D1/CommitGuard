"""Live message feed: Slack monitor + simulated fallback (owner: Riyansh).

A daemon thread started on FastAPI startup polls conversations.history when
SLACK_BOT_TOKEN + SLACK_CHANNEL_ID are set; otherwise it cycles
backend/scenarios.json so the demo works fully offline. Every message runs
through the same _verify() pipeline as POST /verify-context, lands in the
in-memory feed (last 200) and feed_log.jsonl, and is written to the audit
trail via actions.audit(). All failures are fail-open.
"""

import json
import logging
import os
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
        log.warning("slack feed started on channel %s", SLACK_CHANNEL_ID)
    else:
        threading.Thread(target=_sim_loop, daemon=True, name="cg-sim-feed").start()
        log.warning("no SLACK_BOT_TOKEN/SLACK_CHANNEL_ID - feed running in simulated mode")


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


def _slack_request(path, params=None, payload=None, timeout=5) -> dict:
    url = f"https://slack.com/api/{path}"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _slack_loop() -> None:
    global _last_ts, _last_poll_ts, _last_error
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
                    if m.get("subtype") or m.get("bot_id"):
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


def _maybe_reply(item: dict) -> None:
    """One threaded warning per flagged slack message. OFF unless SLACK_REPLY=1."""
    if not (SLACK_REPLY and item["source"] == "slack" and item.get("slack_ts")):
        return
    if item["status"] != "VIOLATION_DETECTED" or not item["violations"]:
        return
    parts = []
    for v in item["violations"]:
        seg = f"{v['category']}: {v['correction']}"
        ev = v.get("evidence") or {}
        if ev.get("brain_key"):
            seg += (f" Evidence: {ev['brain_key']} "
                    f"expected {ev.get('expected')}, found {ev.get('found')}.")
        parts.append(seg)
    n = len(item["violations"])
    body = f":shield: CommitGuard flagged {n} issue{'s' if n != 1 else ''} — " + "\n".join(parts)
    try:
        _slack_request("chat.postMessage", payload={
            "channel": item["channel"], "thread_ts": item["slack_ts"], "text": body})
    except Exception as e:
        log.warning("slack reply failed: %s", e)


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
            "last_ts": items[-1]["ts"] if items else None, "mode": MODE}


def health_info() -> dict:
    info = {"mode": MODE, "channel": SLACK_CHANNEL_ID if MODE == "slack" else None,
            "last_poll_ts": _last_poll_ts}
    if _last_error:
        info["error"] = _last_error
    return info
