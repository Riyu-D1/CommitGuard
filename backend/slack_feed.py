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

Questions: a channel message starting with "?" or "ask:" (case-insensitive),
or mentioning the bot user, is a QUESTION — it isn't run through the rules
engine. It's answered from the brain via the injected ask_fn (same logic as
POST /ask), logged as a feed item with kind="question", and — in reply mode —
gets a threaded Block Kit answer citing each source brain_key. Everything
else is a compliance check with kind="check".

Thread commands: replying inside a CommitGuard thread with "missed: <phrase>"
or "fine" triggers the injected override_fn (same logic as
POST /feed/{id}/override — 'missed' teaches a rule, 'fine' a learned
exception) and the bot answers "📚 Learned: …". Threads the bot has posted
in are polled via conversations.replies for 30 min after posting, at most
once every 5s.

Brain-update proposals: when a check item reads as an authoritative
decision, the injected decision_fn (TribalSync) attaches a brain-patch
proposal to the feed item — never auto-applied. In reply mode it's posted
into the message's thread as a "🧠 Brain update proposed" Block Kit card;
a human answers "apply" or "reject" inside that thread, the injected
proposal_fn (same logic as POST /brain/proposals/{id}/apply|reject) runs,
and the bot confirms "🧠 Brain updated: …" or "🧠 Proposal rejected —
brain unchanged." Proposal and override commands share one tracked thread.
"""

import json
import logging
import os
import re
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
_ask = None          # injected by main — same logic as POST /ask
_override = None     # injected by main — same logic as POST /feed/{id}/override
_decision_fn = None  # injected by main — TribalSync brain-patch detector
_proposal_fn = None  # injected by main — apply/reject a pending proposal
_chase = None        # injected by main — same logic as POST /chase
_chase_command = None  # injected by main — thread 'log'/'paid' on a chase
_cmd_threads = []    # threads the bot replied in (thread commands)
_last_cmd_scan = 0.0
CMD_SCAN_SECONDS = 5
CMD_THREAD_TTL = 1800  # poll a bot thread for commands for 30 min
_feed_listeners = []  # fn(item) called on every pushed/updated feed item
                       # (used by the Lightfern bridge to mirror the feed)


def add_feed_listener(fn) -> None:
    """Register fn(item) — called with a copy of every feed item after it is
    stored (_push) and after update_item rewrites its verdict. Fail-open:
    a listener exception is logged, never raised."""
    if fn not in _feed_listeners:
        _feed_listeners.append(fn)


def remove_feed_listener(fn) -> None:
    if fn in _feed_listeners:
        _feed_listeners.remove(fn)


def _notify(item: dict) -> None:
    for fn in list(_feed_listeners):
        try:
            fn(dict(item))
        except Exception as e:
            log.warning("feed listener failed: %s", e)


def _parse_question(text):
    """If `text` is an ask ("?…", "ask:…" case-insensitive, or an @bot
    mention), return the bare question string; otherwise None."""
    t = (text or "").strip()
    if t.startswith("?"):
        return t[1:].strip() or None
    if t[:4].lower() == "ask:":
        return t[4:].strip() or None
    if _bot_user_id and f"<@{_bot_user_id}>" in t:
        return t.replace(f"<@{_bot_user_id}>", "").strip() or None
    return None


_CHASE_CMD_RE = re.compile(r"(?i)^\s*chase[:\s]+(.+?)\s*$")


def _parse_chase(text):
    """'chase INV-1048' / 'chase Acme' (case-insensitive) -> the invoice or
    customer ref to draft a chase for; otherwise None."""
    m = _CHASE_CMD_RE.match(text or "")
    return m.group(1) if m else None


def start(verify_fn, scenarios, ask_fn=None, override_fn=None,
          decision_fn=None, proposal_fn=None,
          chase_fn=None, chase_command_fn=None) -> None:
    """Called once from main's lifespan. Non-blocking: spawns a daemon thread."""
    global _verify, _scenarios, _started, _last_ts, _ask, _override, \
        _decision_fn, _proposal_fn, _chase, _chase_command
    if _started:
        return
    _started = True
    _verify = verify_fn
    _scenarios = list(scenarios.items())
    _ask = ask_fn
    _override = override_fn
    _decision_fn = decision_fn
    _proposal_fn = proposal_fn
    _chase = chase_fn
    _chase_command = chase_command_fn
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
    """Run one message through the verify pipeline and record it as a feed
    item — unless it's a question (?/ask:/@bot), which is answered from the
    brain instead of checked."""
    global _next_id
    chase_ref = (_parse_chase(text)
                 if source in ("slack", "manual") and _chase is not None
                 else None)
    if chase_ref is not None:
        try:
            res = _chase(chase_ref)
        except Exception as e:
            res = {"error": f"chase failed: {e}"}
        item = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": "chase",
            "source": source,
            "channel": channel,
            "user": user,
            "text": text,
            "context_type": context_type,
            "status": "CHASE",
            "risk_level": "LOW",
            "violations": [],
            "chase": res,
            "suggested_rewrite": None,
            "advisories": [],
            "actions": [],
            "meta": {"engine": res.get("engine", "rules")},
        }
    elif (_parse_question(text) if source in ("slack", "manual")
          and _ask is not None else None) is not None:
        question = _parse_question(text)
        res = _ask(question)
        item = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": "question",
            "source": source,
            "channel": channel,
            "user": user,
            "text": text,
            "context_type": context_type,
            "question": question,
            "status": "QUESTION",
            "risk_level": "LOW",
            "violations": [],
            "answer": res["answer"],
            "sources": res.get("sources") or [],
            "matched": bool(res.get("matched")),
            "suggested_rewrite": None,
            "advisories": [],
            "actions": [],
            "meta": res.get("meta") or {},
        }
    else:
        res = _verify(text, context_type)
        item = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": "check",
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
            "actions": res.get("actions") or [],
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
    if item.get("kind") != "question" and _decision_fn is not None:
        proposal = None
        try:
            proposal = _decision_fn(item)
        except Exception as e:
            log.warning("decision detection failed: %s", e)
        if proposal:
            item["proposal"] = proposal
            item["proposal_id"] = proposal.get("id")
            try:  # audit trail: the item itself was logged pre-detection
                with FEED_LOG_PATH.open("a") as f:
                    f.write(json.dumps({"type": "proposal",
                                        "feed_id": item["id"],
                                        "proposal": proposal}) + "\n")
            except Exception as e:
                log.warning("feed_log proposal write failed: %s", e)
    _notify(item)
    _audit(item)
    _maybe_reply(item)
    return item


