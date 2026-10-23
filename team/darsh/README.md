# Darsh — Backend Rules & Actions

You own `backend/rules.py`, `backend/company_brain.json`, `backend/smoke_test.py`,
and the `/execute-action` handlers in `backend/main.py` (everything except
`_llm_enrich` — that's Riyansh's). `scenarios.json` belongs to Pranali — ask her
before touching it.

**Golden rule: after every change run the smoke test. If it's not green, undo and
re-prompt — never push broken code.**

```bash
cd backend && uv run python smoke_test.py
```

All 4 scenarios must print their expected results (last line of each block):
- sales_email → 3 violations (FINANCIAL_POLICY, MARGIN_BREACH, TREASURY_LOCK)
- vendor_invoice → CRITICAL PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE
- support_reply → 2 PROMISE_BREACH
- clean_email → CLEAN

## How your code fits in

`rules.py` is a list of check functions `(text, brain) -> [violations]` registered in
`ALL_CHECKS`. The API runs every check on every message. No AI knowledge needed —
it's pattern matching (regex) against the JSON brain. Each violation carries an
`evidence` block — that's what makes judges trust it.

## Phases

### Phase 0 — before 10:45
- [ ] `cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt`
- [ ] `uv run uvicorn main:app --port 8000` → open localhost:8000, click the 4 scenario buttons, watch cards appear
- [ ] `uv run python smoke_test.py` → all green
- [ ] Branch `darsh/setup`

### Phase 1 — 10:45→11:15
- [ ] Read `backend/rules.py` top to bottom — understand `_v()` and one check fully
- [ ] Read `CONTRACT.md` — you must not break response fields

### Phase 2 — 11:15→13:00 (M1 gate)
- [ ] **Prompt A**: add 3 new rules (duplicate invoice, sender-domain phishing, urgency+bank-change)
- [ ] Verify: `smoke_test.py` green AND your 3 new test cases fire
- [ ] PR `darsh/rules-v2` → Riyansh merges at M1

### Phase 3 — 13:00→14:30 (M2 gate)
- [ ] **Prompt B**: `/execute-action` hardening (invoice dedupe, `/health`, safe `/brain/reload`)
- [ ] **Prompt C** (if time): unverified-promise rule
- [ ] PR `darsh/actions` → merge at M2

### Phase 4 — 14:30→16:00 (M3 freeze)
- [ ] Freeze. Fix only what breaks the demo. On standby for Riyansh.

## Stuck? In order:

1. Re-run `smoke_test.py` and read the error line
2. `git diff` — check you didn't break an existing check
3. Re-paste the prompt to the agent with the error message appended
4. Ask Riyansh — never sit blocked >10 minutes
