# Darsh — agent prompts (backend: rules, actions, brain, data)

**How to use (every phase):**
1. Fresh branch from latest main, every time (squash-merged branches must not be reused):
   `git checkout main && git pull && git checkout -b darsh/phase<N>`
2. Paste ONE phase's entire fenced block into Codex/Devin. When it says done, run the VERIFY commands yourself.
3. Ship: `git add -A && git commit -m "darsh phase <N>" && git push -u origin HEAD && gh pr create --fill`
   (If Devin opened the PR itself, skip this step.) Post "darsh phase N up" in chat.
4. As soon as YOUR PR is merged, start the next phase. **Do not wait for teammates.** Lanes never overlap.

**Targets:** P1 merged by 12:00 · P2 by 12:40 · P3 by 13:30 · P4 by 14:15. **Don't start P4 after 13:45**; Riyansh then runs the existing bench/seed scripts by hand at 14:30.

**If the AI claims done but a VERIFY fails, or stops mid-task, reply with exactly:**
`Continue — complete every remaining numbered item, then run all VERIFY commands again.`

**Your files:** `backend/rules.py`, `backend/actions.py`, `backend/company_brain.json`,
`backend/scenarios.json`, `backend/smoke_test.py`, `backend/bench.py`, `backend/seed_audit.py`
**Never touch:** `backend/main.py`, `backend/llm_enrich.py` (Riyansh) · `demo/` `plugin/` `pitch/` (Pranali)

---

## Phase 1 — fraud rules engine v2

