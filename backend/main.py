import json
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import rules
import actions
import slack_feed
import tribal_sync
import brain_store
import audit_trace
import lightfern_bridge
import chaser
import treasury
import close
from llm_enrich import llm_enrich, llm_enabled, llm_polish_answer

from rules import explain_policy, policy_cards

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"

PREVIEW_DIR = BASE / ".lightfern_preview"


@asynccontextmanager
async def lifespan(_app):
    hooks = {
        "learn": _learn,
        "exception": _learn_exception,
        "override": _apply_override,
        "ask": _ask_brain,
        "import_brain": _import_brain,
    }
    if not lightfern_bridge.start(hooks=hooks):
        # LIGHTFERN_APP_DIR unset — run the same bridge against a gitignored
        # runtime copy so the /lightfern browser preview shows real live
        # data (feed.json, status.json, inbox commands + answers).
        try:
            PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
            lightfern_bridge.start(hooks=hooks, app_dir=str(PREVIEW_DIR))
        except Exception:
            pass
    slack_feed.start(verify_fn=_verify, scenarios=SCENARIOS,
                     ask_fn=_ask_brain, override_fn=_slack_override,
                     decision_fn=_decision_for_item,
                     proposal_fn=_proposal_decision,
                     chase_fn=_chase_draft, chase_command_fn=_chase_cmd)
    slack_feed.add_feed_listener(_chase_signal)
    slack_feed.add_feed_listener(_treasury_signal)
    yield
    lightfern_bridge.stop()


