# Darsh — Agent Prompts

Run your agent continuously: paste prompt IN FULL → it codes → you run
`cd backend && uv run python smoke_test.py` → green? next prompt : paste error back.

Your files: `backend/rules.py`, `backend/actions.py`, `backend/company_brain.json`,
`backend/smoke_test.py`, `backend/bench.py`. NEVER touch `main.py`,
`llm_enrich.py`, `demo/`, `plugin/`, `scenarios.json`.

---

## Prompt A — Three new rules (~10:45)

```
You are working on CommitGuard: a compliance firewall that checks messages against
a "company brain" JSON. `backend/rules.py` is a rules engine: each check is a
function `check_x(text: str, brain: dict) -> list` returning violation dicts built
with the `_v(category, severity, issue, correction, evidence, span=None, fix=None)`
helper, registered in ALL_CHECKS at the bottom. Read the whole file first and
match its style exactly — compact, regex-based, no comments.

Add these three checks and register them in ALL_CHECKS:

1. check_duplicate_invoice: detect invoice-number patterns (regex like
   r"(?i)\b(?:invoice|inv)[\s#:]*([A-Z]{1,4}-?\d{3,})\b"). If the SAME invoice
   number appears more than once in the text → one CRITICAL violation, category
   DUPLICATE_INVOICE, issue "Invoice <n> appears <count> times — classic
   duplicate-payment fraud", correction "Verify against AP records before paying",
   evidence {"brain_key": "seen_invoices", "expected": "unique", "found":
   "<n> x<count>"}.

2. check_sender_domain: extract emails (r"[\w.+-]+@[\w-]+\.[\w.]+"). For each
   signed_contracts vendor mentioned in text (reuse _find_vendor), if an email
   domain's first meaningful token (before dots, lowercased, strip
   ltd/limited/inc/gmbh) does NOT fuzzy-match the vendor's first word → HIGH
   violation, category PHISHING_SIGNAL, issue "Sender domain <d> does not match
   <vendor>'s expected domain", correction "Confirm the sender is genuinely the
   vendor before paying", evidence {"brain_key":
   "signed_contracts[<vendor>].vendor_name", "expected": "<vendor>", "found":
   "<domain>"}.

3. check_urgency_payment: if text matches urgency words (r"(?i)\b(urgent|urgently|
   asap|immediately|right away|today only|before (?:eod|end of day|close of
   business))\b") AND payment/bank words (r"(?i)\b(payment|pay|bank|iban|
   transfer|wire|account details)\b") → HIGH violation, category
   PAYMENT_REDIRECTION, issue "Urgency combined with payment instructions is the
   top invoice-fraud pattern", correction "Slow down — verify out-of-band before
   paying", evidence {"brain_key": "financial_rules.treasury_lock", "expected":
   "verified payment process", "found": "urgent payment request"}.

Then in `backend/smoke_test.py`, ADD a TEST_CASES list (don't replace SCENARIOS)
with one text triggering each new check:
- duplicate: "...INVOICE #CS-1187... please re-pay INVOICE #CS-1187 to new details"
- domain: invoice text mentioning CloudScale with "From: accounts@cloudscale-billing.net"
- urgency: "URGENT: please update payment to new bank account before end of day"
Run `uv run python smoke_test.py` — the 4 original scenarios must be unchanged
AND all 3 new cases fire. Show me the output.
```

## Prompt B — Actions dedupe + context-aware rules (~13:00)