```
You are a senior backend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first — they describe the project and API). CommitGuard is a pre-send compliance firewall: a deterministic rules engine in backend/rules.py checks draft text and invoice text against backend/company_brain.json. It is NOT an LLM — plain regex/dictionary logic, and every violation must cite auditable evidence.

YOUR FILES ONLY: backend/rules.py, backend/company_brain.json, backend/smoke_test.py. Do NOT modify any other file.

STEP 0 — read backend/rules.py completely. Match its exact conventions: module-level compiled regexes where useful, a _v(category, severity, issue, correction, evidence, span=None, fix=None) constructor, checks registered in the ALL_CHECKS list, functions take (text, brain) and return a list of violation dicts.

TASK — make the smoke test a real gate, then add these 3 new check functions and register them in ALL_CHECKS:

0. SMOKE TEST GATE (do this FIRST, before touching rules.py). backend/smoke_test.py currently only prints, so it can never fail. Keep its printing, and add:
   - BASELINE = {"sales_email": ["FINANCIAL_POLICY","MARGIN_BREACH","TREASURY_LOCK"], "vendor_invoice": ["CONTRACT_OVERAGE","CONTRACT_OVERAGE","PAYMENT_REDIRECTION"], "support_reply": ["PROMISE_BREACH","PROMISE_BREACH"], "clean_email": []}
   - For each of those 4 keys compare sorted([v["category"] for v in violations]) to the expected list; also require that vendor_invoice contains a PAYMENT_REDIRECTION with severity CRITICAL and clean_email has status CLEAN. Any other scenario keys in scenarios.json are printed but not asserted (a 5th scenario may be added later).
   - A small helper for inline rule cases: expect(name, text, context_type, must_have=set(), must_not_have=set()), which calls main.verify_context and checks categories.
   - At the end print "ALL PASS" and exit 0, or print every failure and sys.exit(1).
   - Run it now: it must print ALL PASS on the unchanged rules before you continue.

1. check_duplicate_invoice(text, brain) — category DUPLICATE_INVOICE, severity CRITICAL
   - FIRES WHEN: text contains an invoice number (regex: \b[A-Z]{2,4}[-\s]?\d{3,}\b which matches INV-1042, CS-1187, PO 9918) AND text also contains duplicate-payment language: "already paid", "duplicate", "second request", "paid twice", "settled last", "resending", "previously paid"
   - Issue text: "Invoice {inv} is flagged as a possible duplicate payment request."
   - Correction: "Verify against the payment ledger before approving — duplicate invoice fraud is common."
   - Evidence: {"brain_key": "payment_ledger", "expected": "no prior payment for this invoice", "found": <the duplicate-language phrase matched>}
   - Span: the matched invoice number

2. check_sender_domain(text, brain) — category SENDER_DOMAIN_MISMATCH, severity HIGH
   - First add to backend/company_brain.json a new top-level key: "known_sender_domains": ["cloudscale.co.uk", "northwind-analytics.com", "yourcompany.com"]
   - FIRES WHEN: text contains "from:" or "reply-to:" followed by an email address (case-insensitive regex: (?i)(?:from|reply-to):\s*\S+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})) AND the captured domain is NOT in known_sender_domains
   - Issue: "Sender domain '{domain}' is not a known supplier domain — possible impersonation/phishing."
   - Correction: "Verify the sender out-of-band before acting on this message."
   - Evidence: {"brain_key": "known_sender_domains", "expected": <the list>, "found": <domain>}
   - Span: the email address
   - If the vendor is also identified in the text (reuse _find_vendor), upgrade severity to CRITICAL and change the issue to "...claimed to be from {vendor} — this is a classic supplier-impersonation pattern."

3. check_urgent_payment_change(text, brain) — category URGENT_PAYMENT_CHANGE, severity CRITICAL
   - FIRES WHEN: an urgency word/phrase appears within 120 characters of a payment-detail word. Urgency set: urgent, immediately, asap, today, "by eod", "end of day", "time-sensitive", "before close". Payment-detail set: "iban", "sort code", "bank details", "account number", "updated payment", "new account", "payment details", "change of bank". Case-insensitive.
   - Issue: "Urgency combined with a payment-detail change is the #1 invoice-fraud pattern."
   - Correction: "Never process bank-detail changes under time pressure — verify out-of-band first."
   - Evidence: {"brain_key": "financial_rules.fraud_controls", "expected": "no urgency+bank-change combination", "found": "<urgency phrase> + <payment phrase>"}
   - Span: the window containing both phrases where feasible
   - Also add "fraud_controls" to company_brain.json financial_rules: "Urgency + bank-detail changes always require out-of-band verification."

4. Extend backend/smoke_test.py with ONE expect(...) case per new rule (a short inline text + the category that must appear), e.g. "INVOICE INV-1042 — second request, this was already paid" (incoming_invoice → DUPLICATE_INVOICE); "From: billing@cloudscale-payments.net\nCloudScale Ltd invoice attached" (incoming_invoice → SENDER_DOMAIN_MISMATCH, CRITICAL); "Urgent: please update our bank details today, new IBAN to follow" (slack_message → URGENT_PAYMENT_CHANGE). Do NOT change the 4 baseline expectations.

CONSTRAINTS:
- No new imports beyond `re`/`typing` already used; no external dependencies
- Every violation carries evidence with a real brain_key — never invent brain keys
- Keep function signatures identical to existing checks

WORKING RULES — follow exactly:
- Read every file you will modify completely BEFORE editing it.
- Work the numbered items IN ORDER and complete ALL of them — if one is already implemented, confirm it matches this spec and move on.
- Never silently skip an item — if truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete AND every VERIFY command produces the stated output. Before finishing, re-check each numbered item against your changes. Partial completion is a failure.
- FREEDOM: behaviors, category names, evidence shapes, and message strings in this spec are exact (they're the product contract). Everything else — helper structure, regex details, code organization, extra edge-case handling — is yours to improve. If you see a cleaner or more robust approach that passes the same VERIFY, take it, and note any spec deviation in your final summary.

VERIFY — run and paste output:
cd backend && uv run python smoke_test.py ; echo "exit=$?"
Expected: ALL PASS and exit=0 (4 baseline scenarios unchanged; 3 new cases fire their categories).
```

## Phase 2 — actions layer complete

