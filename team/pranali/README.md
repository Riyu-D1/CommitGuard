# Pranali — Frontends + Content (demo UI, inspector page, scenarios, pitch)

Everyone codes via agents all day — you included. Your workflow: paste prompt →
agent builds → you verify by clicking http://localhost:8000 → next prompt. You
never hand-write code; you own the judgment calls (does it look real? will judges
feel it?).

## Your files

- `demo/` — everything (index.html + inspector.html you create)
- `pitch/` — script, submission, rehearsal sheet, backup video
- `backend/scenarios.json` — the 4 demo texts (data only — never `*.py`)

## The two commands you'll ever need

```bash
cd backend && uv run uvicorn main:app --port 8000   # start backend (once)
open http://localhost:8000                         # the demo
```
If a command errors → screenshot → hand to Riyansh. Don't debug.

## Phases (stay on your agent constantly)

### Phase 0 — before 10:45
- [ ] Demo running; click all 4 scenario buttons; read `pitch/script.md` + PLAYBOOK §4
- [ ] Branch `pranali/setup`

### Phase 1 — 10:45→11:15
- [ ] **Prompt A** (demo v2 inline highlights) — start immediately, it's your biggest build
- [ ] During sponsor talks: note Round Treasury's exact words — pitch should echo them

### Phase 2 — 11:15→13:00 (M1)
- [ ] Finish Prompt A → verify all 4 scenarios → PR `pranali/demo-v2` → M1
- [ ] **Prompt B** (polish pass) then **Prompt C** (inspector page — the compliance console judges will love)
- [ ] Meanwhile: rewrite the 4 scenario TEXTS in a doc (writing, not code — the invoice must look real enough to fool a finance judge; keep trigger strings: wrong IBAN, £85/hr, £6,200+ total)

### Phase 3 — 13:00→14:30 (M2)
- [ ] **Prompt D** (encode your texts into scenarios.json via agent — never hand-edit JSON)
- [ ] **Prompt E** (submission.md + rehearsal sheet)
- [ ] **Record `pitch/backup-demo.mp4`** (60–90s, all 3 acts + clean pass) — mandatory insurance
- [ ] PRs `pranali/inspector` + `pranali/scenarios-pitch` → M2

### Phase 4 — 14:30→16:00 (M3)
- [ ] 2 pitch run-throughs timed ≤90s; **submit before 16:00** from submission.md
- [ ] Airplane-mode test: wifi off → demo still works → tell Riyansh if not

### Stretch queue
- Prompt F: one-page architecture/judge handout (`pitch/one-pager.html`)
- Slack-message scenario text (context_type: slack_message) — coordinate with Darsh on what fires

## Demo act structure (your pitch spine)
1. Sales email → 3 violations → one-click fix. *"Rep saved the margin without knowing the rules."*
2. Invoice → CRITICAL → Escalate/Stage-in-Round. *"Round catches it in the ledger; we catch it in the inbox."*
3. Support reply → PROMISE_BREACH. *"Don't promise what engineering hasn't shipped."*
4. Clean pass → green. *"When it's fine, it gets out of your way."*
5. `audit_log.jsonl` / inspector page. *"Compliance wants receipts, not magic."*
