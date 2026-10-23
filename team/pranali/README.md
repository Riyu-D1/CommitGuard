# Pranali — Demo, Pitch & Story Lead

You own `demo/`, `pitch/`, and `backend/scenarios.json`. You don't need to write
code — your tools are: **writing** (scenario texts, pitch, submission), **the demo
itself** (clicking through it, judging what judges will feel), **recording** (backup
video), and **agent prompts** in PROMPTS.md (paste them whole; the agent does the
technical work — you just verify by clicking).

## The two commands you'll ever need

```bash
# Start the demo (once per day — if it's already running, skip):
cd backend && uv run uvicorn main:app --port 8000

# Open in browser:
http://localhost:8000
```

If the browser shows the CommitGuard page with scenario buttons, you're golden.
If a command fails, hand the error to Riyansh — don't debug it yourself.

## Your job in one line

Make the 90 seconds on stage unforgettable, and make sure nothing in the demo
looks fake to a judge who reads invoices for a living (Round Treasury does).

## Phases

### Phase 0 — before 10:45
- [ ] Open localhost:8000, click each of the 4 scenario buttons, watch the cards
- [ ] Read `PLAYBOOK.md` §2-4 (positioning + demo narrative) and `pitch/script.md`
- [ ] Branch `pranali/setup`

### Phase 1 — 10:45→11:15
- [ ] During sponsor talks, note words Round Treasury uses — our pitch should echo them
- [ ] **Prompt D**: generate `pitch/submission.md` (100-word blurb + bullets) — review it as a human, edit freely, it's yours

### Phase 2 — 11:15→13:00 (M1 gate)
- [ ] **Prompt A**: demo v2 (inline highlights + evidence receipts) — then click every scenario button to verify
- [ ] **Rewrite the scenario texts** — this is pure writing, your highest-value task:
  - `vendor_invoice`: make it look like a REAL invoice (line items, VAT, payment instructions) — keep the wrong IBAN, £85/hr, £6,200+ total (those trigger the catches)
  - `sales_email`: a believable sales follow-up containing Net-60, 15% discount, quarterly billing
  - `support_reply`: believable support tone claiming SOC 2 "complete" + SSO "live"
  - `clean_email`: Net-30, 10%, monthly/50% upfront only — must stay CLEAN
  - Write them in a doc first → **Prompt C** encodes them into `backend/scenarios.json` via the agent (never hand-edit JSON)
- [ ] PR `pranali/demo-v2` → merge at M1

### Phase 3 — 13:00→14:30 (M2 gate)
- [ ] **Record the backup video** (`pitch/backup-demo.mp4`, 60–90s): clean run of all 3 acts + clean pass. This is our insurance if wifi dies — treat it as mandatory
- [ ] Rehearse `pitch/script.md` out loud twice; tighten any line that sounds unnatural in your mouth — you're delivering it
- [ ] Finalize `pitch/submission.md`
- [ ] PR `pranali/scenarios-pitch` → merge at M2

### Phase 4 — 14:30→16:00 (M3 freeze)
- [ ] Two full pitch run-throughs with the team, timed ≤ 90s
- [ ] **Submit before 16:00** — paste from `pitch/submission.md`; not at 16:00, before
- [ ] Airplane-mode test: turn wifi off, run the demo once — must still work (rules engine is offline; if not, tell Riyansh immediately)

## Demo act structure (your spine for the pitch)

1. Sales email → 3 violations → one-click fix. *"Rep saved the margin without knowing the rules."*
2. Invoice → CRITICAL fraud → Escalate/Stage-in-Round. *"Round catches it in the ledger; we catch it in the inbox."*
3. Support reply → promise breaches. *"Don't promise what engineering hasn't shipped."*
4. Clean pass → green. *"When it's fine, it gets out of your way."*
5. Show `audit_log.jsonl`. *"Compliance wants receipts, not magic."*
