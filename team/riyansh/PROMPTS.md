# Riyansh — Codex prompts (backend API + LLM · merge-master)

**How to use:** open Codex in the repo root. Paste ONE phase's entire fenced block as a
single message — it contains everything Codex needs. When it finishes, run the VERIFY
commands, then ship:

```
git checkout -b riyansh/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin riyansh/phase<N> && gh pr create --fill
```

**Merge duty:** when all 3 Phase-N PRs are up, merge in order **Darsh → Pranali → yours**.
Run `cd backend && uv run python smoke_test.py` after each merge.

**If the AI claims done but a VERIFY fails, or stops mid-task, reply with exactly:**
`Continue — complete every remaining numbered item, then run all VERIFY commands again.`

**Your files:** `backend/main.py`, `backend/llm_enrich.py` — never touch anything else.
**Extra:** register Finance/Ops by 11:15 · 12:30 fallback call · 15:30 freeze.

---

## Phase 1 — complete API surface

```
You are a senior backend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first — they define the project and the API contract, which is additive-only: never rename or remove response fields).

CommitGuard: a local FastAPI backend (backend/main.py) checks drafted emails/messages/invoices against backend/company_brain.json using deterministic rules in backend/rules.py. POST /verify-context returns {status, risk_level, violations[], suggested_rewrite, meta}; POST /execute-action delegates to backend/actions.py. A single-file HTML demo (demo/index.html) is served at GET /.

YOUR FILES ONLY: backend/main.py. Do NOT modify any other file.

TASK — complete the API surface. Some of this may already exist — verify what exists, keep what works, build what's missing. All changes must be ADDITIVE: existing response shapes stay identical.

1. VALIDATION on POST /verify-context:
   - text must be non-empty after .strip() → HTTP 422 with body exactly {"error": "text must be non-empty"} (use fastapi.responses.JSONResponse, not HTTPException — the shape must be {"error": ...}, not {"detail": ...})
   - context_type must be one of {"outgoing_email", "slack_message", "incoming_invoice", "general"} (a module-level VALID_CONTEXT_TYPES set) → 422 {"error": "context_type must be one of [...]"}
   - Apply the same validation through a shared _validate(text, context_type) helper returning a JSONResponse or None.

2. POST /verify-batch — request {"items": [{"text": "...", "context_type": "..."}]} → response {"results": [<identical /verify-context response object per item>]}. Empty items → 422 {"error": "items must be a non-empty list"}. Each item validated with _validate. Extract the existing verify logic into _verify(text, context_type) so both endpoints share it.

3. AUDIT FILTERS — extend GET /audit-log to accept optional query params ?type=<action_type> and ?result=<result>, forwarded to actions.read_audit(limit, type=..., result=...) IF that signature exists (Darsh's Phase 2 adds it — call read_audit defensively: try the filtered call, fall back to read_audit(limit) if it raises TypeError). Default limit stays 20.

4. OPENAPI POLISH — add summary= and description= to every route decorator so /docs reads like a product: e.g. verify_context summary="Check a draft or invoice against the company brain", execute_action summary="Apply fixes, stage invoices, escalate fraud, log overrides".

5. ERROR CONSISTENCY — every error path in this file returns a JSON body containing an "error" string field (HTTPException detail dicts that already include "error" are fine; add the field where missing).

CONSTRAINTS: additive only per CONTRACT.md; no new dependencies; must run with OPENAI_API_KEY unset.

WORKING RULES — follow exactly:
- Read backend/main.py completely BEFORE editing it.
- Work the numbered items IN ORDER and complete ALL of them — if one is already implemented, confirm it matches this spec and move on.
- Never silently skip an item — if truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete AND every VERIFY command produces the stated output. Before finishing, re-check each numbered item against your changes. Partial completion is a failure.

VERIFY — run and paste output:
- cd backend && uv run python smoke_test.py → all 4 pass, identical results
- curl -s 127.0.0.1:8000/health → ok:true
- POST /verify-batch with 2 items → {"results":[...]}
- POST /verify-context with "  " text → 422 {"error":"text must be non-empty"}
- POST /verify-context with context_type "bogus" → 422 {"error":...}
- GET /audit-log?type=STAGE_INVOICE → 200 (empty array is fine)
- GET /docs → all endpoints have summaries
```

## Phase 2 — complete llm_enrich.py