def _audit(item: dict) -> None:
    try:
        if item.get("kind") == "chase":
            d = item.get("chase") or {}
            actions.audit({
                "action_type": "CHASE_DRAFT",
                "payload": {
                    "source": item["source"], "channel": item["channel"],
                    "user": item["user"], "text": item["text"],
                    "invoice_id": d.get("invoice_id"),
                    "customer": d.get("customer"), "tone": d.get("tone"),
                    "days_overdue": d.get("days_overdue"),
                },
                "result": "error" if d.get("error") else "drafted",
            })
            return
        if item.get("kind") == "question":
            actions.audit({
                "action_type": "FEED_ASK",
                "payload": {
                    "source": item["source"], "channel": item["channel"],
                    "user": item["user"], "text": item["text"],
                    "question": item["question"],
                },
                "result": "answered" if item.get("matched") else "unmatched",
            })
            return
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
        try:
            _scan_thread_commands()
        except Exception as e:
            log.warning("thread command scan failed: %s", e)
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
    acts = item.get("actions") or []
    if acts:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": "🤖 Actions: " + " · ".join(
                a.get("label") or a.get("type", "") for a in acts)}]})
    return blocks


def build_advisory_blocks(item: dict) -> list:
    """Softer reply for a rule-CLEAN message that still has LLM advisories:
    '💡 Worth a check', each advisory's issue, and its suggested rewrite.
    Advisories are advisory only — never framed as rule violations."""
    blocks = [{
        "type": "header",
        "text": {"type": "plain_text", "emoji": True,
                 "text": "💡 Worth a check"},
    }]
    for a in item.get("advisories") or []:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"• {a.get('issue', '')}"}})
        fix = a.get("suggested_rewrite") or a.get("correction")
        if fix:
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                                                       "text": f">{fix}"}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": "Advisory only — the rules engine found no violation."}]})
    return blocks


