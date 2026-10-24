"""Lightfern file bridge (owner: Riyansh).

When LIGHTFERN_APP_DIR points at the CommitGuard app folder inside a
Lightfern library, the backend mirrors state through plain files — a
Lightfern view's sandbox can't reach http://127.0.0.1, so FILES are the
API:

    <app>/brain/company_brain.json  exported brain (imported back on edits)
    <app>/brain/policies/*.md       one readable file per policy
    <app>/live/feed.json            last 100 checked messages (atomic write)
    <app>/live/status.json          bridge heartbeat, counters, errors
    <app>/live/answers/<id>.json    answers to inbox "ask" commands
    <app>/inbox/<ts>-<id>.json      commands written by the app view
    <app>/inbox/done/               processed commands (+ .result.json)

Commands run through the SAME functions the HTTP endpoints use — main
injects them via start(hooks=...): learn = POST /learn logic, override =
POST /feed/{id}/override logic, ask = POST /ask logic. A 1s daemon thread
drains inbox/, and watches brain/company_brain.json for edits made inside
Lightfern: a valid file is imported (atomically written back to
backend/company_brain.json), a bad one keeps the old brain and logs the
error into live/status.json.

With LIGHTFERN_APP_DIR unset every public function is a no-op and the
backend behaves exactly as before.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import rules
import slack_feed

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"

MAX_FEED_ENTRIES = 100
MAX_ERRORS = 10
TEXT_PREVIEW_CHARS = 800

log = logging.getLogger("commitguard.lightfern")

_lock = threading.Lock()
_enabled = False
_app_dir: Optional[Path] = None
_brain_path = BRAIN_PATH
_hooks: dict[str, Callable] = {}
_thread: Optional[threading.Thread] = None
_stop = threading.Event()
_started = False

_entries: list[dict] = []        # live/feed.json entries, newest first
_api_counter = 0
_exported_brain_hash: Optional[str] = None  # sha256 of our own last export
_brain_file_sig = None                      # (mtime_ns, size) last seen
_state = {
    "checks_total": 0,
    "last_check_ts": None,
    "inbox_processed": 0,
    "last_inbox_ts": None,
    "brain_exported_ts": None,
    "brain_imported_ts": None,
    "errors": [],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_ts() -> str:
    return _now().replace("+00:00", "Z")


# ---- filesystem helpers -----------------------------------------------------


def _atomic_write(path: Path, text: str) -> None:
    """tmp-file + os.replace so a reader never sees a torn write."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_json(path: Path, data) -> None:
    _atomic_write(path, json.dumps(data, indent=2))


def _err(msg: str) -> None:
    log.warning("lightfern bridge: %s", msg)
    with _lock:
        _state["errors"].append(f"{_utc_ts()} {msg}")
        del _state["errors"][:-MAX_ERRORS]


# ---- brain export -----------------------------------------------------------


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "policy"


def export_brain(app_dir: Optional[Path] = None,
                 brain_path: Optional[Path] = None,
                 brain: Optional[dict] = None) -> bool:
    """Write brain/company_brain.json + one md file per policy into the app
    folder. Returns True on success. The brain defaults to the backend file;
    pass `brain` explicitly to export a dict already in memory."""
    global _exported_brain_hash
    app_dir = Path(app_dir) if app_dir else _app_dir
    if app_dir is None:
        return False
    if brain is None:
        try:
            brain = json.loads(Path(brain_path or _brain_path).read_text())
        except Exception as e:
            _err(f"export: brain unreadable — {e}")
            return False
    if not isinstance(brain, dict) or not brain:
        _err("export: brain is empty or not an object")
        return False
    try:
        brain_dir = app_dir / "brain"
        policies_dir = brain_dir / "policies"
        policies_dir.mkdir(parents=True, exist_ok=True)

        text = json.dumps(brain, indent=2) + "\n"
        _atomic_write(brain_dir / "company_brain.json", text)
        _exported_brain_hash = hashlib.sha256(text.encode()).hexdigest()

        cards = rules.policy_cards(brain)
        wanted = set()
        for card in cards:
            name = _slug(card.get("title", "policy"))
            candidate, n = name, 2
            while f"{candidate}.md" in wanted:
                candidate, n = f"{name}-{n}", n + 1
            fname = f"{candidate}.md"
            wanted.add(fname)
            md = (f"# {card.get('title', 'Policy')}\n\n"
                  f"**Rule.** {card.get('rule', '')}\n\n"
                  f"**Brain key.** `{card.get('brain_key', '')}`\n\n"
                  f"**Example violation.** "
                  f"{card.get('example_violation', '')}\n\n"
                  "---\n_Generated from company_brain.json — "
                  "edit the brain, not this file._\n")
            _atomic_write(policies_dir / fname, md)
        for stale in policies_dir.glob("*.md"):
            if stale.name not in wanted:
                stale.unlink()
        with _lock:
            _state["brain_exported_ts"] = _utc_ts()
        return True
    except Exception as e:
        _err(f"export failed: {type(e).__name__}: {e}")
        return False


