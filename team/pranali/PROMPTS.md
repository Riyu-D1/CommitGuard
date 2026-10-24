# Pranali — frontend (everything the judges see)

**How to use:** each phase is ONE fenced block. Paste the ENTIRE block into your AI tool —
it contains all the context the AI needs (it knows nothing until you paste it).
Then verify by clicking at http://127.0.0.1:8000 (server off? run `./start.sh` from the repo root).

```
git checkout -b pranali/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin pranali/phase<N> && gh pr create --fill
```

**Your folders:** `demo/` · `plugin/` · `pitch/` — never touch `backend/`.
**Errors:** screenshot + paste to Riyansh. Never debug code yourself.
**Want different demo wording?** Write the text, hand it to Darsh — `backend/scenarios.json` is his file.

---

## Phase 1 — demo/index.html polish

```
You are a frontend engineer working in a git repo called CommitGuard — a pre-send compliance firewall for a hackathon.

WHAT IT IS: a local FastAPI backend checks drafted emails/messages/invoices against a company knowledge base and returns violations — each with category, severity (LOW/MEDIUM/HIGH/CRITICAL), issue, correction, suggested_rewrite, evidence {brain_key, expected, found}, and optional span {text, start, end}. demo/index.html is a single-file HTML/CSS/JS compose-box demo served by the backend at http://127.0.0.1:8000: it loads 4 demo scenarios from GET /scenarios as buttons, POSTs the text to /verify-context, renders violation cards, shows a suggested rewrite, disables "Send" on CRITICAL, and POSTs /execute-action for fixes/escalations. It already works end-to-end.

YOUR FILES ONLY: demo/index.html. Keep it ONE file, vanilla HTML/CSS/JS, no dependencies, no CDN, no external fonts (must work fully offline). Do NOT modify any other file. Do NOT change which endpoints are called or the JSON shapes used.

TASK — improve the visual design only, keeping every existing feature working:
- Each violation card gets a left border colored by severity (grey/yellow/orange/red scale; CRITICAL = strong red)
- Evidence renders as a compact receipt inside each card: brain key, expected value, found value — small monospace, clearly readable
- CRITICAL result: pulsing red outline on the compose area; CLEAN: brief green check animation
- Successful actions (fix applied, escalated, staged) show a toast notification
- Keep the existing scenario buttons, span highlighting, "Apply all fixes", Send button states, and the "Open Inspector" link all working
VERIFY (describe to me what to click): I will open http://127.0.0.1:8000, click all 4 scenario buttons, and check the browser console has no errors.
```

## Phase 2 — inspector + simulator

```
You are a frontend engineer working in a git repo called CommitGuard — a pre-send compliance firewall. (Context: local FastAPI backend checks drafts/invoices against backend/company_brain.json, returns violations; frontend is single-file vanilla HTML/JS at 127.0.0.1:8000.)

YOUR FILES ONLY: demo/inspector.html and plugin/simulator.html. Do NOT modify any other file — especially NOT plugin/adapter.js (its exported function names are a contract other code depends on).

TASK — visual restyle only:
1. demo/inspector.html already exists: it shows the company brain (GET /brain), a live audit trail (GET /audit-log, auto-refreshes), and health status (GET /health). Restyle it to match demo/index.html — open that file first and reuse its fonts, colors, card styling, and spacing.
2. plugin/simulator.html already exists: it's a mock of the real plugin UI that calls the same backend via plugin/adapter.js. Restyle it the same way.
Keep ALL JavaScript logic, fetch calls, element IDs, and adapter.js usage byte-for-byte identical — change only CSS and non-functional markup.
VERIFY: I will open http://127.0.0.1:8000/inspector.html (should show brain cards + audit table) and plugin/simulator.html — no console errors.
```

## Phase 3 — pitch + submission

