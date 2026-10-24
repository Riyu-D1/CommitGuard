# Riyansh — backend API + LLM · merge-master

**How to use:** each phase is ONE fenced block. Paste the ENTIRE block into your AI tool
(it contains all the context the AI needs — it knows nothing until you paste it).
Run the VERIFY line inside the prompt's output, then ship with the commands below.

**Your files:** `backend/main.py`, `backend/llm_enrich.py` — never touch anything else.
**Merge duty:** after all 3 PRs are up each phase, merge in order Darsh → Pranali → yours.
Run `cd backend && uv run python smoke_test.py` before your own merge.

## Ship (every phase)

```
git checkout -b riyansh/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin riyansh/phase<N> && gh pr create --fill
```

---

## Phase 1 — API hardening

```
You are a senior engineer working in a git repo called CommitGuard — a pre-send compliance firewall built for a hackathon.

WHAT IT IS: a local FastAPI backend (backend/) checks drafted emails/messages/invoices against a structured company knowledge base (backend/company_brain.json) using deterministic rules in backend/rules.py — regex/dictionary checks, NOT an LLM. It returns violations with evidence (brain_key, expected vs found), span offsets, and fix text. A single-file HTML demo (demo/index.html) served by the backend at http://127.0.0.1:8000 shows the results. Everything already runs.

REPO MAP: backend/main.py (FastAPI app), backend/rules.py (rule engine), backend/actions.py (action handlers + audit log), backend/company_brain.json (knowledge base), backend/scenarios.json (4 demo texts), backend/smoke_test.py (tests), demo/ + plugin/ + pitch/ (frontend). CONTRACT.md documents the API — read it first.

YOUR FILES ONLY: backend/main.py and backend/llm_enrich.py. Do NOT modify any other file.

TASK — in backend/main.py only, additive changes (never change existing response shapes):
1. CORS is already enabled via CORSMiddleware — verify it's there, do not duplicate.
2. Refactor the body of POST /verify-context into a shared _verify(text, context_type) helper so the response shape stays identical.
3. Add validation to /verify-context: text must be non-empty after strip; context_type must be one of {outgoing_email, slack_message, incoming_invoice, general} (match CONTRACT.md exactly). On failure return HTTP 422 with body {"error": "<reason>"} — use JSONResponse, not HTTPException, so the shape is exactly {"error": ...}.
4. New POST /verify-batch: request {"items": [{"text": "...", "context_type": "..."}]} → response {"results": [<identical verify-context response per item>]}. Empty items list → 422 {"error": "items must be a non-empty list"}. Reuse _verify and the same validation.

VERIFY (run these and show me output):
- cd backend && uv run python smoke_test.py → all 4 scenarios pass with identical results to before
- curl 127.0.0.1:8000/health → ok:true
- curl -X POST 127.0.0.1:8000/verify-batch with 2 items → {"results":[...]}
- POST /verify-context with empty text → 422 {"error":...}
```

## Phase 2 — LLM enrichment

```
You are a senior engineer working in a git repo called CommitGuard — a pre-send compliance firewall. (Same project context: FastAPI backend checks drafts/invoices against backend/company_brain.json via deterministic rules in backend/rules.py; violations return evidence, spans, fixes. CONTRACT.md documents the API.)

CONTEXT FOR THIS FILE: backend/llm_enrich.py is an OPTIONAL second stage — after rules run, it asks OpenAI to find additional violations and polish rewrites. It must NEVER remove or contradict a rule finding, must never crash, and must work with no API key. The current version already works; your job is to harden it.

YOUR FILES ONLY: backend/llm_enrich.py. Do NOT modify any other file.

TASK — rewrite backend/llm_enrich.py:
- Model gpt-4o-mini, temperature 0, 4s timeout, strict JSON schema (json_schema response_format) for an array of violation objects matching CONTRACT.md fields (category, severity, issue, correction, suggested_rewrite, evidence, span).
- If OPENAI_API_KEY is unset, the request times out, the response fails to parse, or ANY error occurs → return None silently (the caller treats None as "no enrichment"). Never raise.
- Only construct the OpenAI client lazily inside the function when a key exists — importing this module must never crash without the package or key.
- Deduplicate: drop any LLM violation whose evidence.brain_key is already covered by a rule-found violation. LLM output may only ADD findings or improve suggested_rewrite wording.
VERIFY (run and show output):
- cd backend && uv run python smoke_test.py → all pass with OPENAI_API_KEY unset
- import llm_enrich in python → no error without the key
- With a key set (if available): POST /verify-context → meta.engine becomes "rules+llm"
```

## Phase 3 — E2E proof

```
You are a senior engineer working in a git repo called CommitGuard — a pre-send compliance firewall (FastAPI backend + deterministic rules + single-file HTML demo at http://127.0.0.1:8000).

YOUR FILES: you may create E2E.md at the repo root only. Do NOT modify any existing file.

TASK: create E2E.md — a numbered verification runbook a judge or teammate can follow to prove the whole system works end-to-end:
1. Start command (./start.sh or cd backend && uv run uvicorn main:app --port 8000) + expected output
2. curl /health → expected JSON
3. For each of the 4 scenarios (from backend/scenarios.json): the POST /verify-context command and the EXPECTED violations (sales_email→3 incl FINANCIAL_POLICY/MARGIN_BREACH/TREASURY_LOCK; vendor_invoice→CRITICAL PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE; support_reply→2 PROMISE_BREACH; clean_email→CLEAN)
4. POST /execute-action examples (STAGE_INVOICE, ESCALATE_FRAUD, APPROVE_OVERRIDE incl. the 400-without-reason case) + expected responses
5. GET /audit-log → entries appear
6. GET / and /inspector.html → 200
Then actually RUN every command yourself, fix any command that's wrong, and paste real outputs into the file.
VERIFY: every command in E2E.md produces the documented output when run.
```

## Phase 4 — freeze duty (not an agent task)

Run `cd backend && uv run python smoke_test.py` + `uv run python bench.py` on main,
merge the last PRs. If the Lightfern SDK is usable, fill the `[SDK:]` slots in
Pranali's conditional plugin prompt (team/pranali/PROMPTS.md bottom) and hand it to her.
