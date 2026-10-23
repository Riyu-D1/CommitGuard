# Person 3 — Demo & Pitch Lead (demo UI + scenarios + the room)

**Mission:** make the demo unforgettable and own the submission. You own `demo/`, `pitch/`, and `backend/scenarios.json` (data only — no `.py` files).

Judges reward: a story they feel, a demo that doesn't break, evidence they can trace. That's your whole job.

## Phases

### Phase 0 — before 10:45
- [ ] `cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt && uv run uvicorn main:app --port 8000` → open `localhost:8000`, click all 4 scenario buttons, confirm cards render
- [ ] Branch `p3/setup`; skim `PLAYBOOK.md` §4 (demo narrative) — that's your act structure

### Phase 1 — 10:45→11:15
- [ ] Confirm demo runs on **venue wifi** (backend is localhost-only, should be fine — verify anyway)
- [ ] `pitch/submission.md`: draft the 100-word submission blurb from PLAYBOOK pitch

### Phase 2 — 11:15→13:00 (M1 gate)
- [ ] **Demo v2** in `demo/index.html`:
  - [ ] Inline underlines: violations with `span` highlight the offending text (contenteditable overlay or mark-up view — simplest robust approach OK)
  - [ ] Violation cards show evidence "receipt" lines prominently (`brain_key` = expected · found)
  - [ ] `context_type` sent per scenario (invoice → different button set: Stage in Round shows)
  - [ ] Polish pass: it should look like a product, not a form
- [ ] PR `p3/demo-v2` → merge at M1

### Phase 3 — 13:00→14:30 (M2 gate)
- [ ] Finalize `backend/scenarios.json` — tighten the 4 texts (invoice should look like a real invoice; keep every violation P2's rules actually fire on — test each after editing!)
- [ ] **Record the backup video**: clean run of all 3 acts + clean pass (~60-90s, silent or narrated). Save as `pitch/backup-demo.mp4` — DO NOT commit if >50MB, keep on your machine
- [ ] `pitch/script.md`: final 90-sec script + Q&A crib (use PLAYBOOK §7-8)
- [ ] PR `p3/scenarios-pitch` → merge at M2

### Phase 4 — 14:30→16:00 (M3 freeze)
- [ ] Rehearse pitch 3x with team watching; time it ≤ 90s
- [ ] Submit via `pitch/submission.md` before 16:00 — not at 16:00, before
- [ ] Final demo run-through on venue wifi AND offline (airplane mode test — rules engine must still work)

## Demo act structure (rehearse to this)

1. **Sales email** → 3 violations, one-click rewrite. Line: *"rep saved the deal's margin without knowing the rules existed"*
2. **CloudScale invoice** → CRITICAL fraud, Send disabled → Escalate to CFO + Stage in Round. Line: *"Round catches this in the ledger; we catch it in the inbox"*
3. **Support reply** → PROMISE_BREACH on SOC 2/SSO. Line: *"don't promise what engineering hasn't shipped"*
4. **Clean pass** → green CLEAR. Line: *"when it's fine, it gets out of your way"*
5. **Kicker** → show `audit_log.jsonl`: *"compliance wants a trail, not magic"*