```
You are a technical writer working in a git repo called CommitGuard — a pre-send compliance firewall built for the Lightfern "Company Brain" hackathon, competing in the Round Treasury Finance/Ops track.

WHAT IT DOES: before an employee sends an email or pays an invoice, deterministic rules check the text against a company knowledge base and flag violations (payment terms over policy, discounts over cap, invoice bank details that don't match the signed contract = payment-redirection fraud, features promised that engineering hasn't shipped). Violations cite evidence and offer one-click fixes or actions (stage in a Round-style approval queue, escalate to CFO, audit log). UK invoice/mandate fraud costs businesses ~£41M/year. Runs fully offline on localhost; optional OpenAI enrichment.

YOUR FILES ONLY: pitch/ folder (submission.md, script.md, one-pager.html, rehearsal-sheet.md all exist). Do NOT modify any other file.

TASK — polish the existing files:
1. pitch/submission.md — the hackathon submission blurb: tighten to under 200 words, lead with the fraud scenario and "pre-send firewall" positioning, keep the £41M stat and the "Round catches it in the ledger, we catch it at the keyboard" line.
2. pitch/script.md — the 90-second demo script: check timing adds to ~90s, tighten speaker lines.
3. pitch/one-pager.html — the printable judge handout: verify it fits one A4 page in print preview, tighten text if it overflows.
4. pitch/rehearsal-sheet.md — must list the 4-scenario click order (sales email → vendor invoice → support reply → clean pass) with one-line judge-facing narration per step.
VERIFY: I will open pitch/one-pager.html and print-preview it (must be 1 page), and read submission.md aloud (under 60 seconds).
```

## Phase 4 — video + submit (mostly you, not the agent)

```
- ~14:00 record a 2-min backup video: clean run of all 4 scenarios + Inspector page (QuickTime screen record)
- 14:30 rehearse the pitch twice using pitch/rehearsal-sheet.md
- 15:45 airplane-mode test: wifi OFF → demo must still fully work → tell Riyansh immediately if not
- before 16:00 paste pitch/submission.md into the submission form — BEFORE the deadline, not at it
- Optional agent prompt: "In pitch/one-pager.html update the stats block to: <paste Darsh's bench numbers>"
```

## Conditional — real Lightfern plugin (ONLY if Riyansh says GO)

```
You are a frontend engineer working in a git repo called CommitGuard — a pre-send compliance firewall. (Context: local backend at 127.0.0.1:8000 exposes POST /verify-context returning violations and POST /execute-action; plugin/simulator.html shows the exact intended UI; plugin/adapter.js wraps the HTTP calls — keep its exported names identical.)

TASK: port CommitGuard into the Lightfern plugin runtime using these host APIs:
- entry file: [RIYANSH FILLS]
- read draft text: [RIYANSH FILLS]
- write/apply text: [RIYANSH FILLS]
- render UI surface: [RIYANSH FILLS]
- draft-change event: [RIYANSH FILLS]
Create plugin/ files per the SDK's expected structure: same violation-card UI as the simulator, calls adapter.verifyContext on draft change (debounced 400ms), CRITICAL severity blocks send, action buttons call adapter.executeAction.
VERIFY: loads in the host OR passes their validator — screenshot to Riyansh.
```

**If the plugin runtime can't reach localhost** — paste this instead:

```
You are a frontend engineer working in a git repo called CommitGuard — a pre-send compliance firewall. The Lightfern plugin sandbox blocks fetch to localhost, so the deterministic engine must be ported INTO the plugin.

TASK: create plugin/rules.js — a JavaScript port of backend/rules.py's checks (read that file first; copy the same regexes and the same violation shape: category, severity, issue, correction, suggested_rewrite, evidence{brain_key,expected,found}, span{text,start,end}, fix). Inline backend/company_brain.json as a JS object export. The plugin then calls runRules(draftText, brain) directly — zero backend dependency.
VERIFY: run `node plugin/rules.js` (or a small test script) against the 4 scenario texts from backend/scenarios.json — violations must match what the Python engine returns for each scenario.
```
