# Darsh — backend rules + actions + data

**Your files:** `backend/rules.py`, `actions.py`, `company_brain.json`,
`scenarios.json`, `smoke_test.py`, `bench.py`, `seed_audit.py`
**Never touch:** `main.py`, `llm_enrich.py` (Riyansh) · `demo/` `plugin/` `pitch/` (Pranali)

## The day

Paste phase prompts from `PROMPTS.md` in order (1 → 4).

Before **every** commit:

```bash
cd backend && uv run python smoke_test.py
```

Green → ship. Red → paste the error back to the agent. **Never push failing code.**

Expected results never change:
`sales_email` → 3 violations · `vendor_invoice` → CRITICAL PAYMENT_REDIRECTION +
2 CONTRACT_OVERAGE · `support_reply` → 2 PROMISE_BREACH · `clean_email` → CLEAN

## Stuck? In order:

1. Re-run smoke test, read the error
2. `git diff` — did the agent break an existing check?
3. Re-paste the prompt with the error appended
4. Tag Riyansh — never blocked >10 min
