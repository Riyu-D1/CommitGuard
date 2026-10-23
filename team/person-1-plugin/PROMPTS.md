# Person 1 — Agent Prompts

Paste these into your coding agent (Devin/Cursor/etc.) one phase at a time.
Fill in `[SDK]` details once the Lightfern demo reveals the real API.

---

## Prompt A — Adapter scaffold (use at ~10:45, before SDK details known)

```
You are working on CommitGuard, a hackathon project: a "pre-send firewall" that checks
outgoing messages against a company knowledge base and flags violations.

I own the plugin layer in `plugin/` of this repo. A local backend already exists at
http://localhost:8000 — read CONTRACT.md in the repo root for the exact API.

Task: create `plugin/adapter.ts` (or .js) that encapsulates ALL backend communication:
- `verifyContext(text: string, contextType: string) -> Promise<VerifyResponse>`
- `executeAction(actionType: string, payload: object) -> Promise<ActionResponse>`
- A `debounce(fn, ms)` helper.
- TypeScript interfaces matching CONTRACT.md exactly (Violation, VerifyResponse, etc.).

Also write `plugin/README.md` documenting the adapter interface and the UI contract:
what data a violation card needs, which buttons call which action_type, and that
severity CRITICAL must hide Send/override options.

Do not touch anything outside `plugin/`. The backend is someone else's code — treat
CONTRACT.md as immutable.
```

## Prompt B — Plugin UI (use at ~11:15, fill in SDK details)

```
Context: CommitGuard pre-send firewall. Backend at localhost:8000 per CONTRACT.md.
The adapter in `plugin/adapter.ts` is done. The Lightfern plugin SDK works like this:
[PASTE what you learned: how plugins are declared, how to read draft text, how to
render UI — panel/inline/toolbar, lifecycle events, where files must live].

Task: implement the plugin so that:
1. When the draft text changes (debounced 700ms), call verifyContext().
2. Render violations as cards: severity color (CRITICAL=#f85149, HIGH=#f0883e,
   MEDIUM=#d29922), category chip, issue text, evidence line
   ("brain: <evidence.brain_key> = <expected> · found: <found>"), correction.
3. Buttons: "Apply fixes" (replaces draft with top-level suggested_rewrite, then
   re-verifies), "Send anyway" (prompt for reason → APPROVE_OVERRIDE), and when a
   CRITICAL exists: only "Escalate to CFO" (ESCALATE_FRAUD) + "Stage in Round"
   (STAGE_INVOICE) — hide send options.
4. Status line: "engine: <meta.engine> · <meta.latency_ms>ms".

Keep it minimal — clarity beats polish at this phase. Work only in `plugin/`.
```

## Prompt C — Actions & polish (use ~13:00)

```
Context: CommitGuard plugin in `plugin/` — verify render works. API per CONTRACT.md.

Task: finish the interaction layer:
1. Toast/inline confirmation showing `message` + `audit_log_id` after executeAction.
2. Disable Apply-fixes when suggested_rewrite is null.
3. Show audit trail entries in a small feed: poll GET /audit-log?limit=6 every 4s.
4. If any violation has `span` {start,end}, underline that range in the draft if the
   SDK allows decoration; if not, quote `span.text` inside the card.
5. Empty state: when status=CLEAN show a green "CLEAR — brain-backed send" state.

Only edit `plugin/`. Verify by running the backend and exercising all 4 buttons.
```

## Prompt D — Fallback badge (keep in pocket, use only if SDK blocks you ~12:30)

```
Context: CommitGuard. The Lightfern SDK is blocking full UI work, so we fall back to a
minimal integration. Task: make the plugin render ONLY a compact status badge —
"⚠ N violations (risk HIGH)" or "✓ clear" — from GET-ready verifyContext() calls,
plus one button "Open details" that launches http://localhost:8000 (our demo UI) in
the default browser. Nothing else. Minimal code in `plugin/`.
```
