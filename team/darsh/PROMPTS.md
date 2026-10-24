# Darsh — backend rules + actions + data

**Your files:** `backend/rules.py`, `actions.py`, `company_brain.json`, `scenarios.json`, `smoke_test.py`, `bench.py`, `seed_audit.py`
**Never touch:** `backend/main.py`, `backend/llm_enrich.py` (Riyansh) · `demo/` `plugin/` `pitch/` (Pranali)

## The loop

```
1. Paste the phase prompt → VERIFY: cd backend && uv run python smoke_test.py → all pass, the 4 original results unchanged
2. git checkout -b darsh/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin darsh/phase<N> && gh pr create --fill
3. Post "phase N up" → wait for all 3 merges → next phase
```

---

## Phase 1 — fraud rules

```
In backend/rules.py, add 3 checks matching the existing style (evidence dict + span + registered in ALL_CHECKS):
1. DUPLICATE_INVOICE (CRITICAL): fires when text has an invoice number (e.g. INV-\d+) AND words like "already paid"/"duplicate"/"second request".
2. SENDER_DOMAIN_MISMATCH (HIGH): fires when text has "from:"/"reply-to:" with a domain not listed as a known sender domain in company_brain.json (add a known_sender_domains key to the brain if needed).
3. URGENT_PAYMENT_CHANGE (CRITICAL): fires when urgency words (urgent/immediately/today/EOD) appear within 120 chars of bank-detail words (IBAN/sort code/bank details/updated payment).
Add one smoke_test.py case per rule. The 4 existing scenario results must stay identical.
VERIFY: uv run python smoke_test.py → all pass.
```

## Phase 2 — actions hardening

```
In backend/actions.py only:
- Dedupe: same action_type + invoice identifier within 10 minutes → return {success: false, error: "duplicate"}, still write an audit entry.
- ISO timestamp on every audit entry if missing.
- read_audit(): support ?type= and ?status= query filters.
VERIFY: smoke green + one curl POST /execute-action + GET /audit-log?limit=3 shows entries.
```

## Phase 3 — context filtering + promise rule

```
In backend/rules.py:
- run_rules already receives context_type. Add a CONTEXTS map: invoice rules fire only on "incoming_invoice"; payment/promise rules only on outgoing_*/general; CRITICAL rules always fire.
- Add PROMISE_BREACH (MEDIUM): fires when text claims a feature/status that contradicts company_brain.json engineering_status.
Add 2 smoke tests. Keep the 4 original results identical.
VERIFY: uv run python smoke_test.py → all pass.
```

## Phase 4 — perf + polish

```
- uv run python bench.py → put the avg/p95 numbers in your PR description (Pranali needs them for the pitch).
- uv run python seed_audit.py once so the Inspector isn't empty.
- Optional: add a risk_score (0-100) to each violation.
VERIFY: smoke green; the 4 original results identical.
```