def build_question_blocks(item: dict) -> list:
    """Block Kit payload for a question feed item: the brain's answer, then
    one 'Source: <brain_key> = <value>' context line per cited source.
    Unmatched questions say the brain doesn't cover it yet."""
    answer = item.get("answer") or "Not in the company brain yet."
    blocks = [{
        "type": "header",
        "text": {"type": "plain_text", "emoji": True,
                 "text": "💡 CommitGuard answer"},
    }, {
        "type": "section",
        "text": {"type": "mrkdwn", "text": answer},
    }]
    if not item.get("matched"):
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": "Not in the company brain yet — a human can teach it "
                    "with a correction."}]})
    for s in item.get("sources") or []:
        val = str(s.get("value"))
        if len(val) > 300:
            val = val[:300] + "…"
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Source: `{s.get('brain_key')}` = {val}"}]})
    return blocks


def _mesc(s) -> str:
    """Escape user-derived text for Slack mrkdwn (& < > are special)."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_proposal_blocks(item: dict) -> list:
    """Block Kit payload for a brain-patch proposal: the key it would
    change, who made the call, how many checks it touches, and the
    evidence quote. Humans decide by replying 'apply' or 'reject' in the
    thread — the card itself changes nothing."""
    p = item.get("proposal") or {}
    ev = p.get("evidence") or {}
    author = _mesc(ev.get("author") or "feed")
    n = len(p.get("affected_checks") or p.get("affected_feed_ids") or [])
    key, old, new = (_mesc(p.get("brain_key")), _mesc(p.get("old")),
                     _mesc(p.get("new")))
    msg = _mesc((ev.get("message") or "").strip())
    if len(msg) > 200:
        msg = msg[:200] + "…"
    return [{
        "type": "header",
        "text": {"type": "plain_text", "emoji": True,
                 "text": "🧠 Brain update proposed"},
    }, {
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": f"*{key}*: {old} → {new}"},
    }, {
        "type": "context",
        "elements": [{"type": "mrkdwn",
                      "text": f"from @{author} · affects {n} "
                              f"check{'s' if n != 1 else ''} · "
                              "reply `apply` or `reject`"}],
    }, {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f">{msg or '—'}"},
    }]


def _post_question_reply(item: dict) -> None:
    data = _slack_request("chat.postMessage", payload={
        "channel": item["channel"], "thread_ts": item["slack_ts"],
        "text": item.get("answer") or "CommitGuard answer",
        "blocks": build_question_blocks(item)})
    if not data.get("ok"):
        log.warning("chat.postMessage failed: %s", data.get("error"))


def _track_thread(item: dict, data: dict, proposal_id=None) -> None:
    """Remember a thread the bot posted in so the reply scanner picks up
    'missed: <phrase>' / 'fine' / 'apply' / 'reject' commands under it (or
    'log' / 'paid' under a chase-draft thread).
    One tracked thread handles all command families — a proposal card
    posted under an already-tracked thread merges proposal_id into the
    existing entry."""
    if not data.get("ok"):
        return
    for th in _cmd_threads:
        if th["channel"] == item["channel"] and \
                th["thread_ts"] == item["slack_ts"]:
            if proposal_id:
                th["proposal_id"] = proposal_id
            return
    _cmd_threads.append({"channel": item["channel"],
                         "thread_ts": item["slack_ts"],
                         "feed_id": item.get("id"),
                         "proposal_id": proposal_id,
                         "kind": item.get("kind"),
                         "chase_ref": (item.get("chase") or {}).get("invoice_id"),
                         "posted": time.time(),
                         "seen": {item["slack_ts"]}})


def _post_reply(item: dict) -> None:
    n = len(item["violations"])
    icon = _alert_icon(item)
    fallback = f"{icon} CommitGuard caught {n} issue{'s' if n != 1 else ''}"
    data = _slack_request("chat.postMessage", payload={
        "channel": item["channel"], "thread_ts": item["slack_ts"],
        "text": fallback, "blocks": build_blocks(item)})
    if not data.get("ok"):
        log.warning("chat.postMessage failed: %s", data.get("error"))
    _track_thread(item, data)


def _post_advisory_reply(item: dict) -> None:
    data = _slack_request("chat.postMessage", payload={
        "channel": item["channel"], "thread_ts": item["slack_ts"],
        "text": "💡 Worth a check", "blocks": build_advisory_blocks(item)})
    if not data.get("ok"):
        log.warning("chat.postMessage failed: %s", data.get("error"))
    _track_thread(item, data)


def _post_proposal_reply(item: dict) -> None:
    """Post the '🧠 Brain update proposed' card into the message's thread
    and register that thread for apply/reject commands."""
    data = _slack_request("chat.postMessage", payload={
        "channel": item["channel"], "thread_ts": item["slack_ts"],
        "text": "🧠 Brain update proposed",
        "blocks": build_proposal_blocks(item)})
    if not data.get("ok"):
        log.warning("chat.postMessage failed: %s", data.get("error"))
    _track_thread(item, data,
                  proposal_id=(item.get("proposal") or {}).get("id"))


def _post_chase_reply(item: dict) -> None:
    """Threaded Block Kit reply for a 'chase X' command — the draft, its
    evidence cites, and the log/paid close-out instructions."""
    import chaser  # lazy: keeps slack_feed importable without the chaser deps
    d = item.get("chase") or {}
    fallback = (f"📨 Chase draft — {d.get('invoice_id')} · {d.get('customer')}"
                if not d.get("error") else "⚠️ Chase failed")
    data = _slack_request("chat.postMessage", payload={
        "channel": item["channel"], "thread_ts": item["slack_ts"],
        "text": fallback, "blocks": chaser.build_chase_blocks(item)})
    if not data.get("ok"):
        log.warning("chat.postMessage failed: %s", data.get("error"))
    _track_thread(item, data)


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
    message gets one threaded Block Kit warning; a rule-clean message with
    LLM advisories gets a softer '💡 Worth a check' reply; a truly clean
    message gets only a ✅ reaction — never a thread reply, so the channel
    isn't spammed. A question gets a threaded Block Kit answer citing its
    brain sources. A check item carrying a brain-patch proposal also gets
    a '🧠 Brain update proposed' card in the same thread."""
    if not (SLACK_REPLY and item.get("source") == "slack" and item.get("slack_ts")):
        return
    try:
        if item.get("kind") == "question":
            _post_question_reply(item)
        elif item.get("kind") == "chase":
            _post_chase_reply(item)
        elif item["status"] == "VIOLATION_DETECTED" and item["violations"]:
            _post_reply(item)
        elif item.get("advisories"):
            _post_advisory_reply(item)
        else:
            _react_clean(item)
    except Exception as e:
        log.warning("slack reply/react failed: %s", e)
    if item.get("proposal"):
        try:
            _post_proposal_reply(item)
        except Exception as e:
            log.warning("slack proposal reply failed: %s", e)


