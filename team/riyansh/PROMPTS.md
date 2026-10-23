# Riyansh — Agent Prompts

Paste into your coding agent one at a time. Fill `[SDK]` placeholders after the
Lightfern demo. Contract: `CONTRACT.md` (immutable). Your files: `plugin/` +
`_llm_enrich()` in `backend/main.py` only.

---

## Prompt A — Adapter scaffold (~10:45)

```
You are working on CommitGuard, a hackathon project: a "pre-send firewall" that
checks outgoing messages against a company knowledge base and flags violations.

A local backend exists at http://localhost:8000 — read CONTRACT.md in the repo root
for the exact API. I own the plugin layer in `plugin/`.

Task: create `plugin/adapter.ts` (or .js) encapsulating ALL backend communication:
- `verifyContext(text, contextType) -> Promise<VerifyResponse>`
- `executeAction(actionType, payload) -> Promise<ActionResponse>`
- `getAuditLog(limit)`, `getBrain()`, `getScenarios()`
- a `debounce(fn, ms)` helper
- TypeScript interfaces matching CONTRACT.md exactly (Violation, Evidence,
  VerifyResponse, ActionResponse)

Also update `plugin/README.md` "SDK notes" section documenting the UI contract:
what a violation card needs, which buttons call which action_type, and that
severity CRITICAL must hide all send options.

Work only in `plugin/`. Treat CONTRACT.md as immutable.
```

## Prompt B — Plugin UI (~11:15, fill SDK details first)

```
Context: CommitGuard pre-send firewall. Backend at localhost:8000 per CONTRACT.md.
Adapter in `plugin/adapter.ts` is done. The Lightfern plugin SDK works like this:
[PASTE: how plugins are declared/loaded, how to read draft text, UI surface —
panel/inline/toolbar, lifecycle events, required file layout].

Task: implement the plugin so that:
1. On draft text change (debounced 700ms) call verifyContext() with the current
   draft + context_type "outgoing_email".
2. Render violations as cards: severity color (CRITICAL #f85149, HIGH #f0883e,
   MEDIUM #d29922), category chip, issue, evidence line
   ("brain: <evidence.brain_key> = <expected> · found: <found>"), correction.
3. Status line: "engine: <meta.engine> · <meta.latency_ms>ms".
4. CLEAN state: subtle green "CLEAR — brain-backed send" indicator.

Minimal and correct beats pretty. Only edit `plugin/`.
```

## Prompt C — Actions & audit feed (~13:00)

```
Context: CommitGuard plugin in `plugin/` — verify + render works. API per CONTRACT.md.

Task — finish the interaction layer:
1. Buttons per CONTRACT.md: "Apply fixes" (replace draft with top-level
   suggested_rewrite, re-verify), "Send anyway" (prompt reason → APPROVE_OVERRIDE),
   "Escalate to CFO" (ESCALATE_FRAUD) + "Stage in Round" (STAGE_INVOICE) shown when
   any CRITICAL exists — in that case hide all send options.
2. Confirmation toast/inline text after executeAction showing message + audit_log_id.
3. Disable Apply-fixes when suggested_rewrite is null.
4. Small audit feed polling GET /audit-log?limit=6 every 4s.
5. If violation has span {start,end} and SDK supports decoration, underline it;
   else quote span.text in the card.

Only edit `plugin/`. Verify all 4 buttons end-to-end against the running backend.
```

## Prompt D — LLM enrichment (~13:30, your AI-lead task)

```
Context: CommitGuard backend `backend/main.py`. `_llm_enrich()` calls gpt-4o-mini
with strict json_schema structured output; it fails open (None → rules-only).
Darsh owns the rest of backend — touch ONLY this function.

Task:
1. Add temperature=0, keep the 8s timeout and fail-open behavior.
2. Tighten schema: violations items get strict shape {category, severity, issue,
   correction, suggested_rewrite} — all required strings (suggested_rewrite may
   be ""); keep full_rewrite as string|null.
3. Prompt: instruct the model to (a) keep every deterministic violation verbatim
   unless factually wrong, (b) only ADD violations citing a specific brain key,
   (c) produce full_rewrite preserving greeting/sign-off/tone, fixing violations
   with minimal edits, never adding new commitments or facts.
4. Merge: map LLM suggested_rewrite onto deterministic violations by category;
   top-level suggested_rewrite = llm full_rewrite else rules.apply_fixes result.
Verify: `cd backend && uv run python smoke_test.py` passes with and without
OPENAI_API_KEY set; engine shows rules+llm only when key present.
```

## Prompt E — Fallback badge (pocket — only if SDK blocks you at 12:30)

```
Context: CommitGuard. Lightfern SDK is blocking full UI; falling back to minimal
integration. Task: plugin renders ONLY a compact badge — "⚠ N violations (risk
HIGH)" or "✓ clear" — from verifyContext() calls, plus one "Open details" button
opening http://localhost:8000 in the default browser. Minimal code in `plugin/`.
```