# ---- feed + status writes ---------------------------------------------------


def _write_feed() -> None:
    assert _app_dir is not None
    try:
        _write_json(_app_dir / "live" / "feed.json",
                    {"updated_at": _utc_ts(), "entries": _entries})
    except Exception as e:
        _err(f"feed write failed: {type(e).__name__}: {e}")


def _write_status() -> None:
    if _app_dir is None:
        return
    try:
        stats = {}
        try:
            stats = slack_feed.get_stats() or {}
        except Exception:
            pass
        payload = {
            "ts": _utc_ts(),
            "heartbeat_ts": _utc_ts(),  # re-written every ~1s while the
            #                          # bridge thread runs — the app view
            #                          # shows CONNECTED/STALE off this
            "live": True,
            "mode": slack_feed.MODE,
            "checks_total": _state["checks_total"],
            "last_check_ts": _state["last_check_ts"],
            "feed": {k: stats.get(k) for k in
                     ("total", "flagged", "clean", "critical", "questions",
                      "learned") if k in stats},
            "inbox_processed": _state["inbox_processed"],
            "last_inbox_ts": _state["last_inbox_ts"],
            "brain": {"exported_ts": _state["brain_exported_ts"],
                      "imported_ts": _state["brain_imported_ts"]},
            "errors": list(_state["errors"]),
            "sample_company_data": True,
        }
        _write_json(_app_dir / "live" / "status.json", payload)
    except Exception as e:
        log.warning("status write failed: %s", e)


def _upsert_entry(entry: dict) -> None:
    with _lock:
        for i, e in enumerate(_entries):
            if e["entry_id"] == entry["entry_id"]:
                _entries[i] = entry
                break
        else:
            _entries.insert(0, entry)
        del _entries[MAX_FEED_ENTRIES:]
        _state["checks_total"] += 1
        _state["last_check_ts"] = _utc_ts()
    _write_feed()
    _write_status()


def record_feed_item(item: dict) -> None:
    """slack_feed listener — every pushed feed item (check or question)
    mirrors into live/feed.json."""
    if not _enabled:
        return
    try:
        entry = {k: v for k, v in item.items() if k != "id"}
        entry["entry_id"] = f"feed-{item.get('id')}"
        entry["feed_id"] = item.get("id")
        if isinstance(entry.get("text"), str) and \
                len(entry["text"]) > TEXT_PREVIEW_CHARS:
            entry["text"] = entry["text"][:TEXT_PREVIEW_CHARS] + "…"
        _upsert_entry(entry)
    except Exception as e:
        _err(f"record_feed_item failed: {type(e).__name__}: {e}")


def record_api_check(text: str, context_type: str, result: dict) -> None:
    """Direct /verify-context + /verify-batch calls also land in feed.json."""
    global _api_counter
    if not _enabled or not isinstance(result, dict):
        return
    try:
        with _lock:
            _api_counter += 1
            n = _api_counter
        preview = text[:TEXT_PREVIEW_CHARS] + \
            ("…" if len(text) > TEXT_PREVIEW_CHARS else "")
        entry = {
            "entry_id": f"api-{n}",
            "feed_id": None,
            "kind": "check",
            "ts": _now(),
            "source": "api",
            "user": None,
            "context_type": context_type,
            "text": preview,
            "status": result.get("status"),
            "risk_level": result.get("risk_level"),
            "violations": result.get("violations") or [],
            "suggested_rewrite": result.get("suggested_rewrite"),
            "advisories": result.get("advisories") or [],
            "actions": result.get("actions") or [],
            "meta": result.get("meta") or {},
        }
        _upsert_entry(entry)
    except Exception as e:
        _err(f"record_api_check failed: {type(e).__name__}: {e}")


# ---- inbox commands ---------------------------------------------------------


def _err_text(err) -> str:
    """Extract {"error": ...} from an endpoint-style error (JSONResponse) or
    stringify anything else."""
    if err is None:
        return ""
    body = getattr(err, "body", None)
    try:
        if body is not None:
            return json.loads(body).get("error", str(err))
    except Exception:
        pass
    return str(err)


