import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import rules
import actions
import slack_feed
from llm_enrich import llm_enrich, llm_enabled

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"


@asynccontextmanager
async def lifespan(_app):
    slack_feed.start(verify_fn=_verify, scenarios=SCENARIOS)
    yield


app = FastAPI(title="CommitGuard", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
    return {
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
    return _verify(req.text, req.context_type)


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
    return {"results": [_verify(it.text, it.context_type) for it in req.items]}


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
