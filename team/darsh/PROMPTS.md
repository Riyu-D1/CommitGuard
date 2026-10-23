# Darsh — Agent Prompts (the full rules engine + actions build)

> **BASELINE EXISTS:** `rules.py`, `actions.py`, `company_brain.json`,
> `smoke_test.py`, `bench.py`, `seed_audit.py` are all built and working.
> Your prompts EXTEND them — the engine has 8 checks today; your job is rules
> v2, dedupe, context filtering, promises, and brain data. Never delete existing
> checks — only add.

**How to use:** work top-to-bottom through the phases. Paste each prompt into your
agent IN FULL — self-contained, no prior context needed. After every prompt run
the verification it specifies. **Golden rule: `cd backend && uv run python
smoke_test.py` must be green before every commit.** Not green → paste the error
back to the agent → do not move on.

**Your files:** `backend/rules.py`, `backend/actions.py`, `backend/company_brain.json`,
`backend/smoke_test.py`, `backend/bench.py`.
**Never touch:** `backend/main.py` (frozen), `backend/llm_enrich.py`, `demo/`,
`plugin/`, `pitch/`, `backend/scenarios.json` (Pranali's).

**Smoke test must always show:** sales_email → FINANCIAL_POLICY + MARGIN_BREACH +
TREASURY_LOCK · vendor_invoice → CRITICAL PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE ·
support_reply → 2 PROMISE_BREACH · clean_email → CLEAN.

## Ship ritual — after EVERY prompt verifies green

```bash
git checkout -b darsh/phase<N>
git add -A && git commit -m "phase <N> — <what it did>"
git push -u origin darsh/phase<N>
gh pr create --fill --base main        # or click the link git prints
```

| Phase → | Prompt(s) | Branch |
|---|---|---|
| 1 | A | `darsh/phase1` |
| 2 | B | `darsh/phase2` |
| 3 | C + D | `darsh/phase3` |
| 4 | F (+G if time) | `darsh/phase4` |

Then post "phase N up" in chat and **wait for all three merges before the next
phase** (Riyansh merges — don't merge your own).

---

# PHASE 1 — Rules engine v2 (from 10:45, ship as `darsh/phase1`)
Goal: the demo's "wow" — fraud detection rules that fire on realistic text.

## Prompt A — Three fraud-detection rules + tests

```
You are building part of CommitGuard: a compliance firewall that checks drafts and
invoices against a "company brain" JSON. `backend/rules.py` is a deterministic
rules engine: each check is `check_x(text: str, brain: dict) -> list` returning
violation dicts built with `_v(category, severity, issue, correction, evidence,
span=None, fix=None)`, registered in ALL_CHECKS at the bottom. brain is the parsed
backend/company_brain.json (read it to see the shape: financial_rules,
signed_contracts, engineering_status, people).

READ `backend/rules.py` COMPLETELY FIRST. Match its style exactly — compact code,
regex-based, no comments, same helper usage.

TASK: add these three checks and register them in ALL_CHECKS (order: keep invoice
fraud checks adjacent to check_bank_details if it helps readability):

1. check_duplicate_invoice
   - Regex for invoice numbers: r"(?i)\b(?:invoice|inv)[\s#:.-]*([A-Z]{1,5}-?\d{3,})\b"
   - If the SAME normalized invoice id (uppercased) appears 2+ times in the text:
     ONE CRITICAL violation, category "DUPLICATE_INVOICE", issue
     "Invoice <id> appears <count> times — classic duplicate-payment fraud",
     correction "Verify against AP records before paying — never pay the same
     invoice twice", evidence {"brain_key": "audit.seen_invoices", "expected":
     "unique invoice id", "found": "<id> x<count>"}, span covering the second
     occurrence.

2. check_sender_domain
   - Extract emails with r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)"
   - For the FIRST signed_contracts vendor whose name appears in text (reuse
     _find_vendor): derive the expected domain token = vendor's first word
     lowercased, stripped of ltd/limited/inc/gmbh/llp. If any email's domain does
     NOT contain that token -> HIGH violation, category "PHISHING_SIGNAL", issue
     "Sender domain <domain> does not match <vendor>'s expected domain pattern",
     correction "Confirm the sender is genuinely the vendor — call a known
     contact before paying", evidence {"brain_key": "signed_contracts[<vendor>].
     vendor_name", "expected": "domain containing '<token>'", "found": "<domain>"},
     span on the email.

3. check_urgency_payment
   - urgency regex: r"(?i)\b(urgent(?:ly)?|asap|immediately|right away|today only|
     before (?:eod|end of day|close of business|cob)|time[- ]sensitive)\b"
   - payment regex: r"(?i)\b(payment|pay|bank|iban|transfer|wire|account details|
     remit|sort code)\b"
   - If BOTH match -> HIGH violation, category "PAYMENT_REDIRECTION", issue
     "Urgency combined with payment instructions is the #1 invoice-fraud pattern",
     correction "Slow down — verify out-of-band before paying anything urgent",
     evidence {"brain_key": "financial_rules.treasury_lock", "expected":
     "standard verified payment process", "found": "urgent payment request"}.

THEN update `backend/smoke_test.py`: keep the existing SCENARIOS loop exactly as
is, and BELOW it add a TEST_CASES list of dicts [{"name":..., "text":...,
"expect_category":...}, ...] that runs the same verify path and asserts each new
check fires (print "PASS"/"FAIL" per case, exit nonzero on any FAIL):
- dup: "Re: INVOICE #CS-1187 — please re-pay INVOICE #CS-1187 to our new account"
  -> DUPLICATE_INVOICE
- domain: invoice text mentioning CloudScale Ltd with "From: accounts@cloudscale-billing.net"
  -> PHISHING_SIGNAL
- urgency: "URGENT: update payment to our new bank details before end of day"
  -> PAYMENT_REDIRECTION (or PAYMENT_REDIRECTION present among violations)

VERIFY: run `uv run python smoke_test.py` — original 4 scenarios unchanged AND
all new TEST_CASES print PASS. Show me the full output.
```

---

# PHASE 2 — Actions hardening (after Phase 1 merges, ship `darsh/phase2`)

## Prompt B — actions.py: dedupe + richer audit

```
Context: CommitGuard backend. `backend/actions.py` (mine) contains execute_action(),
audit(), read_audit(). `round_staging_queue.json` is the mock Round Treasury queue.
Do NOT touch main.py, rules.py, llm_enrich.py.

TASK:
1. STAGE_INVOICE dedupe: extract an invoice id — try payload["invoice"] first,
   else regex r"(?i)\b(?:invoice|inv)[\s#:.-]*([A-Z]{1,5}-?\d{3,})\b" on
   payload.get("text",""). Normalize (uppercase). Scan existing queue entries the
   same way (check each entry's "invoice" field or its "text"). If the id already
   exists: still audit with result "duplicate_stage_attempt", and return
   {"success": true, "message": "Invoice <id> already staged in Round queue"} —
   do NOT append.
2. Enrich audit(): every entry should also store "context_type" when present in
   payload and "violation_count" when payload carries a "violations" list
   (len of it).
3. read_audit(): add optional param action_type — filter entries where
   entry.action_type == action_type before applying limit.
VERIFY: curl POST /execute-action STAGE_INVOICE twice with the same
{"invoice":"CS-1187"} payload — second returns "already staged" and the queue
file has ONE entry; GET /audit-log?limit=5 shows both attempts with distinct
results. Show outputs.
```

# PHASE 3 — Context filtering + promises + brain (after Phase 2 merges, ship `darsh/phase3`)

## Prompt C — Context-aware rule filtering in rules.py

```
Context: `backend/rules.py` (mine). run_rules(text, brain, context_type=None)
already receives context_type from main.py but ignores it. Possible context_type
values: "outgoing_email", "slack_message", "incoming_invoice".

TASK:
1. Near ALL_CHECKS add a CONTEXTS dict mapping each check function to the set of
   contexts it applies to:
   - invoice-only ({"incoming_invoice"}): check_bank_details,
     check_amounts_vs_contract, check_duplicate_invoice
   - outgoing-only ({"outgoing_email", "slack_message"}): check_payment_terms,
     check_discount_cap, check_treasury_lock, check_feature_claims,
     check_unverified_promise (if defined)
   - universal (all three): check_urgency_payment, check_sender_domain,
     check_large_commitment, check_refund_credits, and DEFAULT for anything
     missing from the dict.
2. run_rules: when context_type is set, skip checks whose CONTEXTS set doesn't
   include it; context_type=None -> run all. Track skipped vs run so
   `len(ALL_CHECKS)` semantics in meta.checks_run stay meaningful (report count
   of checks actually run — do this by returning violations only; the caller
   computes nothing else, so just keep behavior clean).
   IMPORTANT: keep run_rules' return type (list of violations) unchanged.
3. Add to smoke_test.py TEST_CASES: a text containing "Net-60" sent with
   context_type "incoming_invoice" must produce NO FINANCIAL_POLICY violation
   (assert absence); the same text with "outgoing_email" must produce it.
VERIFY: `uv run python smoke_test.py` — all previous PASS plus the new
context-filter cases. Show output.
```

---

## Prompt D — Unverified-promise rule

```
Context: `backend/rules.py` (mine — read first, match style, register in
ALL_CHECKS and add to CONTEXTS as outgoing-only if CONTEXTS exists).

Add check_unverified_promise:
- commitment regex: r"(?i)\b(we(?:'| wi)ll|we promise|we guarantee|i can commit|
  rest assured|count on us)\b"
- deadline regex within 60 chars after it: r"(?i)\b(by|before|within|no later
  than)\s+(?:end of (?:week|month|quarter)|tomorrow|next (?:week|month)|(?:mon|
  tues|wednes|thurs|fri|satur|sun)day|\d{1,2}\s?(?:days?|weeks?|hours?))\b"
- If both match: check whether text mentions any engineering_status feature
  (word-overlap like check_feature_claims) or any signed_contracts vendor
  (_find_vendor). If NO backing entry -> MEDIUM violation, category
  "UNVERIFIED_PROMISE", issue "Deadline commitment has no backing entry in the
  company brain", correction "Get it into the brain (engineering status or
  contract) or soften to a non-committal estimate before sending", evidence
  {"brain_key": "engineering_status|signed_contracts", "expected":
  "backing entry exists", "found": "no matching entry"}.
- If a backing entry DOES exist -> no violation.

Add TEST_CASES in smoke_test.py:
- "We will definitely have multi-region support live by Friday." -> fires
- "We will deploy the Stripe Webhook Latency Fix by Friday." -> does NOT fire
  (backed by engineering_status)
VERIFY: smoke green, all previous results unchanged. Show output.
```

## Prompt E — Brain enrichment

```
Context: `backend/company_brain.json` (mine) — the demo's knowledge base:
financial_rules, signed_contracts (CloudScale Ltd, Northwind Analytics),
engineering_status (Stripe fix merged; SOC 2 + SSO NOT done), people.
Pranali owns scenario TEXT; you own brain DATA.

TASK — enrich without breaking existing keys (all money in GBP):
1. "approval_chain": [{"over_gbp": 10000, "approver": "Finance Lead", "channel":
   "#finance-approvals"}, {"over_gbp": 25000, "approver": "Amara Osei",
   "channel": "#cfo-direct"}]
2. New signed_contract: {"vendor_name": "DataForge GmbH",
   "approved_monthly_retainer_gbp": 4800, "hourly_rate_gbp": 110,
   "bank_iban": "GB33NWBK11223344"} (plausible-looking GB IBAN format)
3. New engineering_status: {"feature": "Mobile app beta", "status": "In QA, no
   release date committed", "date": "2026-10-18"}
4. "blocked_topics": ["roadmap dates", "discounts above cap", "unreleased
   security certifications", "competitor comparisons in writing"]
Keep the file under ~75 lines, valid JSON, same 2-space indent style.
VERIFY: `uv run python smoke_test.py` — all results identical to before.
Then POST /brain/reload and GET /brain to confirm the new keys load. Show output.
```

# PHASE 4 — Stretch (after Phase 3 merges, ship `darsh/phase4`)

## Prompt F — Latency benchmark (produces the "<5ms" demo stat — NOTE: bench.py already exists; run it, paste the table into the pitch deck, extend only if you want)

```
Context: `backend/rules.py`. TASK: create `backend/bench.py`:
- Loads backend/scenarios.json + company_brain.json, runs rules.run_rules over
  each scenario text 200 times (context_type from the scenario), records wall
  time per run.
- Prints a table: scenario | avg_ms | p95_ms | violations_found; then a summary
  line: total checks across scenarios, overall avg, and "all checks complete in
  <5ms" if true.
- Pure stdlib (time, statistics, json, pathlib). No dependencies.
VERIFY: `uv run python bench.py` — show me the table. If anything is slow
(>10ms avg), tell me which check is the bottleneck.
```

---

# PHASE 4 (continued) — claim shared-queue items in TEAM_PLAN first

## Prompt G — Audit seed for the demo

```
Context: backend writes audit entries as JSON lines to backend/audit_log.jsonl.
TASK: create `backend/seed_audit.py` that appends 5 realistic, varied audit
entries spanning action types (SEND_APPROVED, APPLY_REWRITE_AND_LOG,
APPROVE_OVERRIDE with a plausible reason like "client deadline — CFO aware via
slack", STAGE_INVOICE, ESCALATE_FRAUD) with timestamps spread across today,
using the same entry shape as actions.audit() (reuse it — import actions and
call audit()). Run it once so the Inspector page isn't empty at demo time;
show `GET /audit-log?limit=10` output. NOTE: audit_log.jsonl is gitignored —
do not commit it.
```

## Prompt H — Risk score helper

```
Context: `backend/rules.py`. TASK: add `risk_score(violations) -> int` returning
0-100 where CRITICAL=40, HIGH=25, MEDIUM=10, LOW=5 summed and capped at 100.
Export it via __all__ if present. Add a TEST_CASE asserting the vendor_invoice
scenario scores >=80 and clean_email scores 0. Show smoke output.
```
