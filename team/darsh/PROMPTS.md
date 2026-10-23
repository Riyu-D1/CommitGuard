# Darsh — Agent Prompts

Paste each prompt into your coding agent IN FULL, one at a time. Each is
self-contained — the agent needs nothing else. Work only inside `backend/`.

After EVERY prompt finishes, run: `cd backend && uv run python smoke_test.py`
All lines must show expected results. If anything fails, paste the error back to
the agent and say "fix this". Never commit failing code.

---

## Prompt A — Three new rules (~11:15)

```
You are working on CommitGuard: a compliance firewall that checks messages against
a "company brain" JSON. In `backend/rules.py` there is a rules engine: each check is
a function `check_x(text: str, brain: dict) -> list` returning violation dicts built
with the `_v(category, severity, issue, correction, evidence, span=None, fix=None)`
helper. Checks are registered in the ALL_CHECKS list at the bottom. Read the whole
file first and match its style exactly — compact, regex-based, no comments.

Add these three checks and register them in ALL_CHECKS:

1. check_duplicate_invoice: detect invoice number patterns (regex like
   r"(?i)\b(?:invoice|inv)[\s#:]*([A-Z]{1,4}-?\d{3,})\b"). If the SAME invoice number
   appears more than once in the text → one CRITICAL violation, category
   DUPLICATE_INVOICE, issue "Invoice <n> appears multiple times — classic
   duplicate-payment fraud", correction "Verify against AP records before paying",
   evidence {"brain_key": "seen_invoices", "expected": "unique", "found": "<n> x<count>"}.

2. check_sender_domain: extract emails (r"[\w.+-]+@[\w-]+\.[\w.]+"). For each
   signed_contracts vendor mentioned in text (reuse _find_vendor), if an email
   domain's first token (before dots, lowercased, strip ltd/limited/inc/gmbh) does
   NOT fuzzy-match the vendor's first word → HIGH violation, category
   PHISHING_SIGNAL, issue "Sender domain <d> does not match <vendor>'s expected
   domain", correction "Confirm the sender is genuinely the vendor", evidence
   {"brain_key": "signed_contracts[<vendor>].vendor_name", "expected": "<vendor>",
   "found": "<domain>"}.

3. check_urgency_payment: if text matches urgency words (r"(?i)\b(urgent|urgently|
   asap|immediately|right away|today only|before (?:eod|end of day|close of business))\b")
   AND payment/bank words (r"(?i)\b(payment|pay|bank|iban|transfer|wire|account details)\b")
   → HIGH violation, category PAYMENT_REDIRECTION, issue "Urgency combined with
   payment instructions is the top invoice-fraud pattern", correction "Slow down —
   verify out-of-band before paying", evidence {"brain_key":
   "financial_rules.treasury_lock", "expected": "verified payment process",
   "found": "urgent payment request"}.

Then in `backend/smoke_test.py`, ADD (don't replace) a TEST_CASES list exercised the
same way as SCENARIOS: one text triggering each new check. Examples:
- duplicate: "...INVOICE #CS-1187... please re-pay INVOICE #CS-1187 at new details"
- domain: invoice text mentioning CloudScale with "From: accounts@cloudscale-billing.net"
- urgency: "URGENT: please update payment to new bank account before end of day"

Run `uv run python smoke_test.py`. All original 4 scenarios must still produce their
original results AND the 3 new cases must fire. Show me the output.
```

## Prompt B — Actions hardening (~13:00)

```
Context: CommitGuard backend `backend/main.py` (FastAPI). Relevant endpoint:
POST /execute-action handles action_type values; STAGE_INVOICE appends payload to
`round_staging_queue.json`; every action appends to `audit_log.jsonl` via `_audit()`.
Do NOT touch `_llm_enrich` or rules.py — different owner.

Task:
1. STAGE_INVOICE dedupe: extract an invoice id from payload — check payload["invoice"]
   first, else regex r"(?i)\b(?:invoice|inv)[\s#:]*([A-Z]{1,4}-?\d{3,})\b" on
   payload.get("text",""). If that id already exists in round_staging_queue.json
   (match on the same extraction), return {"success": true, "message":
   "Invoice <id> already staged in Round queue"} WITHOUT appending.
2. Add GET /health returning {"ok": true, "engine": "rules" or "rules+llm" depending
   on whether _client is set, "checks": len(rules.ALL_CHECKS), "brain_keys":
   list(COMPANY_BRAIN.keys())}.
3. Harden POST /brain/reload: wrap load_brain() in try/except; on failure return
   HTTP 422 {"reloaded": false, "error": "<msg>"} and KEEP the old brain — the
   server must never lose its brain mid-demo.
4. Append a "GET /health" line to the endpoints list in CONTRACT.md (repo root).
   Nothing else in the contract changes.

Verify with curl: start `uv run uvicorn main:app --port 8000`, POST two identical
STAGE_INVOICE payloads (second must say "already staged"), GET /health, and POST
/brain/reload after temporarily breaking company_brain.json (then restore it).
Show me each response.
```

## Prompt C — Unverified-promise rule (stretch, ~13:45)

```
Context: CommitGuard `backend/rules.py` — same structure as before (check functions
registered in ALL_CHECKS, _v() helper). Read it first, match style.

Add check_unverified_promise: detect commitment language — regex
r"(?i)\b(we(?:'| wi)ll|we promise|we guarantee|i can commit|rest assured)\b.{0,60}
\b(by|before|within)\s+(friday|monday|tuesday|wednesday|thursday|\d{1,2}\s?(?:days?|
weeks?)|end of (?:week|month|quarter)|tomorrow)\b". If it matches AND the text
doesn't mention any engineering_status feature or signed_contracts vendor (reuse
_find_vendor + a small feature-word check like check_feature_claims uses) → MEDIUM
violation, category UNVERIFIED_PROMISE, issue "Commitment with a deadline has no
backing entry in the company brain", correction "Get it into the brain (engineering
status or contract) or soften to a non-committal estimate", evidence
{"brain_key": "engineering_status|signed_contracts", "expected": "backing entry",
"found": "no matching entry"}.

Add one test case to smoke_test.py: "We will definitely have multi-region support
live by Friday." → must fire. A text mentioning "Stripe Webhook Latency Fix" with
the same phrasing must NOT fire. Run smoke_test.py, show output — all previous
results must be unchanged.
```

## Prompt D — Brain data enrichment (filler task, anytime)

```
Context: `backend/company_brain.json` powers the CommitGuard demo. It has
financial_rules, signed_contracts (CloudScale, Northwind), engineering_status
(Stripe fix merged; SOC 2 and SSO NOT done), people. Pranali owns scenario TEXT —
you own this brain DATA. Coordinate with her before adding anything her scenarios
depend on.

Task — enrich without breaking existing keys (values in GBP):
- Add "approval_chain": [{"over_gbp": 10000, "approver": "Finance Lead",
  "channel": "#finance-approvals"}, {"over_gbp": 25000, "approver": "Amara Osei",
  "channel": "#cfo-direct"}]
- Add one more signed_contract (e.g., "DataForge GmbH", retainer 4800, rate 110,
  plausible GB IBAN)
- Add one more engineering_status item clearly NOT done (e.g., "Mobile app beta" —
  "In QA, no release date committed")
Keep the file under ~70 lines, valid JSON. Then `uv run python smoke_test.py` —
all results must be unchanged. Show output.
```
