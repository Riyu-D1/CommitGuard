# Pranali — agent prompts (demo UI, Inspector, pitch)

**How to use (every phase):**
1. Fresh branch from latest main, every time:
   `git checkout main && git pull && git checkout -b pranali/phase<N>`
2. Restart the server after every pull (Ctrl-C the old one): `./start.sh` from the repo root.
3. Paste ONE phase's entire fenced block into Codex/Devin. When it finishes, verify by clicking at http://127.0.0.1:8000.
4. Ship: `git add -A && git commit -m "pranali phase <N>" && git push -u origin HEAD && gh pr create --fill`
   (If Devin opened the PR itself, skip this step.) Post "pranali phase N up" in chat.
5. As soon as YOUR PR is merged, start the next phase. **Do not wait for teammates.**

**You are the critical path.** Targets: P1 merged by 12:45 · P2 by 13:45 · P3 by 14:20 · video 14:30–14:50.
If a phase runs 20 min past its target, ship what works and move on.

**Your folders today:** `demo/` · `pitch/`. Never touch `backend/`. `plugin/` moved to Riyansh for the day
(it's only needed if he calls GO on the real Lightfern plugin at 12:30).
**Errors:** screenshot + paste to Riyansh. Never debug code yourself.
**If the AI claims done but a VERIFY fails, or stops mid-task, reply with exactly:**
`Continue — complete every remaining numbered item, then re-check.`
**Want different demo wording?** Write the text, hand it to Darsh. `backend/scenarios.json` is his file.

---

## Phase 1 — complete demo UI (the flagship · target merged by 12:45)

```
You are a senior frontend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). CommitGuard is a pre-send compliance firewall: a local FastAPI backend checks drafts/invoices against a company knowledge base and returns violations. Each has {category, severity (LOW/MEDIUM/HIGH/CRITICAL), issue, correction, suggested_rewrite, evidence {brain_key, expected, found}, optional span, optional fix}. demo/index.html is the flagship single-file demo served at http://127.0.0.1:8000. It already works: scenario buttons from GET /scenarios, POST /verify-context (debounced on typing), violation cards, Send disabled on CRITICAL, POST /execute-action for Send / Send anyway / Escalate / Stage.

FACTS ABOUT THE REAL DATA (check them yourself with curl before coding):
- span is NOT always complete: payment-terms/discount/treasury violations have span {text,start,end}; PAYMENT_REDIRECTION and CONTRACT_OVERAGE spans have only {text}; PROMISE_BREACH has no span.
- For vendor_invoice and support_reply the top-level suggested_rewrite is identical to the input text (no auto-fixable spans).
- The response may contain a top-level "advisories" array (optional LLM notes) and meta.rules_ms. Both may be absent; handle both cases.
- A 5th scenario button may appear later (backend/scenarios.json is data-driven). Don't hardcode 4.
- POST /execute-action can return HTTP 400 {"error": ...} (e.g. override without reason, unknown action) or 200 {"success": false, "error": "duplicate", "message": ...}.
- The "Apply all fixes" button currently does NOT call /execute-action at all. Nothing is logged when fixes are applied. That must change (item 5).

YOUR FILES ONLY: demo/index.html. It must remain ONE self-contained file: vanilla HTML/CSS/JS, NO frameworks, NO CDN, NO external fonts/assets (it must run fully offline). Keep the endpoints and request/response shapes. You may change markup/IDs as long as the JS you write uses them consistently. Do NOT modify any other file.

TASK — elevate the UI to product quality while keeping every existing behavior:

1. VISUAL SYSTEM — CSS variables for the palette up top (dark fintech/console feel: near-black background, one accent color, severity colors as a set). System font stack only. 8px spacing scale. No purple gradients, no generic rounded-card-everything. This is a dense pro tool for finance people.

2. VIOLATION CARDS — each card:
   - 4px left border by severity: CRITICAL #ff3b30 + subtle pulse, HIGH #ff9500, MEDIUM #ffcc00, LOW #8e8e93
   - Header: severity chip (small, colored bg, uppercase, letterspaced) + category in monospace
   - Body: issue text, then correction prefixed with → in the accent color
   - Evidence receipt: compact bordered box, small monospace, three lines: "brain: <brain_key>" / "expected: <expected>" / "found: <found>". This is the receipt judges photograph, so make it look like a ticket.
   - If violation.fix AND span.start/end exist: an inline "apply fix" mini-button that replaces text[start:end] with fix and re-verifies.
   - Escape all text you insert into innerHTML (write a tiny esc() helper).

3. SPAN HIGHLIGHTS — a read-only preview under the compose box with offending text underlined in the severity color + a tooltip with the category. Use span.start/end when both are numbers; else if span.text exists, use the first indexOf(span.text); else skip. Never crash on a missing span.

4. STATES — compose border pulses red on CRITICAL; CLEAN shows a green check + "Clear to send". Send is enabled ONLY on CLEAN; on any violation Send is disabled and "Send anyway" shows instead (disabled when CRITICAL). Backend unreachable (fetch throws or non-JSON) → persistent "backend offline — checks unavailable" banner + red health dot. Wrap api() in try/catch so nothing throws to the console.

5. ACTIONS + AUDIT PAYLOADS — every button logs to the audit trail with a useful payload. Always include {text, context_type: currentCtx, violations: lastResult?.violations || []}:
   - "Apply all fixes": enabled only when suggested_rewrite is non-null AND differs from the current text. On click: POST APPLY_REWRITE_AND_LOG with payload {original_text, text: <rewrite>, context_type, violations}, then put the rewrite in the box and re-verify.
   - "Escalate to CFO" (ESCALATE_FRAUD): shown only when any violation is CRITICAL.
   - "Stage in Round" (STAGE_INVOICE): shown only when currentCtx === "incoming_invoice". Add payload.invoice = the invoice number if the text matches /INVOICE\s*#?\s*([A-Z]{2,4}-?\d{3,})/i (the backend dedupes on it).
   - "Send" (SEND_APPROVED) and "Send anyway" (APPROVE_OVERRIDE, must prompt for a reason first; cancel or empty → do nothing).
   - Toasts bottom-right, ~3s auto-dismiss: success style shows r.message; if HTTP error or r.success === false, show a warning-style toast with r.message || r.error.
   - The right-rail audit list shows action_type + result + local time (new Date(ts).toLocaleTimeString()) and refreshes after every action.

6. DETAILS — Cmd/Ctrl+Enter triggers verify; active state on the selected scenario button; top bar: "CommitGuard" + live health dot (GET /health every 15s: green=rules, blue=rules+llm, red=offline) + after each verify "<meta.rules_ms ?? meta.latency_ms> ms · <checks_run> checks"; "Open Inspector →" link top-right → /inspector.html. If res.advisories has items, render them under the violations as small dim cards headed "AI review (advisory)". They never affect Send.

WORKING RULES — follow exactly:
- Read demo/index.html completely BEFORE editing it.
- Work the numbered items IN ORDER and complete ALL of them. If one is already implemented, confirm it matches this spec and move on.
- Never silently skip an item. If truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete, the page loads with zero console errors, and every scenario button works. Partial completion is a failure.
- FREEDOM: the behavior contract is exact (endpoints, shapes, send/override logic, audit payloads). Visuals are strong defaults, not a ceiling: you're the designer, so if your judgment produces something better within the constraints (single file, offline, severity-coded, dense console feel), do it.

VERIFY — start the server if needed (`./start.sh` from repo root), then run and paste:
- curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:8000/ → 200
- grep -c "APPLY_REWRITE_AND_LOG" demo/index.html → at least 1
- grep -E "https?://" demo/index.html → no CDN/external asset URLs (an inline-SVG xmlns line is fine)
Then tell me exactly what to click. I will: click each scenario; on sales_email click Apply all fixes (goes green); on vendor_invoice see Send + Send anyway disabled and click Escalate + Stage in Round; on support_reply try Send anyway with a reason; click clean_email → Send; then open /inspector.html and see those actions in the audit trail; console shows zero errors throughout.
```

## Phase 2 — Inspector dashboard (target merged by 13:45)

```
You are a senior frontend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). Frontend is single-file vanilla HTML/JS served by a local FastAPI backend at 127.0.0.1:8000. demo/inspector.html (served at /inspector.html) is the compliance console judges see after the demo: "every block, fix and override lands in an audit trail, and here's why."

DATA FACTS (curl them first):
- GET /audit-log?limit=N → newest-first array of {audit_log_id, ts (ISO 8601 UTC), action_type, payload, result, maybe epoch_ms}. payload may contain: text, context_type, reason (overrides), invoice, violations: [{category, severity, evidence:{brain_key, expected, found}, ...}].
- action_type values: SEND_APPROVED, APPLY_REWRITE_AND_LOG, APPROVE_OVERRIDE, STAGE_INVOICE, ESCALATE_FRAUD. result values include ok, staged_in_round_queue, escalated_to_cfo, duplicate_rejected (others may appear, so render unknown values as-is).
- GET /brain → object; known keys: financial_rules (object), signed_contracts (array), engineering_status (array), people (object), known_sender_domains (ARRAY of strings, may be absent). Unknown keys may appear.
- GET /health → {ok, engine, checks, brain_keys}.

YOUR FILES ONLY: demo/inspector.html. Do NOT modify any other file. Single file, no CDN, offline.

TASK — restyle to match demo/index.html (read it first and reuse its design tokens: palette variables, font stack, spacing, card style, severity colors) and turn it into a dashboard. You MAY add new JS for the items below. Keep using only the endpoints listed above.

1. STATS STRIP (top, big numbers, dashboard feel): fetch GET /audit-log?limit=500 for stats (separate from the table fetch) every 4s. Cards: Total actions · Violations caught (sum of payload.violations.length) · Fraud blocked (entries whose payload.violations has any severity CRITICAL, or action_type ESCALATE_FRAUD) · Fixes applied (APPLY_REWRITE_AND_LOG) · Overrides (APPROVE_OVERRIDE) · Staged in Round (STAGE_INVOICE with result staged_in_round_queue) · Duplicates blocked (result duplicate_rejected). Zero is a valid number; never NaN.

2. AUDIT TRAIL: GET /audit-log?limit=20, auto-refresh every 4s, newest first. Each row: local time (new Date(ts).toLocaleTimeString(); ts is UTC, so don't slice the string), action_type chip, result, violation category chips, and for APPROVE_OVERRIDE the reason in italics. Clicking a row expands it to show each violation's evidence receipt (brain_key / expected / found) and the payload text (first 200 chars). This is the "why was this flagged?" proof. New rows flash briefly.

3. COMPANY BRAIN: grouped cards for financial_rules, signed_contracts (IBANs masked like GB29••••5689: first 4 + •••• + last 4), engineering_status (green dot if status matches /merged|production|live|complete/i else amber), people, and known_sender_domains as tags. Arrays of strings render as tags, objects as key/value rows, unknown keys generically. Missing keys are skipped.

4. HEALTH HEADER: GET /health every 15s: green/red dot, engine mode, check count. Backend offline → every panel shows "backend offline" and nothing throws.

5. Header links: "← Back to demo" (/) and the product name.

WORKING RULES — follow exactly:
- Read demo/index.html and demo/inspector.html completely BEFORE editing.
- Work the numbered items IN ORDER and complete ALL of them. Never silently skip; if blocked output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: all 5 items work with zero console errors, with an empty audit log AND with a populated one. Partial completion is a failure.
- FREEDOM: endpoints and data semantics are exact; layout and styling are yours. It should look like the same product as the demo.

VERIFY — run and paste: curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:8000/inspector.html → 200; grep -E "https?://" demo/inspector.html → no external URLs (an inline-SVG xmlns line is fine). Then I will: click a few actions in the demo, open /inspector.html, see the stats change within 4s, expand an ESCALATE_FRAUD row and see the IBAN evidence receipt, zero console errors.
```

## Phase 3 — pitch package (target merged by 14:20)

```
You are a technical writer working in the CommitGuard repository (read AGENTS.md first). CommitGuard is a pre-send compliance firewall entered in the Round Treasury Finance/Ops track at the Lightfern "Company Brain" Buildathon: deterministic rules check outgoing drafts and incoming invoices against a company brain before anything is sent/paid. It catches payment-term violations, discount-cap breaches, bank-detail mismatches (payment-redirection fraud; UK invoice/mandate fraud ≈ £41M/yr), contract overages, and promises engineering hasn't shipped. Everything runs offline on localhost; violations cite evidence; actions escalate/stage/log to an audit trail shown in the Inspector dashboard.

GET THE REAL FACTS FIRST (the pitch must not claim anything that isn't on main). Start the server if needed (`./start.sh`), then:
- curl -s 127.0.0.1:8000/health → use the real "checks" number for any "N checks" claim
- read backend/rules.py and list the category strings passed to _v(...) → claim only categories that exist
- curl -s 127.0.0.1:8000/scenarios → the real scenario labels (there may be a 5th)
- cd backend && uv run python bench.py → use the real "overall avg" for the latency claim (if it's under 5ms say "under 5 ms"; otherwise use the real number)
- PLUGIN CLAIM: ask me "Did Riyansh confirm the Lightfern plugin loads in the host? (yes/no)". If no or unknown, describe it as "a plugin-ready adapter (plugin/adapter.js); the same check runs anywhere text leaves the company". Never claim a working Lightfern plugin unless I say yes.

YOUR FILES ONLY: pitch/ (submission.md, script.md, one-pager.html, rehearsal-sheet.md, all of which exist). Do NOT modify any other file.

TASK — polish all four to submission quality:

1. pitch/submission.md: the submission text, ≤200 words. One-line hook ("Lightfern finishes your sentences; CommitGuard makes sure you can stand behind them"), the fraud lead (invoice with changed bank details caught before payment), three capabilities (detect / fix / act + audit), why it fits Round Treasury (upstream of their ledger-side fraud checks; STAGE_INVOICE writes to a staging queue Round's AP agent would pick up), tech honesty line (deterministic rules = auditable + offline; optional LLM advisory layer), the £41M stat. Remove any claim the facts above don't support.

2. pitch/script.md: the 90-second demo script, ~90s spoken: 10s hook → sales email 20s (Apply all fixes) → vendor invoice 25s (CRITICAL, Escalate to CFO + Stage in Round) → support reply 15s → clean pass 10s → Inspector close 10s (stats strip + expand the escalation row to show the IBAN receipt). Presenter line AND exact click per beat. If a 5th scenario exists, add it only as an optional Q&A demo, not in the 90s.

3. pitch/one-pager.html: printable A4 portrait judge handout (light theme, system fonts, no external assets): name + one-liner, 3 bullets "what it catches", text flow (draft → rules → brain → verdict → audit), £41M stat, "rules engine, not a black-box model", audit-trail receipt mention, link text 127.0.0.1:8000. Must fit ONE page in print preview; trim until it does (add @page { size: A4; margin: 12mm } and print CSS).

4. pitch/rehearsal-sheet.md: run-of-show matching script.md click-for-click, one judge-facing line per step, fallback line if wifi/API fails ("everything you're seeing runs locally — no network needed"), the plan-B line if the live demo breaks ("let me show you the recording", then play the backup video), and the two hardest questions (Q: "why not just an LLM?" A: auditable, deterministic, offline, <5ms; the LLM is an optional advisory layer. Q: "doesn't Round already do fraud checks?" A: Round catches it in the ledger; we catch it at the keyboard before it enters the system).

WORKING RULES — follow exactly:
- Read all four existing files BEFORE editing; polish them, don't rewrite from scratch.
- Complete ALL four artifacts.
- DONE WHEN: submission.md ≤200 words (run `wc -w pitch/submission.md`), script ≈90 seconds, one-pager prints on 1 A4 page, rehearsal sheet matches the script. Partial completion is a failure.
- FREEDOM: required elements, stats and structure are exact; the writing is yours.

VERIFY: paste `wc -w pitch/submission.md` and the list of facts you used (checks count, categories, bench avg, plugin yes/no). I will print-preview one-pager.html (1 page) and read submission.md aloud.
```

## Phase 4 — video + submit (you, not the agent)

```
- 14:30 Riyansh resets the demo data on the demo laptop (seed_audit.py --reset). Wait for his "ready".
- 14:30–14:50 record a 2-min backup video on FINAL main: all 4 scenarios + Apply all fixes + Escalate + Stage + Inspector (stats + expanded row). QuickTime/Cmd+Shift+5. Save it to the desktop AND upload it somewhere you can reach from a phone.
- 15:00 FREEZE. 15:00–15:30 rehearse the pitch x3 using pitch/rehearsal-sheet.md (you deliver it; a teammate times it).
- 15:30 airplane-mode test: wifi OFF → demo must still fully work → tell Riyansh immediately if not.
- by 15:45 paste pitch/submission.md into the submission form, BEFORE 16:00, not at it.
- Optional agent prompt if numbers change: "In pitch/one-pager.html and pitch/submission.md update the latency stat to: <paste bench.py overall avg>"
```

## Conditional — real Lightfern plugin (ONLY if Riyansh says GO at 12:30; **Riyansh runs this**, not Pranali)

Pranali is the critical path on demo/inspector/pitch, so if the SDK is real, Riyansh pastes this into his own agent after his Phase 2. `plugin/` is in his lane today.

```
You are a senior frontend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). The Lightfern plugin runtime hosts our real integration. plugin/simulator.html is the exact intended UX; plugin/adapter.js wraps all backend HTTP calls (verifyContext, executeAction, debounce, BASE_URL) — do NOT rename its exports.

TASK: port CommitGuard into the Lightfern plugin using these host APIs (Riyansh fills the brackets from the SDK demo):
- plugin entry file + manifest format: [SDK]
- read current draft text: [SDK]
- write/apply text into draft: [SDK]
- render UI surface (panel/card/notification): [SDK]
- draft-change event subscription: [SDK]

Create the plugin/ files the SDK expects. Behavior: on draft change (debounce 400ms) call adapter.verifyContext(text, contextType) → render the same violation-card UI as the simulator in the host's surface → severity CRITICAL disables/intercepts send if the SDK allows, otherwise renders a blocking banner → action buttons call adapter.executeAction → "apply fix" writes the fix/suggested_rewrite back into the draft via the SDK's apply API. Backend unreachable → show "offline" state, never crash.
DONE WHEN: every bracketed SDK API above is wired in — never stub out a listed API silently; if one doesn't exist in the SDK, output "MISSING SDK API: <name>" and stop. Use the SDK idiomatically — if its docs suggest a better pattern than a literal port of the simulator, use it.
VERIFY: the plugin loads in the host OR passes their build/lint validator — screenshot or output to Riyansh.
```

**If the plugin runtime can't reach localhost** — only start this before 13:00 (a faithful port of rules.py incl. Darsh's new checks is 1h+). After 13:00, drop down the fallback ladder instead: plugin badge that opens the demo, or demo-only. Paste this instead:

```
You are a senior engineer working in the CommitGuard repository. The Lightfern plugin sandbox blocks network access to localhost, so the deterministic engine must run INSIDE the plugin.

TASK: create plugin/rules.js — a faithful JavaScript port of backend/rules.py (read that file first): same check functions, same regexes, same violation shape {category, severity, issue, correction, suggested_rewrite, evidence{brain_key,expected,found}, span{text,start,end}, fix}, same ALL_CHECKS registry, run_rules(text, brain, context_type), risk_level(), apply_fixes(). Also create plugin/brain.js exporting the contents of backend/company_brain.json as a JS object. CommonJS module.exports at the bottom so `node` can run it directly.
DONE WHEN: the VERIFY command runs and the JS engine's categories match the Python engine's for every scenario — a partial port (missing checks) is a failure, not a fallback.
VERIFY: run `node -e "const r=require('./plugin/rules.js');const b=require('./plugin/brain.js');const s=require('./backend/scenarios.json');for(const [k,v] of Object.entries(s))console.log(k, r.run_rules(v.text,b,v.context_type).map(x=>x.category))"` — output must match the Python engine's categories per scenario.
```