```
You are a senior backend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). CommitGuard's backend/actions.py handles POST /execute-action: it stages invoices into backend/round_staging_queue.json (a mock Round Treasury pickup queue), escalates fraud to the CFO, logs overrides, and appends every action to backend/audit_log.jsonl via the audit() helper. backend/main.py calls actions.execute_action — you must NOT modify main.py.

YOUR FILES ONLY: backend/actions.py. Read it completely first and match its style (small module, stdlib only: json, uuid, datetime, pathlib, fastapi.HTTPException).

TASK — complete the actions layer:

1. DEDUPLICATION — implement _dedupe_key(action_type, payload) that produces a stable key: action_type + "|" + the invoice identifier found in payload (check keys in order: "invoice", "invoice_id", "id", "vendor" — use the first present; if none, return None meaning "not dedupeable"). In execute_action, BEFORE handling: scan audit_log.jsonl for any entry within the last 10 minutes (parse each line's "ts" ISO timestamp, compare to now UTC) with the same dedupe key. If found → return {"success": False, "error": "duplicate", "audit_log_id": <new audit id>, "message": "Duplicate action within 10 minutes — rejected and logged."} AND still append an audit entry {"action_type": action_type, "payload": payload, "result": "duplicate_rejected"}. Only dedupe STAGE_INVOICE and ESCALATE_FRAUD; other action types pass through.

2. TIMESTAMPS — ensure every audit entry has "ts" in ISO 8601 UTC (already partially done — make it consistent) and add "epoch_ms" (int, unix ms) for cheap sorting.

3. read_audit EXTENSION — change signature to read_audit(limit=20, type=None, result=None): when `type` is given, filter entries to that action_type; when `result` is given, filter to that result value. Both optional, applied before the limit slice; still newest first. Skip blank/corrupt lines instead of crashing. Document the params in the docstring. main.py ALREADY calls read_audit(limit, type=..., result=...) and falls back to read_audit(limit) on TypeError, so once this lands GET /audit-log?type=STAGE_INVOICE filters for real. Do not edit main.py.

4. STAGE_INVOICE polish — the staged queue entry should include the dedupe key field "invoice_ref" (the same identifier logic) so downstream consumers can join on it.

5. UNKNOWN ACTIONS — the valid action types are exactly SEND_APPROVED, APPLY_REWRITE_AND_LOG, APPROVE_OVERRIDE, STAGE_INVOICE, ESCALATE_FRAUD (CONTRACT.md). Any other action_type → raise HTTPException(400, f"Unknown action_type '{action_type}'"), and write nothing to the audit log. (Today an action_type of "BOGUS" returns success:true.)

WORKING RULES — follow exactly:
- Read every file you will modify completely BEFORE editing it.
- Work the numbered items IN ORDER and complete ALL of them — if one is already implemented, confirm it matches this spec and move on.
- Never silently skip an item — if truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete AND every VERIFY command produces the stated output. Before finishing, re-check each numbered item against your changes. Partial completion is a failure.
- FREEDOM: behaviors, category names, evidence shapes, and message strings in this spec are exact (they're the product contract). Everything else — helper structure, regex details, code organization, extra edge-case handling — is yours to improve. If you see a cleaner or more robust approach that passes the same VERIFY, take it, and note any spec deviation in your final summary.

VERIFY — run and paste output. FIRST restart the server so it loads your edited actions.py (a server started earlier keeps running the OLD code): `pkill -f "uvicorn main:app"; cd backend && (nohup uv run uvicorn main:app --port 8000 > /tmp/cg.log 2>&1 &) ; sleep 3`
- cd backend && uv run python smoke_test.py → ALL PASS
- Run twice: curl -s -X POST 127.0.0.1:8000/execute-action -H 'Content-Type: application/json' -d '{"action_type":"STAGE_INVOICE","payload":{"vendor":"TestVendor","invoice":"T-1","amount":100}}' → first succeeds, second returns success:false + error:"duplicate"; then curl -s 127.0.0.1:8000/audit-log shows both entries (staged + duplicate_rejected)
- curl -s "127.0.0.1:8000/audit-log?type=STAGE_INVOICE" → only STAGE_INVOICE rows
- curl -s -w ' %{http_code}' -X POST 127.0.0.1:8000/execute-action -H 'Content-Type: application/json' -d '{"action_type":"BOGUS","payload":{}}' → 400 with an "error" field
- cd backend && uv run python -c "import actions; print(actions.read_audit(10, type='STAGE_INVOICE'))" works
- Clean up your test rows so they don't show in the demo Inspector: `cd backend && rm -f audit_log.jsonl round_staging_queue.json` (both gitignored)
```

