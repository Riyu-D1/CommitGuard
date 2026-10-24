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
  known_sender_domains (added by a phase prompt — may not exist yet)
- `backend/scenarios.json` — the 4 demo texts (smoke test reads these)
- `backend/llm_enrich.py` — optional OpenAI second stage (fail-open)
- `demo/index.html` — flagship single-file demo UI (served at /)
- `demo/inspector.html` — compliance console (brain + audit + health)
- `plugin/` — adapter.js (only backend client), simulator.html;
  rules.js is a planned offline-rules port (may not exist yet)

Work happens in rolling phases on branches `<name>/phase<N>`, each cut from
fresh main. Teammates' phases merge at different times: if a referenced
file, brain key, response field or rule category doesn't exist, that
phase may not have merged yet. Treat it as pending, degrade gracefully,
and never create it outside your own files.
- `pitch/` — submission, script, rehearsal sheet, one-pager
- `CONTRACT.md` — the API contract. **Additive only — never rename/remove fields.**

## Commands (uv + Python 3.12)

```bash
cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt
cd backend && uv run uvicorn main:app --port 8000   # serve on 127.0.0.1:8000
cd backend && uv run python smoke_test.py           # must print ALL PASS / exit 0
# restart after editing backend code (no --reload): a running server keeps the OLD code
pkill -f "uvicorn main:app"; cd backend && (nohup uv run uvicorn main:app --port 8000 > /tmp/cg.log 2>&1 &) ; sleep 3
cd backend && uv run python seed_audit.py           # demo audit entries (--reset once Darsh P4 lands)
```

`audit_log.jsonl` and `round_staging_queue.json` are gitignored local state.
Test curls write to them, so clean up test rows you create.

**Never print backend/.env** — it can hold a real Slack token. If one is
configured, any server you start polls and can post to the live channel
(SLACK_REPLY=1). For local test servers always force simulated mode —
real env wins over .env:

```bash
cd backend && SLACK_BOT_TOKEN=disabled SLACK_REPLY=0 SLACK_CHANNEL_ID= \
  uv run uvicorn main:app --port 8000
```

Use `127.0.0.1`, never `localhost` (IPv6 resolution issue on some Macs).
Backend must work with `OPENAI_API_KEY` unset — no exceptions.

## Non-negotiables

- The baseline smoke-test results never change (a 5th optional scenario may
  be added later — additions fine, the original 4 stay identical): sales_email→FINANCIAL_POLICY+
  MARGIN_BREACH+TREASURY_LOCK · vendor_invoice→CRITICAL PAYMENT_REDIRECTION+
  2 CONTRACT_OVERAGE · support_reply→2 PROMISE_BREACH · clean_email→CLEAN
- Every violation cites evidence — a brain_key, expected vs found value
- Single-file frontend HTML, vanilla JS/CSS, no CDN (offline demo)
- File ownership: backend/main.py + llm_enrich.py + E2E.md + CONTRACT.md =
  Riyansh (plus plugin/ today, only if the plugin is GO); other backend
  files = Darsh; demo/ + pitch/ = Pranali. Stay in your lane.
- LLM output is advisory only: it goes in the top-level `advisories` array
  and never changes `status`, `risk_level` or `violations`.
