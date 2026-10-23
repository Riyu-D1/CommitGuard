# Person 2 — Agent Prompts

Paste into your coding agent one task at a time. Everything stays in `backend/`.
Contract reference: `CONTRACT.md` at repo root — treat it as immutable except for additive fields.

---

## Prompt A — Rules v2 (use ~11:15)

```
You are working on CommitGuard, a pre-send compliance firewall. In `backend/` there is
`rules.py` — a deterministic rules engine where each check is a function
(text: str, brain: dict) -> list[violation dict], registered in ALL_CHECKS.
Violations MUST include: category, severity (LOW/MEDIUM/HIGH/CRITICAL), issue,
correction, evidence {brain_key, expected, found}, and optionally span {text,start,end}
plus fix (replacement text) when a span exists. Read the file first and match its style
exactly — compact, no comments, regex-based.

Add these checks to rules.py:

1. check_duplicate_invoice: maintain no state — instead detect invoice-shaped text
   (invoice number pattern like "INVOICE #CS-1187" or "Inv-1234") and look for a
   repeated invoice number appearing twice in the same text → CRITICAL
   DUPLICATE_INVOICE. Keep it stateless for now.
2. check_sender_domain: find email addresses in text; if a vendor from
   signed_contracts is mentioned AND an email's domain doesn't match the vendor name
   (normalize: strip ltd/limited/inc, compare first token) → HIGH PHISHING_SIGNAL
   with evidence showing expected vs found domain.
3. check_urgency_pattern: regex for urgency phrases ("urgent", "asap", "immediately",
   "today only", "before end of day") co-occurring with payment/bank keywords →
   bump to HIGH PAYMENT_REDIRECTION, issue explains urgency+bank-change is the
   classic fraud pattern.
4. check_unverified_promise: detect commitment language ("we will", "we'll",
   "guarantee", "promise") followed by a deadline ("by Friday", "by <date>",
   "next week") that isn't supported by any brain entry → MEDIUM UNVERIFIED_PROMISE,
   correction: "get it into the brain or soften the commitment".

Then extend backend/smoke_test.py with a test case per new check (add entries to a
test-only list, don't touch scenarios.json). Verify: `uv run python smoke_test.py`
all green, and rules stay under 50ms total (they print latency already).
```

## Prompt B — LLM enrichment tightening (use ~13:00)

```
Context: CommitGuard backend in `backend/`. `_llm_enrich()` in main.py calls
gpt-4o-mini with strict json_schema structured output to polish violations and
produce a full_rewrite. It already fails open (returns None → rules-only result).

Task — improve `_llm_enrich`:
1. Add `temperature=0` and keep the 8s timeout.
2. Change the schema: replace the loose `violations` array-of-object with the strict
   per-violation shape {category, severity, issue, correction, suggested_rewrite}
   (all required strings, suggested_rewrite may be "").
3. Prompt change: instruct the model to (a) preserve every deterministic violation
   verbatim unless factually wrong, (b) only ADD violations that cite a specific
   brain key, (c) write full_rewrite keeping the sender's greeting/sign-off/tone,
   fixing violations with minimal edits — never adding new commitments.
4. Merge logic: map LLM suggested_rewrite onto matching deterministic violations by
   category; use llm full_rewrite as top-level suggested_rewrite when present,
   else fall back to rules.apply_fixes.
5. Verify: run `uv run python smoke_test.py` with and without OPENAI_API_KEY set —
   both must produce sane output.
```

## Prompt C — Actions & brain hardening (use ~13:30)

```
Context: CommitGuard backend, `backend/main.py`. Endpoints: /verify-context,
/execute-action, /brain, /brain/reload, /audit-log, /scenarios, /.

Task:
1. STAGE_INVOICE dedupe: if a payload with the same invoice identifier (payload.invoice
   or an "INVOICE #X" pattern in payload.text) already exists in
   round_staging_queue.json, return success=true with message "already staged" and
   do not append.
2. Add GET /health → {"ok": true, "engine": "rules"|"rules+llm",
   "checks": <len(ALL_CHECKS)>, "brain_keys": <top-level keys>}.
3. Add POST /brain/reload edge case: if company_brain.json is malformed, keep the old
   brain and return {"reloaded": false, "error": <msg>} with 422 status — never crash
   the server mid-demo.
4. Update CONTRACT.md at repo root: append the new /health spec under the endpoints
   list. No other contract changes.
Verify each endpoint with curl; keep everything working offline (no API key needed).
```

## Prompt D — Brain data realism (use anytime as filler)

```
Context: CommitGuard `backend/company_brain.json` powers the demo. It currently has
financial_rules, signed_contracts (CloudScale, Northwind), engineering_status,
people. Task: enrich it for demo realism WITHOUT breaking existing keys:
- Add "approval_chain": [{min_gbp, approver, channel}] escalation ladder.
- Add one more signed_contract and one more engineering_status item that are clearly
  NOT done (fuel for PROMISE_BREACH demos).
- Add "blocked_topics" e.g. ["roadmap dates", "discounts > cap", "unreleased security
  certifications"] — descriptive only.
Keep the file under ~60 lines, valid JSON, values in GBP. Then run
`uv run python smoke_test.py` to confirm nothing broke.
```
