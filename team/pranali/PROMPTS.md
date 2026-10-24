# Pranali — Codex prompts (all frontend + pitch)

**How to use:** open Codex in the repo root. Paste ONE phase's entire fenced block as a
single message — it contains everything Codex needs. When it finishes, verify by clicking
at http://127.0.0.1:8000 (server off? run `./start.sh` from repo root), then ship:

```
git checkout -b pranali/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin pranali/phase<N> && gh pr create --fill
```

**Your folders:** `demo/` · `plugin/` · `pitch/` — never touch `backend/`.
**Errors:** screenshot + paste to Riyansh. Never debug code yourself.
**Want different demo wording?** Write the text, hand it to Darsh — `backend/scenarios.json` is his file.

---

## Phase 1 — complete demo UI (the flagship)

```
You are a senior frontend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). CommitGuard is a pre-send compliance firewall: a local FastAPI backend checks drafts/invoices against a company knowledge base and returns violations — each has {category, severity (LOW/MEDIUM/HIGH/CRITICAL), issue, correction, suggested_rewrite, evidence {brain_key, expected, found}, optional span {text,start,end}, optional fix}. demo/index.html is the flagship single-file demo served at http://127.0.0.1:8000 — it already works: scenario buttons from GET /scenarios, POST /verify-context, violation cards, suggested rewrite, Send disabled on CRITICAL, POST /execute-action.

YOUR FILES ONLY: demo/index.html. Must remain ONE self-contained file — vanilla HTML/CSS/JS, NO frameworks, NO CDN, NO external fonts/assets (must run fully offline). Do NOT change which endpoints are called, the request/response JSON shapes, or element IDs used by the JS logic. Do NOT modify any other file.

TASK — elevate the UI to product-quality while keeping every existing behavior. Read the file first; keep its JS architecture (api() helper, verify(), scenario loader) intact. Improve:

1. VISUAL SYSTEM — define CSS variables for the palette up top (dark, fintech/console feel: near-black background, one accent color, severity colors as a set). System font stack only. Consistent 8px spacing scale. No purple gradients, no generic rounded-card-everything — this is a dense pro tool for finance people.

2. VIOLATION CARDS — each card gets:
   - Left border (4px) colored by severity: CRITICAL #ff3b30 solid + subtle pulse animation, HIGH #ff9500, MEDIUM #ffcc00, LOW #8e8e93
   - Header row: severity chip (small, colored bg, uppercase, letterspaced) + category in monospace
   - Body: issue text (readable), then correction prefixed with a → in the accent color
   - Evidence receipt: a compact bordered box in small monospace showing three lines — "brain: <brain_key>" / "expected: <expected>" / "found: <found>" — this is the "receipt" judges photograph, make it look like a receipt/ticket
   - If violation.fix exists: an inline "apply fix" mini-button that replaces the span text in the draft and re-verifies

3. SPAN HIGHLIGHTS — when violations carry span{start,end}, render a read-only preview under the compose box with those ranges underlined in the severity color (squiggly or solid underline + tooltip with the category).

4. STATES — compose area border pulses red on CRITICAL; CLEAN shows a green check + "Clear to send" state; Send button enabled ONLY when status is CLEAN (CRITICAL shows it blocked with a lock icon); backend unreachable (fetch throws) → persistent "backend offline — checks unavailable" banner + health dot turns red.

5. ACTIONS — buttons: "Apply all fixes" (uses top-level suggested_rewrite), "Escalate to CFO" (ESCALATE_FRAUD), "Stage in Round" (STAGE_INVOICE, only on invoice context), "Send" (SEND_APPROVED), "Override" (APPROVE_OVERRIDE — prompts for a reason first). Every successful action → toast notification bottom-right, auto-dismiss ~3s, dark style with accent border.

6. DETAILS — Cmd/Ctrl+Enter triggers verify; scenario buttons show active state; top bar shows product name "CommitGuard" + a live health dot (GET /health every 15s, green=rules, blue=rules+llm, red=offline) + latency from meta after each verify; "Open Inspector" link top-right → /inspector.html.

VERIFY — tell me exactly what to click; I will open http://127.0.0.1:8000, click all 4 scenario buttons, use every action button, and check the browser console has zero errors.
```

## Phase 2 — inspector + simulator polish

```
You are a senior frontend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). Frontend is single-file vanilla HTML/JS served from a local FastAPI backend at 127.0.0.1:8000.

YOUR FILES ONLY: demo/inspector.html and plugin/simulator.html. Do NOT modify any other file — especially NOT plugin/adapter.js (its exported names are a hard contract).

TASK — restyle both to match demo/index.html (read it first and reuse its design tokens — palette variables, font stack, spacing scale, card style, severity colors, toast style):

1. demo/inspector.html — the compliance console. It shows the company brain (GET /brain) as readable grouped cards (financial_rules, signed_contracts with IBANs masked like GB29••••5689, engineering_status, people, known_sender_domains), a live audit trail (GET /audit-log?limit=20, auto-refresh every 4s, newest first, each row showing action_type + result + timestamp in monospace), and a health header (GET /health every 15s — engine mode, check count, green/red dot). Add a "← Back to demo" link. Keep ALL fetch calls and JS logic identical — only CSS/layout changes.
2. plugin/simulator.html — the plugin-UX mock: same restyle. Its JS calls plugin/adapter.js — keep every adapter call, element ID, and event handler byte-for-byte identical.

VERIFY: I will open http://127.0.0.1:8000/inspector.html (brain cards + live audit rows visible) and plugin/simulator.html — both must look like the same product family as the demo, zero console errors.
```

