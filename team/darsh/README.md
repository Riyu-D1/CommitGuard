# Darsh — backend rules + actions + data

**Your files:** `backend/rules.py`, `actions.py`, `company_brain.json`,
`scenarios.json`, `smoke_test.py`, `bench.py`, `seed_audit.py`
**Never touch:** `main.py`, `llm_enrich.py` (Riyansh) · `demo/` `plugin/` `pitch/`

## The day (rolling phases, no all-3 barrier)

Paste phase prompts from `PROMPTS.md` in order. Start the next one as soon as YOUR PR merges.
Always start with `git checkout main && git pull && git checkout -b darsh/phase<N>`.

| Phase | What | Merged by |
|---|---|---|
| 1 | smoke test becomes a real gate (asserts + exit code) + 3 fraud rules | 12:00 |
| 2 | actions: dedupe, filters, unknown-action 400 | 12:40 |
| 3 | context filtering + UNVERIFIED_CLAIM + brain expansion | 13:30 |
| 4 | bench, `seed_audit.py --reset`, risk_score, 5th scenario (**skip if not started by 13:45**) | 14:15 |

Before **every** commit:

```bash
cd backend && uv run python smoke_test.py   # must end with ALL PASS (exit 0) after Phase 1
```

Green → ship. Red → paste the error back to the agent. **Never push failing code.**

Baseline (never changes): `sales_email` → FINANCIAL_POLICY + MARGIN_BREACH + TREASURY_LOCK · `vendor_invoice` → CRITICAL PAYMENT_REDIRECTION +
2 CONTRACT_OVERAGE · `support_reply` → 2 PROMISE_BREACH · `clean_email` → CLEAN

## Stuck? In order:

1. Re-run smoke test, read the error
2. `git diff`: did the agent break an existing check?
3. Re-paste the prompt with the error appended
4. Tag Riyansh. Never stay blocked >10 min