```
You are a senior backend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first).

backend/llm_enrich.py is the OPTIONAL second stage: after the deterministic rules engine runs, it asks OpenAI for additional findings and a polished full-text rewrite. Contract rules: it must NEVER remove or contradict a rule finding, must NEVER crash or raise (no API key, no network, timeout, bad JSON → all return None), and must never slow the endpoint (hard timeout). backend/main.py calls llm_enrich(text, context_type, violations, brain) and uses llm_enabled() — keep both signatures identical.

YOUR FILES ONLY: backend/llm_enrich.py. Do NOT modify any other file. Do not add dependencies — use the `openai` package already in requirements.txt.

TASK — rewrite backend/llm_enrich.py completely to this spec:

1. LAZY CLIENT — module-level _client = None. Inside a _get_client() helper: if _client is None and os.environ.get("OPENAI_API_KEY") is set, construct OpenAI() inside try/except (any exception → return None). Import openai lazily inside the helper too — `import llm_enrich` must work with the package missing entirely.

2. llm_enabled() → returns True only when a client can be constructed AND OPENAI_API_KEY is set.

3. llm_enrich(text, context_type, violations, brain) → Optional[dict]:
   - Return None immediately if no client.
   - Prompt design: system message = "You are CommitGuard's secondary review layer. Deterministic rules already found the listed violations — do NOT repeat them. Find ONLY additional risks (implied commitments, tone problems, missing disclaimers, promises not backed by the brain) and produce a polished rewrite that resolves ALL findings while keeping the sender's tone."
   - User message contains: json.dumps(brain), json.dumps(existing violations), context_type, and the draft text.
   - Call: client.chat.completions.create(model="gpt-4o-mini", temperature=0, timeout=4, response_format={"type": "json_schema", "json_schema": {"name": "commit_guard_enrich", "strict": True, "schema": {...}}})
   - JSON SCHEMA (use exactly):
     {"type":"object","properties":{
       "violations":{"type":"array","items":{"type":"object","properties":{
         "category":{"type":"string"},"severity":{"type":"string","enum":["LOW","MEDIUM","HIGH","CRITICAL"]},
         "issue":{"type":"string"},"correction":{"type":"string"},
         "suggested_rewrite":{"type":["string","null"]},
         "evidence":{"type":["object","null"],"properties":{"brain_key":{"type":"string"},"expected":{},"found":{}},"required":["brain_key"],"additionalProperties":true},
         "span":{"type":["object","null"],"properties":{"text":{"type":"string"},"start":{"type":"integer"},"end":{"type":"integer"}},"required":["text","start","end"],"additionalProperties":false}},
         "required":["category","severity","issue","correction","suggested_rewrite","evidence","span"],"additionalProperties":false}},
       "full_rewrite":{"type":["string","null"]}},
      "required":["violations","full_rewrite"],"additionalProperties":false}
   - Parse json.loads of the response content inside try/except → None on failure.
   - DEDUPE: filter out any returned violation whose evidence.brain_key already appears in the existing rule violations, or whose category+overlapping span duplicates one.
   - Tag each surviving added violation with source: v["source"]="llm" (additive field).
   - Return {"violations": <added violations>, "full_rewrite": <str or None>}.
   - ANY exception anywhere in this function → return None.

WORKING RULES — follow exactly:
- Read backend/llm_enrich.py and the current call site in backend/main.py completely BEFORE editing.
- Work the numbered items IN ORDER and complete ALL of them.
- Never silently skip an item — if truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete AND every VERIFY command produces the stated output. Before finishing, re-check each numbered item against your changes. Partial completion is a failure.

VERIFY — run and paste output:
- cd backend && env -u OPENAI_API_KEY uv run python -c "import llm_enrich; print(llm_enrich.llm_enabled())" → False, no error
- cd backend && env -u OPENAI_API_KEY uv run python smoke_test.py → all pass
- (if a key is available) OPENAI_API_KEY=... uv run python -c "import llm_enrich,json;print(llm_enrich.llm_enrich('we can do net-90 and 40% off','outgoing_email',[],json.load(open('company_brain.json'))))"
```

## Phase 3 — E2E proof + integration check

```
You are a senior engineer working in the CommitGuard repository (read AGENTS.md first).

YOUR FILES: create E2E.md at repo root ONLY. Do NOT modify any existing file.

TASK — write E2E.md, a numbered verification runbook a judge or teammate can follow to prove the whole system works, then RUN every command yourself and paste real outputs into the file:

1. Setup: clone → cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt → start: uv run uvicorn main:app --port 8000 (or ./start.sh from root)
2. curl -s 127.0.0.1:8000/health → expected {"ok":true,"engine":"rules",...}
3. For EACH of the scenarios in backend/scenarios.json: the exact curl POST /verify-context command (with the scenario's real context_type) and the EXPECTED violation list:
   - sales_email → FINANCIAL_POLICY + MARGIN_BREACH + TREASURY_LOCK (HIGH)
   - vendor_invoice → CRITICAL PAYMENT_REDIRECTION + 2× CONTRACT_OVERAGE
   - support_reply → 2× PROMISE_BREACH
   - clean_email → CLEAN
   - plus any new-rule scenarios added since (check scenarios.json)
4. POST /execute-action examples with expected responses: STAGE_INVOICE (then show round_staging_queue.json entry), ESCALATE_FRAUD (mentions CFO name), APPROVE_OVERRIDE without reason → HTTP 400, APPROVE_OVERRIDE with reason → success:true
5. GET /audit-log?limit=3 → newest-first entries
6. GET / → 200 (demo UI), GET /inspector.html → 200
7. Offline note: every step works with OPENAI_API_KEY unset — state it.
Include the real observed outputs inline under each command.

WORKING RULES — follow exactly:
- Cover ALL 7 sections — do not stop after the curls; the execute-action and offline sections are required.
- Never fabricate an expected output — run each command and paste what it ACTUALLY returned.
- DONE WHEN: E2E.md exists at repo root with real outputs for every numbered section. Partial completion is a failure.

VERIFY: I will run the file's commands in order — every output must match.
```

## Phase 4 — freeze duty (not an agent task)

- `cd backend && uv run python smoke_test.py` + `uv run python bench.py` on main — green
- Merge remaining PRs (Darsh → Pranali → yours)
- If the Lightfern SDK is usable: fill the `[SDK:]` slots in Pranali's conditional plugin prompt (bottom of team/pranali/PROMPTS.md) and hand it to her
- 15:30: call the freeze — demo-blockers only