## Phase 3 — pitch package

```
You are a technical writer working in the CommitGuard repository (read AGENTS.md first). CommitGuard is a pre-send compliance firewall entered in the Round Treasury Finance/Ops track at the Lightfern "Company Brain" hackathon: deterministic rules check outgoing drafts and incoming invoices against a company brain before anything is sent/paid — catching payment-term violations, discount-cap breaches, bank-detail mismatches (payment-redirection fraud — UK invoice/mandate fraud ≈ £41M/yr), contract overages, and promises engineering hasn't shipped. Everything runs offline on localhost; violations cite evidence; actions escalate/stage/log with an audit trail.

YOUR FILES ONLY: pitch/ (submission.md, script.md, one-pager.html, rehearsal-sheet.md — all exist). Do NOT modify any other file.

TASK — polish all four to submission quality:

1. pitch/submission.md — the hackathon submission text, ≤200 words total. Structure: one-line hook ("Lightfern finishes your sentences; CommitGuard makes sure you can stand behind them"), the fraud-scenario lead (invoice with changed bank details caught before payment), the three capabilities (detect / fix / act), why it fits Round Treasury (upstream of their ledger-side fraud checks), tech honesty line (deterministic rules = auditable + offline; optional LLM enrichment), the £41M stat. Tight, confident, no filler.

2. pitch/script.md — the 90-second demo script. Must total ~90 seconds spoken: 10s hook, then the 4-scenario walkthrough with exact one-line narration per click (sales email 20s → vendor invoice 25s → support reply 15s → clean pass 10s), inspector/audit close 10s. Write what the presenter says AND what they click, per beat.

3. pitch/one-pager.html — printable A4 portrait judge handout (light theme, system fonts, prints cleanly, no external assets): product name + one-liner, 3 bullet "what it catches", mini diagram text flow (draft → rules → brain → verdict), the £41M stat, "rules engine, not a black-box model" differentiator, audit-trail receipt mention, QR-less link text 127.0.0.1:8000. Must fit ONE page in print preview — trim content until it does.

4. pitch/rehearsal-sheet.md — run-of-show: the 4-scenario click order, one judge-facing line per step, the fallback line if wifi/API fails ("everything you're seeing runs locally — no network needed"), the two hardest judge questions with their answers (Q: "why not just an LLM?" A: auditable, deterministic, offline, <5ms — LLM is optional enrichment. Q: "doesn't Round already do fraud checks?" A: Round catches it in the ledger; we catch it at the keyboard before it enters the system).

VERIFY: I will print-preview one-pager.html (must be 1 page) and read submission.md aloud (under 60 seconds).
```

## Phase 4 — video + submit (mostly you, not the agent)

```
- ~14:00 record a 2-min backup video: clean run of all 4 scenarios + Inspector (QuickTime screen record, Cmd+Shift+5)
- 14:30 rehearse the pitch twice using pitch/rehearsal-sheet.md — you deliver it
- 15:45 airplane-mode test: wifi OFF → demo must still fully work → tell Riyansh immediately if not
- before 16:00 paste pitch/submission.md into the submission form — BEFORE the deadline, not at it
- Optional Codex prompt if needed: "In pitch/one-pager.html update the stats block to: <paste Darsh's bench.py numbers>"
```

## Conditional — real Lightfern plugin (ONLY if Riyansh says GO)

```
You are a senior frontend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first). The Lightfern plugin runtime hosts our real integration. plugin/simulator.html is the exact intended UX; plugin/adapter.js wraps all backend HTTP calls (verifyContext, executeAction, debounce, BASE_URL) — do NOT rename its exports.

TASK: port CommitGuard into the Lightfern plugin using these host APIs (Riyansh fills the brackets from the SDK demo):
- plugin entry file + manifest format: [SDK]
- read current draft text: [SDK]
- write/apply text into draft: [SDK]
- render UI surface (panel/card/notification): [SDK]
- draft-change event subscription: [SDK]

Create the plugin/ files the SDK expects. Behavior: on draft change (debounce 400ms) call adapter.verifyContext(text, contextType) → render the same violation-card UI as the simulator in the host's surface → severity CRITICAL disables/intercepts send if the SDK allows, otherwise renders a blocking banner → action buttons call adapter.executeAction → "apply fix" writes the fix/suggested_rewrite back into the draft via the SDK's apply API. Backend unreachable → show "offline" state, never crash.
VERIFY: the plugin loads in the host OR passes their build/lint validator — screenshot or output to Riyansh.
```

**If the plugin runtime can't reach localhost** — paste this instead:

```
You are a senior engineer working in the CommitGuard repository. The Lightfern plugin sandbox blocks network access to localhost, so the deterministic engine must run INSIDE the plugin.

TASK: create plugin/rules.js — a faithful JavaScript port of backend/rules.py (read that file first): same check functions, same regexes, same violation shape {category, severity, issue, correction, suggested_rewrite, evidence{brain_key,expected,found}, span{text,start,end}, fix}, same ALL_CHECKS registry, run_rules(text, brain, context_type), risk_level(), apply_fixes(). Also create plugin/brain.js exporting the contents of backend/company_brain.json as a JS object. CommonJS module.exports at the bottom so `node` can run it directly.
VERIFY: run `node -e "const r=require('./plugin/rules.js');const b=require('./plugin/brain.js');const s=require('./backend/scenarios.json');for(const [k,v] of Object.entries(s))console.log(k, r.run_rules(v.text,b,v.context_type).map(x=>x.category))"` — output must match the Python engine's categories per scenario.
```
