# Riyansh — Agent Prompts (the full plugin + LLM build)

> **BASELINE EXISTS:** `plugin/adapter.js` and `plugin/simulator.html` are already
> built and working (Prompts A+B's output). Use Prompts A/B to *review or extend*
> them — or skip straight to Prompt C once the SDK is revealed. `llm_enrich.py`
> baseline works too; Prompt E hardens it.

**How to use:** work top-to-bottom through the phases. Paste each prompt into your
agent IN FULL — they are self-contained and assume no prior context. After each
prompt, do the verification it specifies. Do not move on if verification fails —
paste the error back.

**Your files:** everything in `plugin/` + `backend/llm_enrich.py`.
**Never touch:** `backend/main.py` (frozen), `backend/rules.py`, `backend/actions.py`,
`demo/`, `pitch/`, `backend/scenarios.json`.
**Contract:** `CONTRACT.md` at repo root — the API is fixed; your code adapts to it.

**Run before starting:** `cd backend && uv run uvicorn main:app --port 8000`
then `curl localhost:8000/health` → must return `{"ok":true,...}`.

---

# PHASE 1 — Foundation (10:45–11:15)
Goal: the entire plugin UX built and verified against a simulated host app —
before the real SDK is even understood. This is the critical-path unlock.

## Prompt A — Backend adapter module

```
You are building part of CommitGuard, a hackathon project: a "pre-send firewall"
that checks outgoing drafts (emails, messages) and incoming invoices against a
company knowledge base, flags violations, and offers one-click fixes.

CONTEXT: A FastAPI backend runs at http://localhost:8000. Its API is defined in
CONTRACT.md at the repo root — read that file first. Do not start coding until
you have read it.

TASK: Create `plugin/adapter.js` — the ONLY module allowed to talk to the backend.
Everything else in the plugin imports from here.

Requirements:
1. Vanilla JS (ES6), no dependencies, no build step. Usable via <script src> in a
   plain HTML page AND importable later.
2. Export (via global `CommitGuardAdapter` object, since we may not have modules):
   - `verifyContext(text, contextType)` -> POST /verify-context with
     {text, context_type}. Returns the parsed response.
   - `executeAction(actionType, payload)` -> POST /execute-action. Returns parsed response.
   - `getBrain()` -> GET /brain
   - `getScenarios()` -> GET /scenarios
   - `getAuditLog(limit)` -> GET /audit-log?limit=N
   - `getHealth()` -> GET /health
   - `debounce(fn, ms)` -> standard trailing debounce helper
3. ERROR HANDLING IS CRITICAL — the demo may run on bad venue wifi:
   - Wrap every fetch in try/catch. On network failure, resolve to
     { ok: false, error: "BACKEND_OFFLINE" } instead of throwing/rejecting.
   - On HTTP error status, resolve to { ok: false, error: "HTTP_<status>" }.
   - On success return the parsed body spread with { ok: true, ...body }.
4. JSDoc typedefs at the top matching CONTRACT.md exactly:
   @typedef Violation {category, severity, issue, correction, suggested_rewrite,
                       evidence {brain_key, expected, found}, span? {text,start,end}}
   @typedef VerifyResponse {ok, status, risk_level, violations[],
                            suggested_rewrite, meta {engine, checks_run, latency_ms}}
   @typedef ActionResponse {ok, success, audit_log_id, message}
5. BASE_URL constant = "http://localhost:8000" at top of file.

VERIFY: create nothing else. Tell me the file is ready and list the exports.
```

## Prompt B — Plugin simulator (the whole UX, before the SDK exists)

```
You are building part of CommitGuard, a pre-send compliance firewall. The backend
API is at http://localhost:8000 (contract in repo-root CONTRACT.md — read it).
`plugin/adapter.js` already exists exposing CommitGuardAdapter with verifyContext,
executeAction, getScenarios, getAuditLog, getBrain, debounce (read it first).

CONTEXT: Our final deliverable is a plugin inside a third-party Mac app whose SDK
we don't know yet. So build `plugin/simulator.html`: a faithful mock of a host
compose window + our plugin side-panel, so ALL the plugin UX logic is finished
and verified now. Later we only port it.

TASK: Create `plugin/simulator.html`, a SINGLE file (inline CSS, inline JS, plus
<script src="./adapter.js">). Dark theme, monospace-ish developer aesthetic.

EXACT LAYOUT:
- Header bar: title "CommitGuard Plugin — simulator", right side a chip showing
  "engine: —" (updated from meta.engine after each verify; display "rules" as
  "local checks" and "rules+llm" as "AI-enriched") and a health dot (green if
  GET /health ok, red if BACKEND_OFFLINE — poll every 5s).
- Main area: CSS grid, 2 columns: left = "compose surface" (60%), right = "plugin
  panel" (40%).
- Compose surface: a scenario <select> populated from getScenarios() (option
  label = sc.label), To: and Subject: inputs, and a large <textarea> (the draft).
  Selecting a scenario fills the textarea and triggers verification.
- Plugin panel: status line ("idle" / "checking…" / "CLEAR — brain-backed send" /
  "N violations — risk X" / "backend offline"), then the violations list, then a
  button row.

BEHAVIOR (implement exactly):
1. On textarea input: debounce 700ms -> verifyContext(value, "outgoing_email")
   with the scenario's context_type if one was loaded (store it from the scenario).
   While awaiting, status = "checking…" with a subtle pulse.
2. If adapter returns ok:false -> status "backend offline — showing last result";
   keep previous UI; do NOT clear cards.
3. CLEAN -> status "CLEAR — brain-backed send" (green), violations list empty,
   Send enabled.
4. Violations -> render one card per violation:
   [severity-colored left border (CRITICAL #f85149, HIGH #f0883e, MEDIUM #d29922,
   LOW #8b98a9)] [category chip uppercase] [issue text]
   [evidence line, monospace small: "brain: <evidence.brain_key> = <expected> ·
   found: <found>"] [correction line prefixed "→ " in green]
   If violation.span exists, append a small quoted span.text inside the card.
5. Buttons (same rules as CONTRACT.md):
   - "Apply all fixes": enabled only when top-level suggested_rewrite exists;
     on click replaces textarea content, re-verifies, toasts the result.
   - "Send": enabled only when CLEAN or all violations non-CRITICAL and user
     already overrode; on click SEND_APPROVED then toast message+audit_log_id.
   - "Send anyway": hidden when any CRITICAL exists; on click prompt() for
     reason -> APPROVE_OVERRIDE (cancel = do nothing) -> toast.
   - "Escalate to CFO" + "Stage in Round": visible only when a CRITICAL exists
     (ESCALATE_FRAUD / STAGE_INVOICE) -> toast.
   - Toasts: bottom-center, show message + audit_log_id, auto-dismiss 3s.
6. Audit feed: bottom of plugin panel, polls getAuditLog(6) every 4s, renders
   one compact line each: "<action_type> · <audit_log_id>".
7. Show meta.latency_ms next to status after each verify ("· 3.2ms").

VERIFY: open simulator.html in a browser with the backend running. Load each of
the 4 scenarios via the dropdown and confirm: sales_email = 3 cards; vendor_invoice
= CRITICAL card + Escalate/Stage buttons + send hidden; support_reply = 2 cards;
clean_email = CLEAR + Send enabled. Kill the backend, type something — status must
flip to "backend offline". Report what you saw.
```

---

# PHASE 2 — Port to the real SDK (11:15–13:00)
Goal: violation cards rendering inside the actual Lightfern plugin runtime by M1.
**Fill the `[SDK: …]` slots from the 10:00 demo + any docs before pasting.**

## Prompt C — SDK analysis + plugin skeleton

```
You are building the CommitGuard plugin for a real host app's plugin runtime.
Backend: http://localhost:8000 per CONTRACT.md. `plugin/adapter.js` (backend comms)
and `plugin/simulator.html` (reference UX) are done and verified — read both.

THE HOST SDK (what I learned from their demo/docs):
[SDK: plugin manifest format — e.g. manifest.json fields, entry file, where the
 folder must live]
[SDK: how a plugin reads the current draft text — API/hook/event name]
[SDK: UI surface — panel / inline card / toolbar / sidebar; DOM or their component
 API]
[SDK: lifecycle events — on draft change, on send attempt, on focus]
[SDK: how to write back into the draft, if allowed]

TASK:
1. Write `plugin/SDK_NOTES.md`: a concise summary of the manifest format, text
   access, UI surface, events, write-back — with a code snippet for each from
   their docs. This is our shared understanding; get it right.
2. Create the plugin skeleton (files per their required layout): manifest +
   minimal entry that (a) registers on the draft-change lifecycle event, (b)
   reads current draft text, (c) calls CommitGuardAdapter.verifyContext with a
   700ms debounce, (d) renders "⚠ N violations — risk X" or "✓ clear" as plain
   text in whatever UI surface exists. No cards yet — prove the loop.
3. If the SDK requires a build step or loader, document the exact command in
   SDK_NOTES.md.
VERIFY: the plugin loads in the host app and the badge text updates when I type.
If the host can't run yet, show me the skeleton passes their validator/linter.
```

## Prompt D — Full card UI inside the host

```
Context: CommitGuard plugin skeleton works — draft text reaches the backend and a
text badge renders (files in `plugin/`). Reference UX: `plugin/simulator.html`
(read it — the goal is to port its rendered output into the host's UI surface).
Host SDK notes are in `plugin/SDK_NOTES.md`.

TASK — port the full UX into the host surface:
1. Render the violation CARDS from simulator.html inside the host panel/inline
   area: severity left border (CRITICAL #f85149, HIGH #f0883e, MEDIUM #d29922,
   LOW #8b98a9), category chip, issue, monospace evidence line
   ("brain: <brain_key> = <expected> · found: <found>"), "→ correction" in green,
   quoted span.text when present.
2. Action row with the contract's rules: Apply all fixes (uses top-level
   suggested_rewrite -> write it back into the draft via the SDK's write API; if
   write-back isn't allowed, copy to clipboard + toast "rewrite copied — paste to
   apply"), Send anyway (prompt reason -> APPROVE_OVERRIDE), Escalate to CFO +
   Stage in Round only when CRITICAL exists (ESCALATE_FRAUD / STAGE_INVOICE).
3. Status line + latency exactly like the simulator; health dot polling
   GET /health every 5s; "backend offline" state preserves last render.
4. If the host surface is too small for cards, implement progressive disclosure:
   badge -> click expands a panel; never silently drop information.
VERIFY: in the host app, type the sales_email scenario text (from GET /scenarios)
into a draft — 3 cards appear with correct colors; click Apply all fixes — draft
is replaced and re-verifies to CLEAN. Then the vendor_invoice text — CRITICAL
card, Escalate/Stage buttons, no send path. Report which level you reached.
```

---

# PHASE 3 — LLM enrichment + integration hardening (13:00–14:30)

## Prompt E — LLM second stage (backend/llm_enrich.py — your file)

```
Context: CommitGuard backend. `backend/llm_enrich.py` is the OPTIONAL second stage
after the deterministic rules engine (backend/rules.py — NOT yours). It calls
gpt-4o-mini via OpenAI structured outputs and MUST fail open (any error or no key
-> return None -> caller serves rules-only results). main.py calls llm_enrich and
expects the returned dict to have: status, risk_level, violations (list of dicts),
full_rewrite. Do NOT touch main.py or rules.py.

TASK — upgrade llm_enrich.py:
1. temperature=0; keep timeout=8; keep the OpenAI client lazy-initialized only
   when OPENAI_API_KEY exists.
2. Strict JSON schema — replace the loose violations items with:
   {"type":"object","properties":{"category":{"type":"string"},"severity":
   {"type":"string","enum":["LOW","MEDIUM","HIGH","CRITICAL"]},"issue":
   {"type":"string"},"correction":{"type":"string"},"suggested_rewrite":
   {"type":"string"}},"required":[all five],"additionalProperties":false}
   Keep status/risk_level/full_rewrite fields as they are.
3. Rewrite the prompt to enforce editorial discipline:
   - "Preserve every deterministic violation verbatim unless factually wrong."
   - "Only ADD a violation if it can cite a specific key in the Company Brain
     (name the key in the issue text)."
   - "full_rewrite: fix each violation with minimal edits; preserve greeting,
     sign-off, tone and length; never add commitments, facts, numbers, or dates
     not in the draft or the brain."
   - "If the draft is CLEAN, set violations=[] and full_rewrite=null."
4. Add a `dedupe(llm_violations, deterministic_violations)` helper: drop LLM
   violations whose category already exists in deterministic findings; return
   only net-new ones — expose them under key "extra_violations" so the caller
   can ignore or append without double-flagging.
VERIFY: `cd backend && uv run python smoke_test.py` must be all-green WITHOUT
OPENAI_API_KEY, and WITH it (engine=rules+llm via GET /health). Show both runs.
```

## Prompt F — End-to-end integration proof

```
Context: CommitGuard repo. Backend: `cd backend && uv run uvicorn main:app
--port 8000`. Demo UI at localhost:8000. Simulator at plugin/simulator.html.
API per CONTRACT.md.

TASK: write `plugin/E2E.md` — a numbered, checkboxed end-to-end test script a
human can execute in under 3 minutes covering the full product story:
1. Health: GET /health shows engine + checks count.
2. Sales email scenario -> 3 violations (FINANCIAL_POLICY, MARGIN_BREACH,
   TREASURY_LOCK) each with an evidence line -> Apply all fixes -> re-verifies
   CLEAN -> Send -> audit_log_id returned.
3. Vendor invoice -> CRITICAL PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE ->
   Escalate to CFO -> audit entry; Stage in Round -> message "staged".
4. Send-anyway override on a non-critical violation -> requires reason ->
   audit entry contains the reason.
5. Support reply -> 2 PROMISE_BREACH.
6. Clean email -> CLEAN immediately.
7. Kill backend -> type in draft -> "backend offline" state, no crash.
8. Restart backend, POST /brain/reload -> audit log intact at GET /audit-log.
Then EXECUTE the script yourself via curl where possible and tick off items.
Report a pass/fail table.
```

---

# PHASE 4 — Conditional fallback + stretch (use only as directed)

## Prompt G — Badge fallback (ONLY if told at the 12:30 decision)

```
Context: CommitGuard. The host SDK is blocking full UI; we ship a minimal
integration instead. `plugin/adapter.js` is done. Host SDK notes in
plugin/SDK_NOTES.md.
TASK: plugin renders ONLY a compact badge in the host surface — "⚠ N violations
(risk X)" colored by max severity, or "✓ clear" green — driven by debounced
verifyContext() calls on draft change, plus ONE action "Open details" that opens
http://localhost:8000 in the system browser (or copies the URL to clipboard if
opening is impossible). Nothing else. Minimal code, robust to BACKEND_OFFLINE
(show "— offline"). Verify: badge updates as I type.
```

## Prompt H — Stretch: slack context + settings

```
Context: CommitGuard plugin/simulator working. CONTRACT.md allows context_type
values: outgoing_email, slack_message, incoming_invoice.
TASK:
1. simulator.html: add a context_type selector (auto-set from scenario, manually
   overridable) sent in every verifyContext call.
2. A tiny settings popover in the plugin panel: toggle "auto-verify on typing"
   (default on) and "verify on send attempt" (default on) — persist to
   localStorage.
3. Show which checks ran: meta.checks_run as "· N checks" after latency.
Verify slack_message context passes through (backend may filter rules — that's
fine, just confirm the field arrives: watch Network or backend logs).
```
