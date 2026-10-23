# Riyansh — Agent Prompts

Run your agent continuously: finish a prompt → verify → paste the next.
Fill `[SDK]` placeholders after the Lightfern demo. Contract: `CONTRACT.md` (immutable).
Your files: `plugin/` and `backend/llm_enrich.py`.

---

## Prompt A — Adapter + simulator (~10:45)

```
You are working on CommitGuard, a hackathon project: a "pre-send firewall" that
checks outgoing messages against a company knowledge base and flags violations.
Backend at http://localhost:8000 — read CONTRACT.md in the repo root for the API.

Two deliverables, all inside `plugin/`:

1. `plugin/adapter.js` — ALL backend communication:
   - `verifyContext(text, contextType)`, `executeAction(actionType, payload)`,
     `getAuditLog(limit)`, `getBrain()`, `getScenarios()`
   - a `debounce(fn, ms)` helper
   - JSDoc typedefs matching CONTRACT.md exactly

2. `plugin/simulator.html` — a single-file mock of the host app our plugin will
   live in. It simulates the plugin lifecycle so UI logic can be built before the
   real SDK exists:
   - a compose textarea (the "draft"), a "Load scenario" dropdown that fills it
     from GET /scenarios, and a side panel = our plugin surface
   - on textarea input (debounced 700ms) call verifyContext() and render violation
     cards in the panel: severity color (CRITICAL #f85149, HIGH #f0883e, MEDIUM
     #d29922), category chip, issue, evidence line ("brain: <evidence.brain_key>
     = <expected> · found: <found>"), correction
   - status line: "engine: <meta.engine> · <meta.latency_ms>ms"; CLEAN → green
     "CLEAR — brain-backed send"
   - buttons: Apply fixes (replace textarea with top-level suggested_rewrite,
     re-verify), Send anyway (prompt reason → APPROVE_OVERRIDE), and when any
     CRITICAL: hide send options, show "Escalate to CFO" (ESCALATE_FRAUD) +
     "Stage in Round" (STAGE_INVOICE)
   - toasts showing action message + audit_log_id
   - small audit feed polling GET /audit-log?limit=6 every 4s
   Dark theme, single file, vanilla JS. Import adapter.js via <script src>.
```

## Prompt B — Port to real SDK (~11:15, fill SDK details first)

```
Context: CommitGuard. `plugin/simulator.html` + `plugin/adapter.js` are done and
verified — the card UI and action wiring work against the live backend
(localhost:8000, CONTRACT.md).

The Lightfern plugin SDK works like this: [PASTE: manifest format, how plugins
are declared/loaded, how to read the current draft text, UI surface (panel/
inline/toolbar), lifecycle events, how to write back into the draft].

Task: port the simulator's plugin-surface logic into a real plugin:
1. Manifest + file layout per SDK requirements.
2. Draft text → verifyContext() on change (debounced 700ms), context_type
   "outgoing_email".
3. Same cards, same buttons, same CRITICAL lockout — reuse adapter.js calls and
   the simulator's render code wherever the SDK surface allows.
4. Apply fixes → write suggested_rewrite back to the draft via the SDK's write
   API (or clipboard/instruction if read-only).
If the SDK surface can't host cards, render a compact badge — "⚠ N violations
(risk HIGH)" / "✓ clear" — with a details action. Tell me which level you reached.
```

## Prompt C — Plugin actions & audit (~13:00)

```
Context: CommitGuard plugin in `plugin/` — verify + render working (simulator or
real SDK). API per CONTRACT.md.

Task — finish interaction polish:
1. Toast/inline confirmation after every executeAction: message + audit_log_id.
2. Disable Apply-fixes when suggested_rewrite is null.
3. Audit feed: poll GET /audit-log?limit=6 every 4s, render compact entries
   (action_type, audit_log_id, time).
4. If violation has span {start,end} and the surface supports it, underline the
   range in the draft; else quote span.text inside the card.
5. Empty state for zero violations and a subtle loading state during requests.
Verify all 4 buttons end-to-end. Only edit `plugin/`.
```

## Prompt D — LLM enrichment (~13:30, in backend/llm_enrich.py)

```
Context: CommitGuard backend. `backend/llm_enrich.py` is mine — it calls
gpt-4o-mini with strict json_schema structured output and fails open (returns
None → rules-only). main.py calls it as the optional second stage after the
deterministic rules in rules.py (NOT my file — don't touch it).

Task — harden llm_enrich.py:
1. Add temperature=0; keep timeout=8 and fail-open.
2. Tighten schema: violations items get strict shape {category, severity, issue,
   correction, suggested_rewrite} — all required strings (suggested_rewrite may
   be ""); full_rewrite stays string|null.
3. Prompt rewrite: (a) keep every deterministic violation verbatim unless
   factually wrong, (b) only ADD violations citing a specific brain key,
   (c) full_rewrite preserves greeting/sign-off/tone, fixes violations with
   minimal edits, never adds new commitments or facts.
4. main.py already merges llm output — check the merge loop handles the new
   strict items (it maps suggested_rewrite by category onto deterministic
   violations; fix only if broken — main.py edits need a PR flag).
Verify: `cd backend && uv run python smoke_test.py` green with and without
OPENAI_API_KEY; with key, engine reports rules+llm via GET /health.
```

## Prompt E — Fallback badge (pocket — only if SDK blocks you at 12:30)

```
Context: CommitGuard. Lightfern SDK is blocking full UI; fallback needed.
Task: make `plugin/` render ONLY a compact badge — "⚠ N violations (risk HIGH)"
or "✓ clear" — driven by verifyContext() calls, plus an "Open details" action
launching http://localhost:8000 in the default browser. Minimal code.
```