## Phase 3 — context filtering + unverified-claim rule + brain expansion

```
You are a senior backend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). The deterministic engine in backend/rules.py checks text against backend/company_brain.json. run_rules(text, brain, context_type=None) already receives context_type from main.py but ignores it. Valid context_type values: "outgoing_email", "slack_message", "incoming_invoice", "general" (CONTRACT.md).

YOUR FILES ONLY: backend/rules.py, backend/company_brain.json, backend/smoke_test.py, backend/scenarios.json. Do NOT modify any other file.

TASK:

1. CONTEXT-AWARE FILTERING — add a module-level CONTEXTS dict mapping each check function to either a set of context_types or the string "ALL":
   - "ALL" (fraud signatures — must fire in every context): check_bank_details, check_duplicate_invoice, check_urgent_payment_change
   - {"incoming_invoice"}: check_amounts_vs_contract, check_sender_domain
   - {"outgoing_email", "slack_message", "general"}: check_payment_terms, check_discount_cap, check_treasury_lock, check_feature_claims, check_refund_credits, check_large_commitment, check_unverified_claims (new rule below)
   - Update run_rules: when context_type is provided AND the check's CONTEXTS entry is a set, skip checks whose set doesn't contain it; "ALL" checks always run; a check missing from CONTEXTS defaults to "ALL"; unknown context_type → run everything (fail-open).
   - Net effect: an incoming_invoice mentioning "Net-60" does NOT trigger sales-policy noise; an outgoing_email containing a mismatched vendor IBAN still triggers the CRITICAL fraud catch.

2. UNVERIFIED_CLAIM rule — add check_unverified_claims(text, brain), category UNVERIFIED_CLAIM, severity MEDIUM, outgoing contexts only:
   - FIRES WHEN: text asserts a certification/attestation not present in the brain. Scan for certification names: "soc 2", "iso 27001", "iso27001", "hipaa", "pci dss", "pci-dss", "gdpr certified", "cyber essentials". For each found, check whether any engineering_status item's feature+status text contains that token (case-insensitive). If the brain has NO engineering_status entry covering it → flag.
   - Issue: "'{claim}' is asserted but has no backing entry in the company brain."
   - Correction: "Remove the claim or add an authoritative source to the brain before sending."
   - Evidence: {"brain_key": "engineering_status", "expected": "a status entry covering {claim}", "found": "no entry"}
   - Do NOT fire when the claim IS covered (e.g., "SOC 2" is covered by an engineering_status feature containing "SOC 2" — even if status is 'in audit', that case belongs to check_feature_claims, not this rule).

3. BRAIN EXPANSION — extend backend/company_brain.json:
   - Add a third signed_contract: Meridian Security Ltd, approved_monthly_retainer_gbp 4200, hourly_rate_gbp 80, bank_iban "GB77NWBK11223344"
   - Add a fourth engineering_status item: feature "Bulkhead v2", status "Planning — not started", date "2026-10-20". (Keep this exact name: check_feature_claims matches on any feature word longer than 2 chars, so a generic word like "API" would make every "our API is live" draft fire PROMISE_BREACH.)
   - Ensure known_sender_domains from Phase 1 is present (add "meridian-sec.com" to it)
   - Do not rename or remove existing keys; existing values stay identical.

4. TESTS — add to backend/smoke_test.py:
   - A context-filtering case: run an invoice-style text (with IBAN + vendor name) through run_rules with context_type="outgoing_email" and assert CRITICAL rules still fire but invoice-only HIGH rules do NOT
   - An unverified-claim case: text claiming "we are ISO 27001 certified" → expect UNVERIFIED_CLAIM; text saying "our SOC 2 report" → expect NO UNVERIFIED_CLAIM (it's covered)
   - Use the expect(...) helper from Phase 1 (call rules.run_rules directly for the context-filter case). The 4 baseline assertions MUST still pass.

WORKING RULES — follow exactly:
- Read every file you will modify completely BEFORE editing it.
- Work the numbered items IN ORDER and complete ALL of them — if one is already implemented, confirm it matches this spec and move on.
- Never silently skip an item — if truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete AND every VERIFY command produces the stated output. Before finishing, re-check each numbered item against your changes. Partial completion is a failure.
- FREEDOM: behaviors, category names, evidence shapes, and message strings in this spec are exact (they're the product contract). Everything else — helper structure, regex details, code organization, extra edge-case handling — is yours to improve. If you see a cleaner or more robust approach that passes the same VERIFY, take it, and note any spec deviation in your final summary.

VERIFY — run and paste output: cd backend && uv run python smoke_test.py ; echo "exit=$?" → ALL PASS, exit=0.
```

