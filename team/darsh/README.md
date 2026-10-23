# Darsh — Backend Rules, Actions & Brain

Everyone codes via agents all day. Your workstream: the deterministic engine +
actions + brain data. **Your build lives in `PROMPTS.md` — execute it
top-to-bottom.**

## Your files (nobody else touches them)

- `backend/rules.py` — the deterministic engine (the demo's magic lives here)
- `backend/actions.py` — execute-action handlers + audit helpers
- `backend/company_brain.json` — brain data (Pranali owns scenario *text*)
- `backend/smoke_test.py` — your safety net (extend it, never weaken it)
- `backend/bench.py`, `backend/seed_audit.py` — yours to create

## Phase map

| Phase | Time | Prompts | Done when |
|---|---|---|---|
| 1 — Rules v2 | 10:45–13:00 | A (3 fraud rules + tests) | DUPLICATE_INVOICE, PHISHING_SIGNAL, urgency check all fire; smoke green → **M1** |
| 2 — Actions + filtering | 13:00–14:00 | B (dedupe + audit) → C (context-aware rules) | double-stage returns "already staged"; invoice checks don't fire on emails |
| 3 — Promises + brain + perf | 13:45–14:30 | D (unverified promise) → E (brain enrichment) → F (bench.py) | promise rule fires only when unbacked; brain has 3 vendors/4 eng items; latency table exists → **M2** |
| 4 — Stretch | — | G (audit seed) · H (risk score) — claim shared queue items first | — |

## The ritual (every prompt, no exceptions)

```bash
cd backend && uv run python smoke_test.py
```

Green → commit/PR. Not green → paste error back to agent. **Never push failing code.**

Expected always: sales_email → 3 violations · vendor_invoice → CRITICAL
PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE · support_reply → 2 PROMISE_BREACH ·
clean_email → CLEAN.

## Stuck? In order:
1. Re-run smoke_test, read the error
2. `git diff` — did the agent break an existing check?
3. Re-paste the prompt with the error appended
4. Ask Riyansh — never blocked >10 min
