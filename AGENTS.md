# CommitGuard — project context for AI agents

**What this is:** a pre-send compliance firewall. A local FastAPI backend checks
drafted emails, messages, and incoming invoices against a structured company
knowledge base and returns violations BEFORE anything is sent or paid.
Detection is a **deterministic rules engine** (regex + dictionary checks — NOT
an LLM). An optional OpenAI layer enriches results but is never required.

**Track:** Round Treasury Finance/Ops — judges care about fraud detection,
auditability ("why was this flagged?" must cite evidence), and working software.

## Architecture

- `backend/main.py` — FastAPI app. Endpoints: POST /verify-context,
  POST /verify-batch, POST /execute-action, GET /brain, POST /brain/reload,
  GET /audit-log, GET /scenarios, GET /health, GET /, GET /inspector.html
- `backend/rules.py` — deterministic engine. Check functions registered in
  `ALL_CHECKS`; each returns violation dicts:
  `{category, severity, issue, correction, suggested_rewrite, evidence:
  {brain_key, expected, found}, span: {text, start, end}, fix}`.
  `run_rules(text, brain, context_type)`, `risk_level()`, `apply_fixes()`.
- `backend/actions.py` — POST /execute-action handlers + audit_log.jsonl +
  round_staging_queue.json (mock Round pickup queue)
- `backend/company_brain.json` — the knowledge base: financial_rules,
  signed_contracts (incl. bank_iban), engineering_status, people,
  known_sender_domains
- `backend/scenarios.json` — the 4 demo texts (smoke test reads these)
- `backend/llm_enrich.py` — optional OpenAI second stage (fail-open)
- `demo/index.html` — flagship single-file demo UI (served at /)
- `demo/inspector.html` — compliance console (brain + audit + health)
- `plugin/` — adapter.js (only backend client), simulator.html, rules.js
- `pitch/` — submission, script, rehearsal sheet, one-pager
- `CONTRACT.md` — the API contract. **Additive only — never rename/remove fields.**

## Commands (uv + Python 3.12)

```bash
cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt
cd backend && uv run uvicorn main:app --port 8000   # serve on 127.0.0.1:8000
cd backend && uv run python smoke_test.py           # MUST stay green
```

Use `127.0.0.1`, never `localhost` (IPv6 resolution issue on some Macs).
Backend must work with `OPENAI_API_KEY` unset — no exceptions.

## Non-negotiables

- The 4 smoke-test results never change: sales_email→FINANCIAL_POLICY+
  MARGIN_BREACH+TREASURY_LOCK · vendor_invoice→CRITICAL PAYMENT_REDIRECTION+
  2 CONTRACT_OVERAGE · support_reply→2 PROMISE_BREACH · clean_email→CLEAN
- Every violation cites evidence — a brain_key, expected vs found value
- Single-file frontend HTML, vanilla JS/CSS, no CDN (offline demo)
- File ownership: backend/main.py + llm_enrich.py = Riyansh; other backend
  files = Darsh; demo/ + plugin/ + pitch/ = Pranali. Stay in your lane.