def _parse_thread_command(text):
    """Thread-reply commands under a CommitGuard thread:
    'missed: <phrase>' -> ('missed', phrase) teaches a rule;
    'fine' -> ('false_positive', None) learns an exception for that item;
    'apply'/'reject' -> decide a pending brain-patch proposal (exact word
    only — they're common enough that a bare substring can't count)."""
    t = (text or "").strip()
    if t[:7].lower() == "missed:" and t[7:].strip():
        return "missed", t[7:].strip()
    word = t.lower().rstrip(".!")
    if word == "fine":
        return "false_positive", None
    if word == "apply":
        return "apply", None
    if word == "reject":
        return "reject", None
    return None


def _post_learned_reply(th: dict, payload: dict, err) -> None:
    """'📚 Learned: …' confirmation posted into the thread after a thread
    command runs the override — or a short reason why it couldn't."""
    if err:
        text = f"⚠️ Couldn't learn from that: {err}"
    else:
        rule = (payload or {}).get("rule")
        exc = (payload or {}).get("exception")
        if rule:
            text = (f"📚 Learned: '{rule.get('phrase')}' is now a rule — "
                    "enforced immediately.")
        elif exc:
            text = (f"📚 Learned: '{exc.get('phrase')}' no longer triggers "
                    f"{exc.get('category')}.")
        else:
            text = "📚 Learned: override recorded."
    try:
        data = _slack_request("chat.postMessage", payload={
            "channel": th["channel"], "thread_ts": th["thread_ts"],
            "text": text})
        if not data.get("ok"):
            log.warning("learned reply failed: %s", data.get("error"))
    except Exception as e:
        log.warning("learned reply failed: %s", e)