def _dispatch(cmd: dict) -> dict:
    """Run one inbox command through the injected endpoint functions.
    Returns the result dict persisted to inbox/done/<name>.result.json."""
    c = (cmd.get("cmd") or "").strip().lower()
    if c == "learn" or (c == "override"
                       and cmd.get("decision") == "missed"
                       and cmd.get("feed_id") is None):
        stored, err = _hooks["learn"](
            phrase=cmd.get("phrase"),
            category=cmd.get("category") or "LEARNED_RULE",
            severity=cmd.get("severity") or "HIGH",
            issue=cmd.get("issue"),
            correction=cmd.get("correction"),
            source_feed_id=cmd.get("feed_id"),
        )
        if err is not None:
            return {"ok": False, "cmd": c, "error": _err_text(err)}
        return {"ok": True, "cmd": "learn", "rule": stored}

    if c == "override":
        decision = (cmd.get("decision") or "").strip().lower()
        feed_id = cmd.get("feed_id")
        if feed_id is not None:
            payload, err = _hooks["override"](
                feed_id, decision,
                phrase=cmd.get("phrase"),
                note=cmd.get("note"),
                category=cmd.get("category"))
            if err is not None:
                return {"ok": False, "cmd": c, "error": _err_text(err)}
            _mark_overridden(feed_id, decision)
            return {"ok": True, "cmd": c, "result": payload}
        if decision == "false_positive":
            stored, err = _hooks["exception"](
                phrase=cmd.get("phrase"),
                category=cmd.get("category"),
                note=cmd.get("note"),
                source_feed_id=None)
            if err is not None:
                return {"ok": False, "cmd": c, "error": _err_text(err)}
            return {"ok": True, "cmd": c, "exception": stored}
        return {"ok": False, "cmd": c,
                "error": "decision must be 'missed' or 'false_positive'"}

    if c == "ask":
        q = (cmd.get("question") or "").strip()
        answer_id = str(cmd.get("id") or "ask-unknown")
        if not (3 <= len(q) <= 300):
            return {"ok": False, "cmd": c,
                    "error": "question must be 3-300 characters"}
        res = _hooks["ask"](q)
        doc = {"ok": True, "id": answer_id, "question": q, "ts": _utc_ts(),
               "answer": res.get("answer"), "sources": res.get("sources") or [],
               "matched": bool(res.get("matched")),
               "meta": res.get("meta") or {}}
        try:
            answers = _app_dir / "live" / "answers"
            answers.mkdir(parents=True, exist_ok=True)
            _write_json(answers / f"{answer_id}.json", doc)
        except Exception as e:
            return {"ok": False, "cmd": c,
                    "error": f"answer write failed: {e}"}
        return {"ok": True, "cmd": c, "answer_id": answer_id}

    return {"ok": False, "error": f"unknown cmd {c!r}"}


def _mark_overridden(feed_id, decision: str) -> None:
    with _lock:
        for e in _entries:
            if e.get("feed_id") == feed_id:
                e["overridden_by"] = decision
    _write_feed()


def _process_inbox() -> None:
    assert _app_dir is not None
    inbox = _app_dir / "inbox"
    done = inbox / "done"
    for f in sorted(inbox.glob("*.json")):
        try:
            cmd = json.loads(f.read_text())
            if not isinstance(cmd, dict):
                raise ValueError("command file must hold a JSON object")
        except Exception as e:
            result = {"ok": False, "error": f"unparseable command: {e}"}
            _finish_inbox(f, done, result)
            continue
        try:
            result = _dispatch(cmd)
        except Exception as e:
            result = {"ok": False,
                      "error": f"{type(e).__name__}: {e}"}
        _finish_inbox(f, done, result)
        if result.get("ok") and result.get("cmd") != "ask":
            # learned rules / exceptions change the brain → re-export so the
            # change shows up inside Lightfern
            export_brain()
        with _lock:
            _state["inbox_processed"] += 1
            _state["last_inbox_ts"] = _utc_ts()


def _finish_inbox(src: Path, done: Path, result: dict) -> None:
    try:
        done.mkdir(parents=True, exist_ok=True)
        result = {**result, "processed_ts": _utc_ts(), "file": src.name}
        _write_json(done / f"{src.name}.result.json", result)
        os.replace(src, done / src.name)
    except Exception as e:
        _err(f"inbox cleanup failed for {src.name}: {e}")


# ---- brain import (edits made inside Lightfern) -----------------------------


