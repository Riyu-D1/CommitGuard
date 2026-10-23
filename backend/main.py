import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import rules

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"
AUDIT_PATH = BASE / "audit_log.jsonl"
STAGING_PATH = BASE / "round_staging_queue.json"

app = FastAPI(title="CommitGuard", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_client = None
if os.environ.get("OPENAI_API_KEY"):
    from openai import OpenAI
    _client = OpenAI()


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


def _llm_enrich(text: str, context_type: str, violations: list, brain: dict) -> Optional[dict]:
    if not _client:
        return None
    prompt = f"""You are CommitGuard, the pre-send compliance firewall for a company.
Review the draft below against the Company Brain and the deterministic findings.

Company Brain:
{json.dumps(brain, indent=2)}

Deterministic findings (already detected - keep them, improve wording if needed):
{json.dumps(violations, indent=2)}

Context type: {context_type}
Draft:
\"\"\"{text}\"\"\"

Return: status (CLEAN or VIOLATION_DETECTED), risk_level, violations (same fields:
category, severity, issue, correction, suggested_rewrite), and a single polished
full_rewrite of the draft that resolves every violation while keeping the sender's
tone. Set full_rewrite to null if CLEAN."""
    try:
        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=8,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "commit_guard_response",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["CLEAN", "VIOLATION_DETECTED"]},
                            "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                            "violations": {"type": "array", "items": {"type": "object"}},
                            "full_rewrite": {"type": ["string", "null"]},
                        },
                        "required": ["status", "risk_level", "violations", "full_rewrite"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return None


@app.post("/verify-context")
def verify_context(req: VerifyRequest):
    t0 = time.time()
    violations = rules.run_rules(req.text, COMPANY_BRAIN)
    engine = "rules"

    llm = _llm_enrich(req.text, req.context_type, violations, COMPANY_BRAIN)
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


def _audit(entry: dict) -> dict:
    entry = {
        "audit_log_id": f"log_{uuid.uuid4().hex[:8]}",
        "ts": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    with AUDIT_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


@app.post("/execute-action")
def execute_action(req: ActionRequest):
    if req.action_type == "STAGE_INVOICE":
        queue = json.loads(STAGING_PATH.read_text()) if STAGING_PATH.exists() else []
        queue.append({"staged_at": datetime.now(timezone.utc).isoformat(), **req.payload})
        STAGING_PATH.write_text(json.dumps(queue, indent=2))
        entry = _audit({"action_type": req.action_type, "payload": req.payload,
                        "result": "staged_in_round_queue"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": "Invoice staged to Round Treasury approval queue."}

    if req.action_type == "APPROVE_OVERRIDE" and not req.payload.get("reason"):
        raise HTTPException(400, "Override requires a reason - it goes in the audit log.")

    if req.action_type == "ESCALATE_FRAUD":
        entry = _audit({"action_type": req.action_type, "payload": req.payload,
                        "result": "escalated_to_cfo"})
        return {"success": True, "audit_log_id": entry["audit_log_id"],
                "message": f"Escalated to {COMPANY_BRAIN.get('people', {}).get('cfo', 'CFO')} - payment blocked pending out-of-band verification."}

    entry = _audit({"action_type": req.action_type, "payload": req.payload, "result": "ok"})
    return {"success": True, "audit_log_id": entry["audit_log_id"],
            "message": f"Processed {req.action_type} and wrote it to the audit trail."}


@app.get("/brain")
def get_brain():
    return COMPANY_BRAIN


@app.post("/brain/reload")
def reload_brain():
    global COMPANY_BRAIN
    COMPANY_BRAIN = load_brain()
    return {"reloaded": True, "keys": list(COMPANY_BRAIN.keys())}


@app.get("/audit-log")
def audit_log(limit: int = 20):
    if not AUDIT_PATH.exists():
        return []
    lines = AUDIT_PATH.read_text().strip().splitlines()
    return [json.loads(l) for l in lines[-limit:]][::-1]


@app.get("/scenarios")
def scenarios():
    return SCENARIOS


@app.get("/")
def index():
    return FileResponse(BASE.parent / "demo" / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