def _post_proposal_reply_status(th: dict, payload: dict, err) -> None:
    """'🧠 Brain updated: …' / '⚠️ …' confirmation posted into the thread
    after an apply/reject command runs the proposal — or a short reason
    why it couldn't."""
    if err:
        text = f"⚠️ {err}"
    else:
        p = payload or {}
        prop = p.get("proposal") or p.get("changelog") or {}
        if p.get("applied"):
            text = (f"🧠 Brain updated: {prop.get('brain_key', '—')} "
                    f"{prop.get('old', '—')} → {prop.get('new', '—')} — "
                    "affected feed items re-checked.")
        else:
            text = "🧠 Proposal rejected — brain unchanged."
    try:
        data = _slack_request("chat.postMessage", payload={
            "channel": th["channel"], "thread_ts": th["thread_ts"],
            "text": text})
        if not data.get("ok"):
            log.warning("proposal status reply failed: %s", data.get("error"))
    except Exception as e:
        log.warning("proposal status reply failed: %s", e)


def _parse_chase_thread_command(text):
    """Inside a chase-draft thread: 'log'/'sent' marks the chase sent,
    'paid' marks the invoice paid."""
    t = (text or "").strip().lower().rstrip(".!")
    if t in ("log", "sent", "logged"):
        return "log"
    if t in ("paid", "they paid", "payment received"):
        return "paid"
    return None


def _post_chase_cmd_reply(th: dict, payload: dict, err) -> None:
    """Confirmation posted into a chase thread after 'log' / 'paid'."""
    if err:
        text = f"⚠️ Couldn't update the chase: {err}"
    elif (payload or {}).get("kind") == "paid":
        text = (f"✅ {payload.get('invoice_id')} marked paid — it's off the "
                "overdue list.")
    else:
        text = (f"📨 Chase logged for {payload.get('invoice_id', 'the invoice')}"
                " — the next draft counts it.")
    try:
        data = _slack_request("chat.postMessage", payload={
            "channel": th["channel"], "thread_ts": th["thread_ts"],
            "text": text})
        if not data.get("ok"):
            log.warning("chase cmd reply failed: %s", data.get("error"))
    except Exception as e:
        log.warning("chase cmd reply failed: %s", e)


