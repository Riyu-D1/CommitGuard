# Darsh — backend rules + actions + data

**How to use:** each phase is ONE fenced block. Paste the ENTIRE block into your AI tool
(it contains all the context the AI needs — it knows nothing until you paste it).
Then run the verify commands the AI gives you, and ship:

```
git checkout -b darsh/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin darsh/phase<N> && gh pr create --fill
```

**Your files:** `backend/rules.py`, `actions.py`, `company_brain.json`, `scenarios.json`,
`smoke_test.py`, `bench.py`, `seed_audit.py` — never touch `main.py`, `llm_enrich.py`, or anything in `demo/` `plugin/` `pitch/`.

---

## Phase 1 — fraud rules

```
You are an engineer working in a git repo called CommitGuard — a pre-send compliance firewall for a hackathon.

WHAT IT IS: a local FastAPI backend checks drafted emails/messages/invoices against backend/company_brain.json (a fake company's knowledge base: financial rules, signed contracts with bank details, engineering status) using backend/rules.py — a deterministic rule engine (regex + dictionary lookups, NOT an LLM). Each check function returns violation dicts and is registered in ALL_CHECKS. backend/smoke_test.py runs 4 demo scenarios from backend/scenarios.json and prints results. Read backend/rules.py FIRST to match the exact violation format: {category, severity, issue, correction, suggested_rewrite, evidence: {brain_key, expected, found}, span: {text, start, end}, fix}.

YOUR FILES ONLY: backend/rules.py, backend/company_brain.json, backend/smoke_test.py. Do NOT modify any other file.

TASK — add 3 new check functions to backend/rules.py in the existing style (register each in ALL_CHECKS):
1. DUPLICATE_INVOICE (severity CRITICAL): fires when text contains an invoice number (regex like INV-\d+ or similar) AND words like "already paid", "duplicate", or "second request".
2. SENDER_DOMAIN_MISMATCH (severity HIGH): fires when text contains "from:" or "reply-to:" with a domain NOT in a new "known_sender_domains" list you add to backend/company_brain.json.
3. URGENT_PAYMENT_CHANGE (severity CRITICAL): fires when urgency words (urgent, immediately, today, EOD) appear within 120 characters of bank-detail words (IBAN, sort code, bank details, updated payment).
Every violation must have evidence (brain_key pointing at real brain data, expected, found) and a span where feasible.

Then add ONE smoke_test.py case per new rule (a short text string + expected category). The 4 existing scenario results MUST stay identical.

VERIFY (run and show output): cd backend && uv run python smoke_test.py — all pass, original 4 unchanged.
```

## Phase 2 — actions hardening

```
You are an engineer working in a git repo called CommitGuard — a pre-send compliance firewall. (Backend checks drafts/invoices against backend/company_brain.json via deterministic rules; backend/actions.py handles POST /execute-action: applies rewrites, stages invoices into a Round-style queue file, escalates fraud, and appends every action to an audit_log.jsonl. backend/main.py calls actions.execute_action — do not touch main.py.)

YOUR FILES ONLY: backend/actions.py. Read it first, match its style. Do NOT modify any other file.

TASK — in backend/actions.py only:
1. Deduplication: if the same action_type + the same invoice identifier appears in audit_log.jsonl within the last 10 minutes, return {success: false, error: "duplicate"} — but STILL append an audit entry recording the rejected attempt.
2. Ensure every audit entry carries an ISO timestamp field.
3. Extend read_audit() to support optional filters: action type and result/status (the caller will pass ?type= and ?status= as kwargs or a filter dict — pick the simplest signature and document it in a comment).
VERIFY (run and show output):
- cd backend && uv run python smoke_test.py → all pass
- POST /execute-action twice with the same STAGE_INVOICE payload → second returns duplicate error; GET /audit-log shows both attempts
```

## Phase 3 — context filtering + promise rule

```
You are an engineer working in a git repo called CommitGuard — a pre-send compliance firewall. (Deterministic rules in backend/rules.py check text against backend/company_brain.json; run_rules(text, brain, context_type) already receives context_type from main.py but currently ignores it. Valid context_type values per CONTRACT.md: outgoing_email, slack_message, incoming_invoice, general.)

YOUR FILES ONLY: backend/rules.py, backend/smoke_test.py, backend/company_brain.json. Do NOT modify any other file.

TASK — in backend/rules.py:
1. Add a CONTEXTS mapping declaring which context_types each check applies to. Rules: invoice-specific checks (bank details, contract amounts, duplicate invoice, sender domain, urgency) fire ONLY on "incoming_invoice"; payment/promise/policy checks (payment terms, discount cap, treasury lock, feature claims, refund caps) fire ONLY on outgoing_* and "general"; CRITICAL-severity rules always fire regardless. run_rules must use the map and default safely for unknown context_type values.
2. Add one new check: PROMISE_BREACH (severity MEDIUM) — fires when text claims a feature or status that contradicts company_brain.json engineering_status (e.g., claiming something is "live"/"complete"/"shipped" that the brain says is in development or in audit).
3. Add 2 smoke_test.py cases covering context filtering (e.g., invoice words in an outgoing_email should NOT trigger invoice rules). The 4 original scenario results MUST stay identical.
VERIFY (run and show output): cd backend && uv run python smoke_test.py — all pass, original 4 unchanged.
```

## Phase 4 — perf + polish

```
You are an engineer working in a git repo called CommitGuard — a pre-send compliance firewall (deterministic rules engine in backend/rules.py; demo at 127.0.0.1:8000 with an Inspector page showing the audit log).

YOUR FILES ONLY: backend/bench.py, backend/seed_audit.py, backend/rules.py (small additive change only), backend/company_brain.json.

TASK:
1. Run uv run python bench.py (it already exists — times the rules engine over all scenarios). Report the avg and p95 latency numbers in your PR description — the pitch needs a "runs in <N ms" stat.
2. Run uv run python seed_audit.py once so the Inspector page's audit table isn't empty for the demo.
3. OPTIONAL (only if 1-2 are done and tests pass): add a "risk_score" (0-100) field to each violation dict in rules.py — a simple severity-weighted score. Additive field only; do not rename or remove existing fields.
VERIFY (run and show output): cd backend && uv run python smoke_test.py — all pass, 4 original results identical.
```