```
Context: CommitGuard backend. `backend/actions.py` (mine) holds execute_action()
+ audit helpers; `backend/rules.py` (mine) holds run_rules(text, brain,
context_type=None) — the context_type param already arrives from main.py but is
currently unused. Do NOT touch main.py or llm_enrich.py.

Task:
1. STAGE_INVOICE dedupe in actions.py: extract an invoice id — payload["invoice"]
   first, else regex r"(?i)\b(?:invoice|inv)[\s#:]*([A-Z]{1,4}-?\d{3,})\b" on
   payload.get("text",""). If an entry with the same extracted id already exists
   in round_staging_queue.json → return {"success": true, "message": "Invoice
   <id> already staged in Round queue"} WITHOUT appending (still audit it as
   result "duplicate_stage_attempt").
2. Context-aware filtering in rules.py: tag each check with the context_types it
   applies to via a CONTEXTS dict {check_fn: {"outgoing_email","slack_message",
   "incoming_invoice"}}. Invoice-only checks: check_bank_details,
   check_amounts_vs_contract, check_duplicate_invoice → apply only to
   incoming_invoice. Outgoing-only: check_payment_terms, check_discount_cap,
   check_treasury_lock, check_feature_claims, check_unverified_promise (if it
   exists). Universal: check_urgency_payment, check_sender_domain,
   check_large_commitment, check_refund_credits → all contexts. run_rules skips
   non-matching checks when context_type is set; context_type=None runs all.
   Put CONTEXTS near ALL_CHECKS, derive defaults sensibly if a check is missing.
3. Append a line to CONTRACT.md (repo root) endpoints list: "GET /health → {ok,
   engine, checks, brain_keys}". Nothing else changes in the contract.
Verify: smoke_test.py still fully green (context_type passes through), plus curl
a STAGE_INVOICE twice — second returns "already staged". Show outputs.
```

## Prompt C — Unverified-promise rule (~13:45)

```
Context: CommitGuard `backend/rules.py` — same structure as before (read it
first, match style, register in ALL_CHECKS, add to CONTEXTS as outgoing-only if
that exists).

Add check_unverified_promise: detect commitment language — regex
r"(?i)\b(we(?:'| wi)ll|we promise|we guarantee|i can commit|rest assured)\b
.{0,60}\b(by|before|within)\s+(friday|monday|tuesday|wednesday|thursday|\d{1,2}
\s?(?:days?|weeks?)|end of (?:week|month|quarter)|tomorrow)\b". If it matches AND
the text doesn't mention any engineering_status feature or signed_contracts
vendor (reuse _find_vendor + a feature-word check like check_feature_claims uses)
→ MEDIUM violation, category UNVERIFIED_PROMISE, issue "Commitment with a
deadline has no backing entry in the company brain", correction "Get it into the
brain (engineering status or contract) or soften to a non-committal estimate",
evidence {"brain_key": "engineering_status|signed_contracts", "expected":
"backing entry", "found": "no matching entry"}.

Add a TEST_CASE to smoke_test.py: "We will definitely have multi-region support
live by Friday." → fires. Same phrasing mentioning "Stripe Webhook Latency Fix"
→ does NOT fire. Run smoke_test.py, show output — all previous results unchanged.
```

## Prompt D — Brain enrichment (~14:00)

```
Context: `backend/company_brain.json` (mine) powers the demo: financial_rules,
signed_contracts (CloudScale, Northwind), engineering_status (Stripe fix merged;
SOC 2 + SSO NOT done), people. Pranali owns scenario TEXT — you own brain DATA.

Task — enrich without breaking existing keys (GBP values):
- "approval_chain": [{"over_gbp": 10000, "approver": "Finance Lead", "channel":
  "#finance-approvals"}, {"over_gbp": 25000, "approver": "Amara Osei", "channel":
  "#cfo-direct"}]
- one more signed_contract ("DataForge GmbH", retainer 4800, hourly 110,
  plausible GB IBAN)
- one more engineering_status clearly NOT done ("Mobile app beta" — "In QA, no
  release date committed")
- "blocked_topics": ["roadmap dates", "discounts above cap", "unreleased security
  certifications"]
Keep file valid JSON, under ~75 lines. Then `uv run python smoke_test.py` —
results must be unchanged. Show output.
```

## Prompt E — Latency benchmark (stretch)

```
Context: CommitGuard `backend/rules.py`. Task: create `backend/bench.py` — a
script that runs rules.run_rules over every scenario in backend/scenarios.json
200 times each and prints per-scenario avg/p95 latency in ms plus total checks
count. Pretty-print a table. Purpose: demo stat "all checks run in <5ms". Run it,
show me the numbers — if anything is slow, tell me which check.
```