app = FastAPI(title="CommitGuard", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/vendor", StaticFiles(directory=BASE.parent / "demo" / "vendor"), name="vendor")


@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        content = {"error": "request failed", **exc.detail}
    else:
        content = {"error": str(exc.detail), "detail": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=content,
                        headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError):
    return JSONResponse(status_code=422,
                        content={"error": "invalid request", "detail": exc.errors()})


def load_brain():
    try:
        return json.loads(BRAIN_PATH.read_text())
    except Exception:
        return {}


COMPANY_BRAIN = load_brain()


class VerifyRequest(BaseModel):
    text: str
    context_type: str = "outgoing_email"
    recipient: Optional[str] = None


class VerifyBatchRequest(BaseModel):
    items: List[VerifyRequest] = []


class ActionRequest(BaseModel):
    action_type: str
    payload: dict = {}


class InjectRequest(BaseModel):
    text: str
    user: Optional[str] = None
    context_type: Optional[str] = None


class AskRequest(BaseModel):
    question: str


class LearnRequest(BaseModel):
    phrase: str
    category: str = "LEARNED_RULE"
    severity: str = "HIGH"
    issue: Optional[str] = None
    correction: Optional[str] = None
    source_feed_id: Optional[int] = None


class OverrideRequest(BaseModel):
    decision: str
    phrase: Optional[str] = None
    note: Optional[str] = None
    category: Optional[str] = None


VALID_CONTEXT_TYPES = {"outgoing_email", "slack_message", "incoming_invoice", "general"}


def _validate(text: str, context_type: str):
    if not text or not text.strip():
        return JSONResponse(status_code=422, content={"error": "text must be non-empty"})
    if context_type not in VALID_CONTEXT_TYPES:
        return JSONResponse(status_code=422, content={
            "error": f"context_type must be one of {sorted(VALID_CONTEXT_TYPES)}"})
    return None


SCENARIOS_PATH = BASE / "scenarios.json"
SCENARIOS = json.loads(SCENARIOS_PATH.read_text()) if SCENARIOS_PATH.exists() else {}


def _verify(text: str, context_type: str) -> dict:
    t0 = time.time()
    brain = COMPANY_BRAIN  # one snapshot — a reload mid-verify stays coherent
    tr = time.time()
    violations = rules.run_rules(text, brain, context_type)
    audit_ran = context_type == "incoming_invoice"
    try:
        audit_added = audit_trace.audit_violations(text, brain,
                                                   context_type, violations)
        violations += audit_added
        audit_ran = audit_ran or any(
            v.get("category") in audit_trace.CATEGORIES
            for v in audit_added)
    except Exception:
        pass  # audit is additive — never let it take down /verify
    violations = rules._apply_exceptions(text, violations, brain)
    rules_ms = round((time.time() - tr) * 1000, 2)
    engine = "rules"
    advisories = []
    full_rewrite = None

    llm = llm_enrich(text, context_type, violations, brain)
    if llm:
        engine = "rules+llm"
        advisories = llm.get("violations", [])
        full_rewrite = llm.get("full_rewrite")

    status = "VIOLATION_DETECTED" if violations else "CLEAN"
    if status == "CLEAN":
        suggested_rewrite = None
    elif isinstance(full_rewrite, str) and full_rewrite.strip():
        suggested_rewrite = full_rewrite
    else:
        suggested_rewrite = rules.apply_fixes(text, violations)
    result = {
        "status": status,
        "risk_level": rules.risk_level(violations),
        "violations": violations,
        "advisories": advisories,
        "suggested_rewrite": suggested_rewrite,
        "meta": {
            "engine": engine,
            "checks_run": len(rules.ALL_CHECKS) +
            (audit_trace.CHECK_COUNT if audit_ran else 0),
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "rules_ms": rules_ms,
        },
    }
    result["actions"] = actions.plan_actions(result, brain, text=text)
    return result


def _on_brain_change(brain_key, old, new, meta):
    """brain_store on_change: reload the in-memory brain and re-verify any
    feed items a patch was predicted to flip, so their verdicts visibly
    change in /feed (the 'self-healing brain' demo beat)."""
    global COMPANY_BRAIN
    fresh = load_brain()
    if fresh:
        COMPANY_BRAIN = fresh
    for fid in (meta or {}).get("affected_feed_ids") or []:
        try:
            it = slack_feed.get_item(fid)
            if it and it.get("kind", "check") == "check":
                slack_feed.update_item(
                    fid, _verify(it["text"],
                                 it.get("context_type", "slack_message")))
        except Exception:
            continue


brain_store.register_on_change(_on_brain_change)


def _decision_for_item(item):
    """slack_feed decision_fn: run TribalSync detection on a checked feed
    item; recent feed texts are the probes used to predict which verdicts
    the patch would flip. Fail open — detection never breaks the feed."""
    try:
        if item.get("kind") != "check":
            return None
        probes = slack_feed.recent_texts(limit=60)
        return tribal_sync.build_proposal(
            item.get("text", ""), COMPANY_BRAIN,
            meta={"feed_id": item.get("id"), "author": item.get("user"),
                  "ts": item.get("ts"), "source": item.get("source"),
                  "context_type": item.get("context_type")},
            probes=probes)
    except Exception:
        return None


def _proposal_decision(proposal_id, action, user):
    """slack_feed proposal_fn: 'apply'/'reject' thread commands — same
    logic as the HTTP endpoints. Returns (payload, error_message)."""
    try:
        if action == "apply":
            return tribal_sync.apply_proposal(
                proposal_id, decided_by=user or "slack"), None
        return tribal_sync.reject_proposal(
            proposal_id, decided_by=user or "slack"), None
    except Exception as e:
        return None, str(e)


@app.post("/verify-context",
          summary="Check a draft or invoice against the company brain",
          description="Runs the deterministic rules engine (plus the optional LLM "
                      "enrichment stage) over a drafted email, Slack message, or "
                      "incoming invoice. Returns violations with brain-key evidence, "
                      "inline span locations, and a one-click suggested rewrite.")
def verify_context(req: VerifyRequest):
    err = _validate(req.text, req.context_type)
    if err:
        return err
    result = _verify(req.text, req.context_type)
    lightfern_bridge.record_api_check(req.text, req.context_type, result)
    return result


@app.post("/verify-batch",
          summary="Check multiple drafts or invoices in one call",
          description="Batch version of /verify-context: every item is validated and "
                      "checked independently, and the response is one identical "
                      "verify-context result object per item, in order.")
def verify_batch(req: VerifyBatchRequest):
    if not req.items:
        return JSONResponse(status_code=422, content={"error": "items must be a non-empty list"})
    for it in req.items:
        err = _validate(it.text, it.context_type)
        if err:
            return err
    results = []
    for it in req.items:
        res = _verify(it.text, it.context_type)
        lightfern_bridge.record_api_check(it.text, it.context_type, res)
        results.append(res)
    return {"results": results}


_OWES_RE = re.compile(
    r"(?i)\b(who\s+owes|owe[sd]?\s+us|owed|what'?s\s+overdue|whats\s+overdue|"
    r"overdue\s+receiv|receivables?|outstanding\s+(invoices?|money)|"
    r"who\s+hasn'?t\s+paid|haven'?t\s+paid)\b")

_TREASURY_RE = re.compile(
    r"(?i)\b(ready\s+to\s+pay|payment\s+queue|treasury\s+queue|"
    r"round\s+treasury|what'?s\s+payable|payments?\s+(queued|pending|"
    r"waiting|held))\b")


def _ask_brain(question: str) -> dict:
    """Shared ask-the-brain logic for POST /ask and Slack questions.
    Deterministic first; if OPENAI_API_KEY is set the answer is rephrased
    in friendlier words (sources untouched), failing open.

    Receivables questions ('who owes us money', 'what's overdue') are
    answered by the chaser's ageing summary — same response shape.
    'What's ready to pay' is answered by the Round Treasury queue."""
    t0 = time.time()
    if _OWES_RE.search(question or ""):
        out = chaser.ask_summary(COMPANY_BRAIN)
    elif _TREASURY_RE.search(question or ""):
        out = treasury.ask_summary(COMPANY_BRAIN)
    else:
        out = (close.ask(question, COMPANY_BRAIN)
               or explain_policy(question, COMPANY_BRAIN))
    engine = "rules"
    if out.get("matched"):
        polished = llm_polish_answer(question, out["answer"])
        if polished:
            out = {**out, "answer": polished}
            engine = "rules+llm"
    return {**out,
            "meta": {"engine": engine,
                     "latency_ms": round((time.time() - t0) * 1000, 1)}}


@app.post("/ask",
          summary="Ask the company brain a question (the onboarding test)",
          description="A new hire asks 'what are the rules?' in plain English "
                      "and gets a sourced answer: every reply cites the "
                      "brain keys it came from. matched=false means the brain "
                      "doesn't cover it yet — a human can teach it via /learn.")
def ask(req: AskRequest):
    q = (req.question or "").strip()
    if not (3 <= len(q) <= 300):
        return JSONResponse(
            status_code=422,
            content={"error": "question must be 3-300 characters"})
    return _ask_brain(q)


@app.get("/brain/policies",
         summary="Policy cards generated from the brain",
         description="One card per policy family — title, rule text, the "
                     "brain_key it cites, and an example violation. Powers "
                     "the dashboard's brain panel.")
def brain_policies():
    return policy_cards(COMPANY_BRAIN)


@app.post("/execute-action",
          summary="Apply fixes, stage invoices, escalate fraud, log overrides",
          description="SEND_APPROVED, APPLY_REWRITE_AND_LOG, APPROVE_OVERRIDE "
                      "(requires payload.reason), STAGE_INVOICE (appends to "
                      "round_staging_queue.json for Round Treasury pickup), and "
                      "ESCALATE_FRAUD. Every action appends to audit_log.jsonl.")
def execute_action(req: ActionRequest):
    return actions.execute_action(req.action_type, req.payload, COMPANY_BRAIN)


@app.get("/brain",
         summary="Read the live company brain",
         description="Returns the in-memory company_brain.json: financial rules, "
                     "signed contracts, engineering status, and people.")
def get_brain():
    return COMPANY_BRAIN


@app.post("/brain/reload",
          summary="Reload the company brain from disk",
          description="Re-reads company_brain.json without a restart — edit the file "
                      "and enforcement updates instantly. A 422 keeps the old brain.")
def reload_brain():
    global COMPANY_BRAIN
    try:
        fresh = load_brain()
    except Exception as e:
        raise HTTPException(422, {"reloaded": False, "error": str(e)})
    if not fresh:
        raise HTTPException(422, {"reloaded": False, "error": "company_brain.json empty or malformed"})
    COMPANY_BRAIN = fresh
    return {"reloaded": True, "keys": list(COMPANY_BRAIN.keys())}


@app.get("/brain/proposals",
         summary="List brain-patch proposals (TribalSync)",
         description="Newest-first proposals detected from authoritative feed "
                     "decisions. ?status=pending|applied|rejected filters; no "
                     "param returns all. Never auto-applied.")
def brain_proposals(status: Optional[str] = None):
    if status is not None and status not in {"pending", "applied", "rejected"}:
        return JSONResponse(status_code=422, content={
            "error": "status must be pending|applied|rejected"})
    return tribal_sync.list_proposals(status=status)


@app.get("/brain/changelog",
         summary="Applied brain patches, newest first",
         description="The brain_store changelog — every TribalSync proposal "
                     "patch applied to company_brain.json, with before/after "
                     "values and citation.")
def brain_changelog(limit: int = 50):
    return brain_store.changelog(limit=limit)


@app.get("/brain/proposals/{pid}", summary="One brain-patch proposal")
def brain_proposal(pid: str):
    prop = tribal_sync.get_proposal(pid)
    if prop is None:
        raise HTTPException(404, {"error": f"proposal {pid} not found"})
    return prop


@app.post("/brain/proposals/{pid}/apply",
          summary="Apply a brain patch (human approval)",
          description="Writes the patch through brain_store (atomic write + "
                      "changelog + on_change hooks), reloads the brain, and "
                      "re-verifies the proposal's affected feed items.")
def brain_proposal_apply(pid: str):
    if tribal_sync.get_proposal(pid) is None:
        raise HTTPException(404, {"error": f"proposal {pid} not found"})
    try:
        return tribal_sync.apply_proposal(pid, decided_by="http")
    except (ValueError, KeyError) as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


@app.post("/brain/proposals/{pid}/reject", summary="Reject a brain patch")
def brain_proposal_reject(pid: str):
    if tribal_sync.get_proposal(pid) is None:
        raise HTTPException(404, {"error": f"proposal {pid} not found"})
    try:
        return tribal_sync.reject_proposal(pid, decided_by="http")
    except (ValueError, KeyError) as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


LEARN_SEVERITIES = {"MEDIUM", "HIGH", "CRITICAL"}


def _learn(phrase, category, severity, issue, correction, source_feed_id):
    """Shared /learn logic. Returns (stored_rule, error_response)."""
    phrase = (phrase or "").strip()
    if not (3 <= len(phrase) <= 120):
        return None, JSONResponse(
            status_code=422,
            content={"error": "phrase is required and must be 3-120 chars"})
    sev = (severity or "HIGH").strip().upper()
    if sev not in LEARN_SEVERITIES:
        return None, JSONResponse(
            status_code=422,
            content={"error": f"severity must be one of {sorted(LEARN_SEVERITIES)}"})
    cat = (category or "LEARNED_RULE").strip().upper()
    if not cat:
        return None, JSONResponse(status_code=422,
                                  content={"error": "category must be non-empty"})
    stored = rules.add_learned_rule({
        "phrase": phrase,
        "category": cat,
        "severity": sev,
        "issue": (issue or "").strip() or
                 f"Learned rule: '{phrase}' was flagged by a human reviewer.",
        "correction": (correction or "").strip() or
                      f"Remove or rephrase '{phrase}', or get explicit approval.",
        "source_feed_id": source_feed_id,
    })
    global COMPANY_BRAIN
    new_brain = load_brain()
    if new_brain:
        COMPANY_BRAIN = new_brain
    return stored, None


def _learn_exception(phrase, category, note=None, source_feed_id=None):
    """Shared learned-exception logic — used by _apply_override and by the
    Lightfern bridge for 'fine' commands on entries with no feed id.
    Returns (stored_exception, error_response)."""
    try:
        stored = rules.add_learned_exception({
            "phrase": phrase, "category": category, "note": note,
            "source_feed_id": source_feed_id})
    except ValueError as e:
        return None, JSONResponse(status_code=422,
                                  content={"error": str(e)})
    global COMPANY_BRAIN
    new_brain = load_brain()
    if new_brain:
        COMPANY_BRAIN = new_brain
    return stored, None


def _import_brain(brain: dict) -> None:
    """Swap the whole brain for a dict edited inside Lightfern: atomic write
    to company_brain.json, then in-memory swap. The bridge validates the
    shape before calling this."""
    global COMPANY_BRAIN
    rules._write_brain(brain, BRAIN_PATH)
    COMPANY_BRAIN = brain


@app.post("/learn",
          summary="Teach the engine a new rule from a human correction",
          description="Stores {phrase, category, severity, issue, correction} in "
                      "brain.learned_rules (deduped on lower-cased phrase), reloads "
                      "the in-memory brain, and returns the stored rule. From the "
                      "next request on, any message containing the phrase is "
                      "flagged — this is the 'learns and updates itself' path.")
def learn(req: LearnRequest):
    stored, err = _learn(req.phrase, req.category, req.severity,
                         req.issue, req.correction, req.source_feed_id)
    if err:
        return err
    return JSONResponse(status_code=201, content=stored)


@app.get("/brain/learned",
         summary="List learned rules and exceptions, newest first",
         description="Returns {rules, exceptions} — brain.learned_rules "
                     "(taught via /learn or override 'missed') and "
                     "brain.learned_exceptions (override 'false_positive'), "
                     "each newest first.")
def brain_learned():
    return {"rules": list(reversed(COMPANY_BRAIN.get("learned_rules", []))),
            "exceptions": list(reversed(
                COMPANY_BRAIN.get("learned_exceptions", [])))}


@app.get("/brain/learned/rules",
         summary="List learned rules only (legacy shape)",
         description="The pre-/brain/learned shape: a plain array of "
                     "brain.learned_rules, newest first.")
def brain_learned_rules():
    return list(reversed(COMPANY_BRAIN.get("learned_rules", [])))


@app.get("/audit-log",
         summary="Read the audit trail, newest first",
         description="Returns entries from audit_log.jsonl, newest first. Optional "
                     "?type=<action_type> and ?result=<result> filters are forwarded "
                     "to actions.read_audit when supported.")
def audit_log(limit: int = 20, result: Optional[str] = None,
              type_: Optional[str] = Query(None, alias="type")):
    try:
        return actions.read_audit(limit, type=type_, result=result)
    except TypeError:
        return actions.read_audit(limit)


@app.get("/scenarios",
         summary="List the canned demo scenarios",
         description="Returns backend/scenarios.json — the demo texts behind the "
                     "UI's scenario buttons (sales_email, vendor_invoice, "
                     "support_reply, clean_email).")
def scenarios():
    return SCENARIOS


@app.get("/feed",
         summary="Live feed of checked messages, newest first",
         description="Every message the monitor has checked — real Slack "
                     "messages (source=slack), offline scenario replays "
                     "(source=simulated), or manual injections (source=manual). "
                     "?since=<id> returns only items newer than that id; "
                     "?limit caps the page (default 50).")
def feed(since: Optional[int] = None, limit: int = 50):
    return slack_feed.get_feed(since=since, limit=limit)


@app.get("/feed/stats",
         summary="Aggregate stats over the live feed",
         description="{total, flagged, critical, clean, by_category, last_ts, "
                     "mode: 'slack' | 'simulated'} — the dashboard's counter strip.")
def feed_stats():
    return slack_feed.get_stats()


@app.post("/feed/inject",
          summary="Push a message through the pipeline manually",
          description="Runs {text} through the same verify path as "
                      "/verify-context with context_type 'slack_message', "
                      "records it as a feed item with source 'manual', and "
                      "returns the item. For testing and the live demo.")
def feed_inject(req: InjectRequest):
    if not req.text or not req.text.strip():
        return JSONResponse(status_code=422, content={"error": "text must be non-empty"})
    if req.context_type is not None and req.context_type not in VALID_CONTEXT_TYPES:
        return JSONResponse(status_code=422, content={
            "error": f"context_type must be one of {sorted(VALID_CONTEXT_TYPES)}"})
    item = slack_feed.inject(req.text, user=req.user,
                             context_type=req.context_type or "slack_message")
    if item is None:
        return JSONResponse(status_code=503, content={"error": "feed pipeline not started"})
    return item


def _apply_override(feed_id, decision, phrase=None, note=None, category=None):
    """Shared override logic for POST /feed/{id}/override and Slack thread
    commands. Returns (payload, error_response)."""
    global COMPANY_BRAIN
    item = slack_feed.get_item(feed_id)
    if item is None:
        return None, JSONResponse(
            status_code=404,
            content={"error": f"feed item {feed_id} not found"})
    violations = item.get("violations") or []
    rule = exception = recheck = used_phrase = None
    if decision == "missed":
        if not phrase or not phrase.strip():
            return None, JSONResponse(status_code=422, content={
                "error": "phrase is required when decision is 'missed'"})
        rule, err = _learn(phrase, "LEARNED_RULE", "HIGH", None, None, feed_id)
        if err:
            return None, err
        used_phrase = phrase
    elif decision == "false_positive":
        cat = (category or "").strip().upper() or \
              (violations[0].get("category") if violations else None)
        if not cat:
            return None, JSONResponse(status_code=422, content={
                "error": "category is required — item has no violations "
                         "to infer one from"})
        ph = (phrase or "").strip()
        if not ph:
            hit = next((v for v in violations
                        if v.get("category") == cat
                        and (v.get("span") or {}).get("text")), None) or \
                  next((v for v in violations
                        if (v.get("span") or {}).get("text")), None)
            ph = ((hit or {}).get("span") or {}).get("text") or ""
        if not ph:
            return None, JSONResponse(status_code=422, content={
                "error": "phrase is required — item violations have no "
                         "span text to default to"})
        exception, err = _learn_exception(ph, cat, note=note,
                                          source_feed_id=feed_id)
        if err:
            return None, err
        used_phrase = ph
    if decision in ("missed", "false_positive"):
        recheck = _verify(item["text"], item.get("context_type", "slack_message"))
        slack_feed.update_item(feed_id, recheck)
    override = slack_feed.record_override(
        feed_id, decision, phrase=used_phrase or phrase, note=note,
        rule_id=(rule or exception or {}).get("id"))
    return {"override": override, "rule": rule,
            "exception": exception, "recheck": recheck}, None


def _slack_override(feed_id, decision, phrase=None):
    """slack_feed's thread-command hook ('missed: <phrase>' / 'fine') — same
    logic as the HTTP override without the HTTP layer. Returns
    (payload, error_message)."""
    payload, err = _apply_override(feed_id, decision, phrase=phrase)
    if err is not None:
        try:
            msg = json.loads(err.body).get("error", "override failed")
        except Exception:
            msg = "override failed"
        return None, msg
    return payload, None


@app.post("/feed/{feed_id}/override",
          summary="Human verdict: 'missed' teaches a rule, 'false_positive' "
                  "an exception",
          description="decision='missed' requires phrase: it learns a rule "
                      "(same as POST /learn with source_feed_id=id), re-runs the "
                      "item's text, and flips the stored item to its new verdict — "
                      "the UI can show it go CLEAN -> caught. "
                      "decision='false_positive' learns an exception via "
                      "rules.add_learned_exception: category defaults to the "
                      "item's first violation category, phrase to that "
                      "violation's span text; the recheck drops the suppressed "
                      "category. Either way an override record is appended to "
                      "feed_log.jsonl and returned as 'override'.")
def feed_override(feed_id: int, req: OverrideRequest):
    decision = (req.decision or "").strip().lower()
    if decision not in {"missed", "false_positive"}:
        return JSONResponse(status_code=422, content={
            "error": "decision must be 'missed' or 'false_positive'"})
    payload, err = _apply_override(feed_id, decision, phrase=req.phrase,
                                   note=req.note, category=req.category)
    if err:
        return err
    return payload


@app.get("/lightfern/status",
         summary="Lightfern file-bridge status",
         description="Returns {enabled, app_dir, last_export, last_inbox, "
                     "checks_total, inbox_processed, feed_entries, errors}. "
                     "enabled=false when LIGHTFERN_APP_DIR is unset — the "
                     "backend then behaves exactly as without the bridge.")
def lightfern_status():
    return lightfern_bridge.status()


# ---- Lightfern browser preview ---------------------------------------------
# The desktop app's home.tsx runs unchanged in a browser: the host shim calls
# these endpoints instead of the Lightfern sandbox file API. All file access
# is confined to the bridge's app dir (LIGHTFERN_APP_DIR, else the gitignored
# backend/.lightfern_preview/ started in lifespan).

LF_APP_SRC = BASE.parent / "lightfern" / "CommitGuard Brain"


def _lf_root() -> Path:
    st = lightfern_bridge.status()
    if not st.get("enabled") or not st.get("app_dir"):
        raise HTTPException(404, {"error": "lightfern preview not enabled"})
    return Path(st["app_dir"]).resolve()


def _lf_resolve(rel: str) -> Path:
    """Resolve rel inside the app dir; 400 on absolute paths / '..'
    traversal, resolved-path check catches symlink escapes."""
    root = _lf_root()
    if not rel or rel.startswith("/") or rel.startswith("\\"):
        raise HTTPException(400, {"error": "path must be relative"})
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if any(p == ".." for p in parts):
        raise HTTPException(400, {"error": "path traversal rejected"})
    dest = (root.joinpath(*parts)).resolve()
    if root != dest and root not in dest.parents:
        raise HTTPException(400, {"error": "path escapes app dir"})
    return dest


@app.get("/lightfern",
         summary="Lightfern app — browser preview",
         description="Serves demo/lightfern.html: the real home.tsx bundled "
                     "for the browser, talking to this backend via the "
                     "/lightfern/files proxy instead of the desktop sandbox.")
def lightfern_preview():
    path = BASE.parent / "demo" / "lightfern.html"
    if not path.exists():
        raise HTTPException(404, {"error": "lightfern.html not found"})
    return FileResponse(path)


@app.get("/lightfern/bundle.js", include_in_schema=False)
def lightfern_bundle():
    path = BASE.parent / "demo" / "lightfern-bundle.js"
    if not path.exists():
        raise HTTPException(404, {"error": "bundle not built — run "
                                "lightfern/dev/harness/build-preview.mjs"})
    return FileResponse(path, media_type="text/javascript")


@app.get("/lightfern/styles.css", include_in_schema=False)
def lightfern_styles():
    path = LF_APP_SRC / "code" / "styles.css"
    if not path.exists():
        raise HTTPException(404, {"error": "styles.css not found"})
    return FileResponse(path)


@app.get("/lightfern/files/{path:path}",
         summary="Read a file (or list a dir with ?list=1) in the app dir",
         description="ctx.files.read/list backing for the browser preview. "
                     "Confined to the bridge app dir — '..' and absolute "
                     "paths return 400.")
def lightfern_file_read(path: str, list: bool = False):
    dest = _lf_resolve(path)
    if list or dest.is_dir():
        if not dest.is_dir():
            raise HTTPException(404, {"error": f"no such dir: {path}"})
        entries = [
            {"path": f"{path.strip('/')}/{c.name}" if path.strip("/")
                     else c.name,
             "name": c.name,
             "kind": "folder" if c.is_dir() else "file"}
            for c in sorted(dest.iterdir(), key=lambda c: c.name)
            if not c.name.startswith(".")
        ]
        return entries
    if not dest.is_file():
        raise HTTPException(404, {"error": f"no such file: {path}"})
    return PlainTextResponse(dest.read_text(errors="replace"))


class _FileWrite(BaseModel):
    content: str


@app.post("/lightfern/files/{path:path}",
          summary="Write a file inside the app dir",
          description="ctx.files.write backing for the browser preview — "
                      "inbox command files land here and the bridge drains "
                      "them exactly like in the desktop app.")
def lightfern_file_write(path: str, req: _FileWrite):
    dest = _lf_resolve(path)
    if dest.is_dir():
        raise HTTPException(400, {"error": f"is a directory: {path}"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(req.content)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"ok": True, "path": path}


@app.get("/slack/status",
         summary="Slack monitor mode and health",
         description="Returns {mode: 'slack' | 'simulated', channel, "
                     "token: 'set' | 'missing' (the value is never exposed), "
                     "reply_enabled, last_poll_ts, last_error}.")
def slack_status():
    return slack_feed.slack_status()


@app.get("/health",
         summary="Liveness and engine status",
         description="Returns {ok, engine: 'rules' | 'rules+llm', checks, brain_keys, "
                     "feed: {mode, channel, last_poll_ts, error?}}. "
                     "Works fully with OPENAI_API_KEY unset.")
def health():
    return {"ok": True, "engine": "rules+llm" if llm_enabled() else "rules",
            "checks": len(rules.ALL_CHECKS), "brain_keys": list(COMPANY_BRAIN.keys()),
            "feed": slack_feed.health_info()}


@app.get("/inspector.html",
         summary="Compliance console UI",
         description="Serves demo/inspector.html — live brain, audit trail, and "
                     "health inspector.")
def inspector():
    path = BASE.parent / "demo" / "inspector.html"
    if not path.exists():
        raise HTTPException(404, {"error": "inspector.html not built yet"})
    return FileResponse(path)


# ---- invoice chaser (receivables) -------------------------------------------


def _chase_draft(ref: str) -> dict:
    """Shared draft logic for POST /chase and the Slack 'chase X' command.
    The draft cites invoice/amount/due date/days overdue + prior promises;
    context comes from the live feed. DRAFT ONLY — nothing is sent."""
    return chaser.draft_chase(COMPANY_BRAIN, ref,
                              feed_items=slack_feed.get_feed(limit=200))


def _chase_cmd(ref, cmd):
    """slack_feed thread-command hook for chase drafts ('log'/'paid').
    Returns (payload, error_message) like _slack_override."""
    global COMPANY_BRAIN
    if not ref:
        return None, "no invoice on this chase thread"
    try:
        if cmd == "paid":
            res = chaser.mark_paid(ref, note="marked paid from Slack thread")
        else:
            res = chaser.log_chase(ref, channel="slack")
    except Exception as e:
        return None, str(e)
    if res is None:
        return None, f"no open receivable matching '{ref}'"
    _reload_brain_after_chase()
    if cmd == "paid":
        return {"kind": "paid", "invoice_id": res["invoice_id"]}, None
    return {"kind": "log", "invoice_id": ref, "entry": res}, None


def _chase_signal(item: dict) -> None:
    """Feed listener — 'Acme paid INV-1043' / 'Acme will pay Friday' style
    messages update the receivable in the brain (atomic write)."""
    global COMPANY_BRAIN
    try:
        updates = chaser.record_signal(COMPANY_BRAIN, item.get("text") or "",
                                       source=item.get("source") or "feed",
                                       brain_path=BRAIN_PATH)
        if updates:
            new_brain = load_brain()
            if new_brain:
                COMPANY_BRAIN = new_brain
            lightfern_bridge.export_brain(brain=COMPANY_BRAIN)
    except Exception:
        pass


def _treasury_signal(item: dict) -> None:
    """Feed listener — checked incoming invoices land in the Round Treasury
    queue (ready to stage vs held). Fail-open like every listener."""
    try:
        treasury.ingest_feed_item(item, COMPANY_BRAIN)
    except Exception:
        pass


class TreasuryActionRequest(BaseModel):
    name: Optional[str] = None


@app.get("/treasury/queue",
         summary="Round Treasury payment queue — ready vs held invoices",
         description="Every checked incoming invoice, sorted by the action "
                     "plan: no hold-type action -> ready to stage with "
                     "amount/payee/due date/tier approver; HOLD_PAYMENT, "
                     "VERIFY_VENDOR or ESCALATE -> held with the reason and "
                     "cited brain_key. Sample data — no money ever moves.")
def treasury_queue():
    return treasury.list_queue()


@app.post("/treasury/{qid}/approve",
          summary="Mark a queued invoice approved (still no payment)",
          description="Records approved_by + approved_at on a ready item. "
                      "Held items must be released first. Nothing is paid — "
                      "the label always says sample data, no money moves.")
def treasury_approve(qid: str, req: TreasuryActionRequest):
    entry, err = treasury.approve(qid, req.name or "api")
    if err:
        code = 404 if "not found" in err else 409
        return JSONResponse(status_code=code, content={"error": err})
    return entry


@app.post("/treasury/{qid}/release-hold",
          summary="Release a held invoice back to ready",
          description="Clears the hold — the original violation reason stays "
                      "on the record for audit.")
def treasury_release(qid: str, req: TreasuryActionRequest):
    entry, err = treasury.release_hold(qid, req.name or "api")
    if err:
        code = 404 if "not found" in err else 409
        return JSONResponse(status_code=code, content={"error": err})
    return entry


def _reload_brain_after_chase() -> None:
    global COMPANY_BRAIN
    new_brain = load_brain()
    if new_brain:
        COMPANY_BRAIN = new_brain
    try:
        lightfern_bridge.export_brain(brain=COMPANY_BRAIN)
    except Exception:
        pass


class ChaseRequest(BaseModel):
    invoice_id: Optional[str] = None
    customer: Optional[str] = None


class ChaseNoteRequest(BaseModel):
    note: Optional[str] = None


@app.get("/receivables",
         summary="Who owes us money — receivables ageing",
         description="Open receivables from finance.invoices with days "
                     "overdue, ageing bucket (current / 1-30 / 31-60 / 60+), "
                     "prior chase count, last recorded promise, and bucket + "
                     "total sums. Paid invoices drop out automatically.")
def get_receivables():
    return chaser.ageing(COMPANY_BRAIN)


@app.post("/chase",
          summary="Draft a payment chase for an invoice or customer",
          description="{invoice_id} or {customer} -> a DRAFT chase email on "
                      "the tone ladder (friendly reminder -> firm -> final "
                      "notice escalating to the CFO). Cites invoice no, "
                      "amount, due date, days overdue and any prior promise; "
                      "uses OpenAI when OPENAI_API_KEY is set and a "
                      "deterministic template otherwise. Never sends.")
def chase(req: ChaseRequest):
    ref = req.invoice_id or req.customer
    if not ref or not str(ref).strip():
        return JSONResponse(status_code=422,
                            content={"error": "invoice_id or customer is required"})
    res = _chase_draft(str(ref))
    if res.get("error"):
        return JSONResponse(status_code=404, content={"error": res["error"]})
    return res


@app.post("/chase/{invoice_id}/log",
          summary="Mark a drafted chase as sent",
          description="Appends a 'chase' entry to the invoice's chase_log in "
                      "the brain (atomic write) — the next draft counts it "
                      "toward the tone ladder.")
def chase_log(invoice_id: str, req: ChaseNoteRequest):
    entry = chaser.log_chase(invoice_id, note=(req.note if req else None),
                             channel="api")
    if entry is None:
        return JSONResponse(status_code=404,
                            content={"error": f"no open receivable matching '{invoice_id}'"})
    _reload_brain_after_chase()
    return JSONResponse(status_code=201, content={
        "logged": True, "invoice_id": invoice_id, "entry": entry})


@app.post("/chase/{invoice_id}/paid",
          summary="Mark a receivable as paid",
          description="Sets the invoice status to paid (it drops out of "
                      "/receivables) and appends a 'paid' row to chase_log. "
                      "The previous status is kept in chase_paid_from.")
def chase_paid(invoice_id: str, req: ChaseNoteRequest):
    res = chaser.mark_paid(invoice_id, note=(req.note if req else None))
    if res is None:
        return JSONResponse(status_code=404,
                            content={"error": f"no open receivable matching '{invoice_id}'"})
    _reload_brain_after_chase()
    return {"paid": True, "invoice_id": res["invoice_id"],
            "from_status": res["from_status"], "entry": res["entry"]}


@app.get("/chase/{invoice_id}/history",
         summary="Chase history for an invoice",
         description="The invoice's chase_log — every chase sent, promise "
                     "recorded and paid event, oldest first.")
def chase_history(invoice_id: str):
    res = chaser.history(COMPANY_BRAIN, invoice_id)
    if res is None:
        return JSONResponse(status_code=404,
                            content={"error": f"no receivable matching '{invoice_id}'"})
    return res


# ---- month-end close -----------------------------------------------------


class CloseNudgeRequest(BaseModel):
    owner: Optional[str] = None


@app.get("/close",
         summary="Month-end close status",
         description="Percent done + the missing/in-progress steps with "
                     "owners and blockers, from finance.month_end_close "
                     "(SAMPLE data).")
def get_close():
    return close.close_status(COMPANY_BRAIN)


@app.get("/close/due-out",
         summary="Everything due out this month",
         description="Unpaid payable invoices + recurring bills + payroll "
                     "due in ?month=YYYY-MM (default: current month), with "
                     "a single total.")
def close_due_out(month: Optional[str] = None):
    return close.due_out(COMPANY_BRAIN, month)


@app.get("/runway",
         summary="Cash runway in months",
         description="finance.bank.balance_gbp ÷ monthly_burn_gbp — "
                     "computed live, figures cited.")
def get_runway():
    res = close.runway(COMPANY_BRAIN)
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    return res


@app.post("/close/nudge",
          summary="Draft close-chasing nudges — never sends",
          description="{owner} optional -> a DRAFT Slack DM to whoever "
                      "holds a missing/in-progress close step (one per "
                      "owner when omitted). Draft only — nothing is sent.")
def close_nudge(req: CloseNudgeRequest):
    res = close.draft_close_nudge(COMPANY_BRAIN, owner=(req.owner if req else None))
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    return res


@app.get("/",
       summary="Demo UI",
       description="Serves demo/index.html — the flagship single-file demo: "
                   "compose box, inline violations with evidence, one-click fixes.")
def index():
    return FileResponse(BASE.parent / "demo" / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
