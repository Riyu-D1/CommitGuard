import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import rules
import actions
import slack_feed
import lightfern_bridge
from llm_enrich import llm_enrich, llm_enabled, llm_polish_answer

from rules import explain_policy, policy_cards

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"

@asynccontextmanager
async def lifespan(_app):
    lightfern_bridge.start(hooks={
        "learn": _learn,
        "exception": _learn_exception,
        "override": _apply_override,
        "ask": _ask_brain,
        "import_brain": _import_brain,
    })
    slack_feed.start(verify_fn=_verify, scenarios=SCENARIOS,
                     ask_fn=_ask_brain, override_fn=_slack_override)
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
    tr = time.time()
    violations = rules.run_rules(text, COMPANY_BRAIN, context_type)
    rules_ms = round((time.time() - tr) * 1000, 2)
    engine = "rules"
    advisories = []
    full_rewrite = None

    llm = llm_enrich(text, context_type, violations, COMPANY_BRAIN)
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
            "checks_run": len(rules.ALL_CHECKS),
            "latency_ms": round((time.time() - t0) * 1000, 1),
            "rules_ms": rules_ms,
        },
    }
    result["actions"] = actions.plan_actions(result, COMPANY_BRAIN)
    return result


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


def _ask_brain(question: str) -> dict:
    """Shared ask-the-brain logic for POST /ask and Slack questions.
    Deterministic first; if OPENAI_API_KEY is set the answer is rephrased
    in friendlier words (sources untouched), failing open."""
    t0 = time.time()
    out = explain_policy(question, COMPANY_BRAIN)
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
        COMPANY_BRAIN = load_brain()
    except Exception as e:
        raise HTTPException(422, {"reloaded": False, "error": str(e)})
    if not COMPANY_BRAIN:
        raise HTTPException(422, {"reloaded": False, "error": "company_brain.json empty or malformed"})
    return {"reloaded": True, "keys": list(COMPANY_BRAIN.keys())}


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
    item = slack_feed.inject(req.text, user=req.user)
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


@app.get("/",
       summary="Demo UI",
       description="Serves demo/index.html — the flagship single-file demo: "
                   "compose box, inline violations with evidence, one-click fixes.")
def index():
    return FileResponse(BASE.parent / "demo" / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