def _scan_thread_commands() -> None:
    """Poll conversations.replies on threads the bot posted in during the
    last 30 min, at most once every CMD_SCAN_SECONDS. Bot/subtype/own
    replies are ignored; 429 Retry-After is honored inside _slack_request."""
    global _last_cmd_scan
    if _override is None and _proposal_fn is None and \
            _chase_command is None:
        return
    now = time.time()
    if now - _last_cmd_scan < CMD_SCAN_SECONDS:
        return
    _last_cmd_scan = now
    cutoff = now - CMD_THREAD_TTL
    for th in list(_cmd_threads):
        if th["posted"] < cutoff:
            _cmd_threads.remove(th)
            continue
        try:
            data = _slack_request(
                "conversations.replies",
                params={"channel": th["channel"], "ts": th["thread_ts"],
                        "oldest": th["thread_ts"], "limit": "100"})
        except Exception as e:
            log.warning("conversations.replies failed: %s", e)
            continue
        if not data.get("ok"):
            log.warning("conversations.replies not ok: %s", data.get("error"))
            continue
        for m in sorted(data.get("messages", []),
                        key=lambda x: float(x.get("ts", "0"))):
            ts = m.get("ts")
            if not ts or ts in th["seen"] or float(ts) <= float(th["thread_ts"]):
                continue
            th["seen"].add(ts)
            if m.get("subtype") or m.get("bot_id") or \
                    (_bot_user_id and m.get("user") == _bot_user_id):
                continue
            if th.get("kind") == "chase" and _chase_command is not None:
                ccmd = _parse_chase_thread_command(m.get("text"))
                if not ccmd:
                    continue
                payload, err = _chase_command(th.get("chase_ref"), ccmd)
                _post_chase_cmd_reply(th, payload, err)
                continue
            cmd = _parse_thread_command(m.get("text"))
            if not cmd:
                continue
            decision, phrase = cmd
            if decision in ("apply", "reject"):
                if not th.get("proposal_id") or _proposal_fn is None:
                    continue  # common words — only count on proposal threads
                payload, err = _proposal_fn(
                    th["proposal_id"], decision, m.get("user"))
                _post_proposal_reply_status(th, payload, err)
                continue
            if _override is None:
                continue
            payload, err = _override(th["feed_id"], decision, phrase=phrase)
            _post_learned_reply(th, payload, err)


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


def inject(text, user=None, context_type="slack_message"):
    """POST /feed/inject path — same pipeline, source 'manual'."""
    if _verify is None:
        return None
    return _push(text, "manual", user=user, context_type=context_type)


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


def recent_texts(limit=60) -> list:
    """Newest-first [(id, text, context_type)] for check items — the probes
    TribalSync uses to predict which verdicts a brain patch would flip."""
    with _lock:
        items = [i for i in _feed if i.get("kind", "check") == "check"]
    return [(i["id"], i["text"], i.get("context_type", "slack_message"))
            for i in items[::-1][:limit]]


def update_item(feed_id, res: dict) -> dict:
    """Overwrite a feed item's verdict fields from a fresh verify result —
    used after /feed/{id}/override learns a rule so the item visibly flips
    from CLEAN to caught."""
    with _lock:
        for i in _feed:
            if i["id"] == feed_id:
                for k in ("status", "risk_level", "violations",
                          "suggested_rewrite", "advisories", "actions", "meta"):
                    i[k] = res[k]
                item = dict(i)
                break
        else:
            return None
    _notify(item)
    return item


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
    flagged = critical = clean = questions = 0
    for i in items:
        if i.get("kind", "check") == "question":
            questions += 1
            continue
        if i["status"] == "VIOLATION_DETECTED":
            flagged += 1
        else:
            clean += 1
        if any(v.get("severity") == "CRITICAL" for v in i["violations"]):
            critical += 1
        for v in i["violations"]:
            by_category[v["category"]] = by_category.get(v["category"], 0) + 1
    return {"total": len(items), "flagged": flagged, "critical": critical,
            "clean": clean, "questions": questions,
            "by_category": by_category,
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
