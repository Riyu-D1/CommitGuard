# CommitGuard Plugin — Lightfern Mac app

Owner: **Riyansh**. All logic lives in the backend (`http://localhost:8000`) —
this plugin is a thin client. See `CONTRACT.md` for API shapes and
`team/riyansh/PROMPTS.md` for the build prompts.

## What the plugin must do

1. Read the current draft text (Lightfern SDK hook — fill in at event).
2. `POST /verify-context` on change, debounced ~700ms.
3. Render violation cards → severity color, category, issue, evidence line
   (`brain_key` = expected · found), correction.
4. Buttons → `POST /execute-action`:
   - Apply fixes → replace draft with top-level `suggested_rewrite`
   - Send anyway → `APPROVE_OVERRIDE` (prompt for `reason` — required)
   - Escalate to CFO → `ESCALATE_FRAUD` (CRITICAL only)
   - Stage in Round → `STAGE_INVOICE` (invoice context)
5. `severity: CRITICAL` anywhere → hide Send/Send-anyway; Escalate only.

## SDK notes (fill in during the 10:00 Lightfern demo)

- Plugin manifest format:
- How to read draft text:
- UI surface available (panel / inline / toolbar):
- Lifecycle events:
- How actions modify the draft:
