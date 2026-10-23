import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import rules
import actions
from llm_enrich import llm_enrich, llm_enabled

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"

app = FastAPI(title="CommitGuard", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


class ActionRequest(BaseModel):
    action_type: str
    payload: dict = {}


SCENARIOS_PATH = BASE / "scenarios.json"
SCENARIOS = json.loads(SCENARIOS_PATH.read_text()) if SCENARIOS_PATH.exists() else {}


@app.post("/verify-context")
def verify_context(req: VerifyRequest):
    t0 = time.time()
    violations = rules.run_rules(req.text, COMPANY_BRAIN, req.context_type)
    engine = "rules"

    llm = llm_enrich(req.text, req.context_type, violations, COMPANY_BRAIN)
    full_rewrite = None
    if llm:
        engine = "rules+llm"
        full_rewrite = llm.get("full_rewrite")
        for v in llm.get("violations", []):
            if v.get("suggested_rewrite"):
                for dv in violations:
                    if not dv.get("suggested_rewrite") and dv["category"] == v.get("category"):
                        dv["suggested_rewrite"] = v["suggested_rewrite"]

    status = "VIOLATION_DETECTED" if violations else "CLEAN"
    return {
        "status": status,
        "risk_level": rules.risk_level(violations),
        "violations": violations,
        "suggested_rewrite": full_rewrite or (rules.apply_fixes(req.text, violations) if violations else None),
        "meta": {
            "engine": engine,
            "checks_run": len(rules.ALL_CHECKS),
            "latency_ms": round((time.time() - t0) * 1000, 1),
        },
    }


@app.post("/execute-action")
def execute_action(req: ActionRequest):
    return actions.execute_action(req.action_type, req.payload, COMPANY_BRAIN)


@app.get("/brain")
def get_brain():
    return COMPANY_BRAIN


@app.post("/brain/reload")
def reload_brain():
    global COMPANY_BRAIN
    try:
        COMPANY_BRAIN = load_brain()
    except Exception as e:
        raise HTTPException(422, {"reloaded": False, "error": str(e)})
    if not COMPANY_BRAIN:
        raise HTTPException(422, {"reloaded": False, "error": "company_brain.json empty or malformed"})
    return {"reloaded": True, "keys": list(COMPANY_BRAIN.keys())}


@app.get("/audit-log")
def audit_log(limit: int = 20):
    return actions.read_audit(limit)


@app.get("/scenarios")
def scenarios():
    return SCENARIOS


@app.get("/health")
def health():
    return {"ok": True, "engine": "rules+llm" if llm_enabled() else "rules",
            "checks": len(rules.ALL_CHECKS), "brain_keys": list(COMPANY_BRAIN.keys())}


@app.get("/inspector.html")
def inspector():
    path = BASE.parent / "demo" / "inspector.html"
    if not path.exists():
        raise HTTPException(404, "inspector.html not built yet")
    return FileResponse(path)


@app.get("/")
def index():
    return FileResponse(BASE.parent / "demo" / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