def _check_brain_import() -> None:
    """If the app's brain/company_brain.json changed on disk since our last
    export, validate and import it; keep the old brain + log on bad JSON."""
    global _brain_file_sig
    assert _app_dir is not None
    path = _app_dir / "brain" / "company_brain.json"
    try:
        st = path.stat()
    except OSError:
        return
    sig = (st.st_mtime_ns, st.st_size)
    if sig == _brain_file_sig:
        return
    _brain_file_sig = sig
    try:
        text = path.read_text()
    except OSError:
        return
    if hashlib.sha256(text.encode()).hexdigest() == _exported_brain_hash:
        return  # our own export writing back — not a user edit
    try:
        brain = json.loads(text)
        if not isinstance(brain, dict) or not brain:
            raise ValueError("brain must be a non-empty JSON object")
    except Exception as e:
        _err(f"brain import rejected (kept old brain): {e}")
        return
    try:
        _hooks["import_brain"](brain)
    except Exception as e:
        _err(f"brain import failed: {type(e).__name__}: {e}")
        return
    with _lock:
        _state["brain_imported_ts"] = _utc_ts()
    log.warning("lightfern bridge: imported brain edited inside Lightfern")
    export_brain(brain=brain)  # refresh policies md for the new content


# ---- lifecycle --------------------------------------------------------------


def _tick() -> None:
    _process_inbox()
    _check_brain_import()
    _write_status()


def _loop() -> None:
    while not _stop.is_set():
        try:
            _tick()
        except Exception as e:
            _err(f"tick failed: {type(e).__name__}: {e}")
        _stop.wait(1.0)


def start(hooks: Optional[dict] = None,
          app_dir: Optional[str] = None,
          brain_path: Optional[Path] = None) -> bool:
    """Enable the bridge. Returns True when it actually started — False when
    LIGHTFERN_APP_DIR is unset and no app_dir was passed (default no-op)."""
    global _enabled, _app_dir, _hooks, _brain_path, _thread, _started
    global _brain_file_sig
    if _started:
        return _enabled
    raw = app_dir or os.environ.get("LIGHTFERN_APP_DIR")
    if not raw:
        return False
    app = Path(raw).expanduser().resolve()
    try:
        for sub in ("brain/policies", "live/answers", "inbox/done"):
            (app / sub).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        _err(f"cannot create app folders under {app}: {e}")
        return False

    _app_dir = app
    _brain_path = Path(brain_path) if brain_path else BRAIN_PATH
    _hooks = hooks or {}
    with _lock:
        _entries.clear()
        _state.update({
            "checks_total": 0, "last_check_ts": None,
            "inbox_processed": 0, "last_inbox_ts": None,
            "brain_exported_ts": None, "brain_imported_ts": None,
            "errors": [],
        })
        global _api_counter
        _api_counter = 0

    def _missing(name):
        return lambda *a, **k: (None, f"hook '{name}' not wired")

    for name in ("learn", "exception", "override"):
        _hooks.setdefault(name, _missing(name))
    _hooks.setdefault("ask", lambda q: {
        "answer": "bridge running without an ask hook", "sources": [],
        "matched": False, "meta": {}})
    _hooks.setdefault("import_brain", lambda b: None)

    export_brain()
    try:
        feed_path = app / "live" / "feed.json"
        existing = json.loads(feed_path.read_text()) if feed_path.exists() \
            else {}
        if isinstance(existing.get("entries"), list):
            with _lock:
                _entries.extend(
                    e for e in existing["entries"]
                    if isinstance(e, dict) and e.get("entry_id"))
                del _entries[MAX_FEED_ENTRIES:]
    except Exception:
        pass
    _write_feed()
    _write_status()
    try:
        st = (app / "brain" / "company_brain.json").stat()
        _brain_file_sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        _brain_file_sig = None

    slack_feed.add_feed_listener(record_feed_item)

    _enabled = True
    _started = True
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True,
                               name="cg-lightfern-bridge")
    _thread.start()
    log.warning("lightfern bridge: app_dir=%s", app)
    return True


def stop() -> None:
    """Stop the thread and detach listeners. Bridge state stays for the
    next start() (tests re-start with fresh dirs)."""
    global _enabled, _started
    _enabled = False
    _started = False
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=3)
    slack_feed.remove_feed_listener(record_feed_item)


def status() -> dict:
    """GET /lightfern/status payload."""
    with _lock:
        errors = list(_state["errors"])
        out = {
            "enabled": _enabled,
            "app_dir": str(_app_dir) if _app_dir else None,
            "last_export": _state["brain_exported_ts"],
            "last_inbox": _state["last_inbox_ts"],
            "checks_total": _state["checks_total"],
            "inbox_processed": _state["inbox_processed"],
            "brain_imported_ts": _state["brain_imported_ts"],
            "feed_entries": len(_entries),
            "errors": errors,
        }
    return out
