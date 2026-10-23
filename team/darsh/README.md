# Darsh — Backend Rules, Actions & Brain

Everyone codes via agents all day. Your workstream: `backend/rules.py`,
`backend/actions.py`, `backend/company_brain.json`, `backend/smoke_test.py`.
`main.py` and `llm_enrich.py` are NOT yours (Riyansh/shared). `scenarios.json`
is Pranali's — ask her before touching.

**Golden rule: after every agent run — `cd backend && uv run python smoke_test.py`.
Not green → paste the error back to the agent. Never push failing code.**

## Your files

- `backend/rules.py` — the deterministic engine (all the demo magic lives here)
- `backend/actions.py` — execute-action handlers + audit helpers
- `backend/company_brain.json` — the brain data
- `backend/smoke_test.py` — your safety net (extend it, never weaken it)
- `backend/bench.py` — yours to create (stretch task)

Expected smoke results: sales_email → 3 violations · vendor_invoice → CRITICAL
PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE · support_reply → 2 PROMISE_BREACH ·
clean_email → CLEAN.

## Phases (stay on your agent constantly)

### Phase 0 — before 10:45
- [ ] `cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt`
- [ ] `uv run uvicorn main:app --port 8000` → click all 4 scenarios at localhost:8000
- [ ] `uv run python smoke_test.py` green; read `rules.py` — understand `_v()` + one check fully
- [ ] Branch `darsh/setup`

### Phase 1 — 10:45→11:15
- [ ] **Prompt A** straight away (3 new rules + tests) — this is your biggest task, start early

### Phase 2 — 11:15→13:00 (M1)
- [ ] Finish Prompt A → verify → PR `darsh/rules-v2` → Riyansh merges at M1
- [ ] Start **Prompt B** (actions dedupe + context filtering)

### Phase 3 — 13:00→14:30 (M2)
- [ ] Finish Prompt B → PR `darsh/actions`
- [ ] **Prompt C** (unverified-promise rule), then **Prompt D** (brain enrichment)
- [ ] PRs merged at M2

### Phase 4 — 14:30→16:00 (M3)
- [ ] Freeze. Demo-blockers only, on standby for Riyansh.

### Stretch queue (if early — pull from TEAM_PLAN shared list first)
- **Prompt E**: `bench.py` latency report (demo stat: "checks run in <5ms")
- Context-type scenario suggestions for Pranali (what should fire differently for slack_message vs invoice?)

## Stuck? In order:
1. Re-run smoke_test, read the error
2. `git diff` — did you break an existing check?
3. Re-paste the prompt with the error appended
4. Ask Riyansh — never sit blocked >10 min
