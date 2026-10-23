# Person 1 — Plugin Lead (Lightfern Mac app integration)

**Mission:** get CommitGuard's violation cards rendering inside Lightfern's Mac app plugin runtime. You own `plugin/` and nothing else.

## Interface you build against

- Backend: `http://localhost:8000` — see `CONTRACT.md` for exact shapes.
- Flow: capture draft text → `POST /verify-context` (debounced ~700ms on input) → render violation cards → buttons → `POST /execute-action`.
- Card needs: severity color, category chip, issue, evidence line (`evidence.brain_key` = expected · found), correction.
- Buttons: **Apply fixes** (use top-level `suggested_rewrite`), **Send anyway** (prompt reason → `APPROVE_OVERRIDE`), **Escalate to CFO** (`ESCALATE_FRAUD`, CRITICAL only), **Stage in Round** (`STAGE_INVOICE`, invoice context).
- CRITICAL severity → no Send/Send-anyway, Escalate only.

## Phases

### Phase 0 — before 10:45
- [ ] Clone repo, create branch `p1/setup`
- [ ] Skim `CONTRACT.md`, run backend (`cd backend && uv run uvicorn main:app --port 8000`), curl `/verify-context` once
- [ ] Open `plugin/` — write `plugin/README.md` skeleton: "adapter contract" (what the plugin must do) so the design is fixed before SDK details land

### Phase 1 — 10:45→11:15 (during talks + registration)
- [ ] Watch the Lightfern demo for: how plugins are declared/loaded, what UI surface exists (panel? inline? toolbar?), how to read draft text, how to get lifecycle events
- [ ] Ask their team ONE sharp question early: "how do I read the current draft text and render a custom panel?"
- [ ] PR `p1/setup`: hello-world plugin + README documenting actual SDK API → **merge at M0**

### Phase 2 — 11:15→13:00 (M1 gate)
- [ ] Plugin polls `/verify-context` on draft change, renders 1 violation card
- [ ] PR `p1/verify-render` → merge at M1 (13:00)
- [ ] **12:30 decision point:** if no card renders, escalate to fallback ladder (TEAM_PLAN.md §Fallbacks) — tell the team, don't suffer silently

### Phase 3 — 13:00→14:30 (M2 gate)
- [ ] All 4 buttons wired to `/execute-action`; toasts/acknowledgements
- [ ] Severity styling + CRITICAL lockout
- [ ] PR `p1/actions` → merge at M2

### Phase 4 — 14:30→16:00 (M3 freeze)
- [ ] Demo-blocker fixes only; rehearse your 20-second segment of the pitch
- [ ] Final PR → merge, done

## Fallback ladder (yours to execute if needed)

1. Full plugin card UI ← target
2. Plugin shows "⚠ N violations" badge + button that opens `localhost:8000` demo page
3. demo.html standalone (P3 owns it — you just make sure it's running)
4. Backup video