## Phase 4 — perf, demo-data reset, risk score (skip if not started by 13:45)

```
You are a senior backend engineer working in the CommitGuard repository (read AGENTS.md first).

YOUR FILES ONLY: backend/bench.py, backend/seed_audit.py, backend/rules.py (one small additive change), backend/company_brain.json.

TASK:
1. backend/bench.py already exists — run `uv run python bench.py` and report the avg/p95 latency table in your PR description (the pitch needs a "checks run in <N ms" stat). If the file is missing, create it: loads scenarios.json + company_brain.json, runs rules.run_rules 200 iterations per scenario, prints a table of avg/p50/p95/max ms per scenario.
2. backend/seed_audit.py already exists. Upgrade it for demo day:
   - Add a `--reset` flag: delete backend/audit_log.jsonl and backend/round_staging_queue.json first, then seed. (Both are gitignored, so seeding only affects the machine it runs on. Riyansh runs `uv run python seed_audit.py --reset` on the demo laptop at 14:30.)
   - Stagger timestamps: pass an explicit "ts" in each entry (actions.audit() lets the entry's own keys override the defaults) spread over the last ~2 hours, oldest first, plus a matching "epoch_ms".
   - Make every seeded payload that represents a block carry "violations": a list of {category, severity, evidence:{brain_key, expected, found}} using REAL brain keys from company_brain.json. The Inspector's "violations caught" stat sums payload.violations.
   - Use the same "result" strings actions.py writes (staged_in_round_queue, escalated_to_cfo, ok) so the Inspector counts them consistently.
   - Run `uv run python seed_audit.py --reset` and paste the output.
3. risk_score — in backend/rules.py, add a "risk_score" integer field (0–100) to every violation dict produced by _v(). Mapping: LOW=20, MEDIUM=45, HIGH=70, CRITICAL=95. Additive only — no existing fields change.
4. OPTIONAL 5th scenario — only if steps 1–3 pass cleanly: add "slack_urgent_fraud" to backend/scenarios.json (label "Slack — urgent bank change", context_type "slack_message"): someone urgently asks finance to update CloudScale's bank details today → fires URGENT_PAYMENT_CHANGE CRITICAL. A 5th button appears in the demo automatically. Post the label in chat for Pranali's pitch.

WORKING RULES — follow exactly:
- Read every file you will modify completely BEFORE editing it.
- Work the numbered items IN ORDER and complete ALL of them — if one is already implemented, confirm it matches this spec and move on.
- Never silently skip an item — if truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete AND every VERIFY command produces the stated output. Before finishing, re-check each numbered item against your changes. Partial completion is a failure.
- FREEDOM: behaviors, category names, evidence shapes, and message strings in this spec are exact (they're the product contract). Everything else — helper structure, regex details, code organization, extra edge-case handling — is yours to improve. If you see a cleaner or more robust approach that passes the same VERIFY, take it, and note any spec deviation in your final summary.

VERIFY — run and paste output: cd backend && uv run python smoke_test.py ; echo "exit=$?" → ALL PASS, exit=0. Post the bench.py "overall avg / p95" line in team chat (Pranali's pitch uses it).
```
