# Pranali — Frontends + Content

Everyone codes via agents all day — you included. Your workflow: paste prompt →
agent builds → you verify at http://127.0.0.1:8000 by clicking → next prompt.
**Your build lives in `PROMPTS.md` — execute it top-to-bottom.**

## Your files (nobody else touches them)

- `demo/` — index.html (flagship UI) + inspector.html (compliance console)
- `pitch/` — script, submission, rehearsal sheet, one-pager, backup video
- `backend/scenarios.json` — the 4 demo texts (data only — never `*.py`)

## Phase map

| Phase | Time | Prompts | Done when |
|---|---|---|---|
| 1 — Flagship UI | 10:45–13:00 | A (full compose rebuild) → B (micro-polish) | 4 scenarios + cards + evidence receipts + offline state all verified → **M1** |
| 2 — Inspector + scenarios | 13:00–14:00 | C (inspector.html) → D (encode your texts) | console populates live; your texts encoded, smoke green |
| 3 — Pitch artifacts | 14:00–14:45 | E (submission + rehearsal sheet) → F (one-pager) | submission.md ready to paste → **M2** |
| 4 — Non-agent tasks | interleaved | see below | video + rehearsal + submit |

## Non-agent tasks (interleave with the phases)

- **Write scenario texts** (while agent runs Prompt A): 4 realistic texts in a
  notes doc — the invoice must fool a finance judge; keep trigger strings
  (wrong IBAN, £85/hr, £6,200+ total, "updated bank details" / Net-60, 15%,
  quarterly / SOC 2 "complete", SSO "live" / Net-30, 10%, monthly+50% upfront).
  Feed them to the agent via Prompt D — never hand-edit JSON.
- **Backup video** ~14:00 (`pitch/backup-demo.mp4`, 60–90s, all 3 acts + clean
  pass) — mandatory insurance.
- **Rehearsal** 14:30–15:30: 2 timed run-throughs using rehearsal-sheet.md.
  You deliver the pitch.
- **Submit before 16:00** from `pitch/submission.md`. Before, not at.
- **Airplane-mode test** ~15:45: wifi off → demo still verifies → tell Riyansh if not.

## The two commands you'll ever need

```bash
./start.sh                                        # from repo root — does everything
open http://127.0.0.1:8000                        # the demo (use 127.0.0.1, not localhost)
```
Errors → screenshot → Riyansh. Don't debug.

## Demo act structure (your pitch spine)
1. Sales email → 3 violations → one-click fix. *"Rep saved the margin without knowing the rules."*
2. Invoice → CRITICAL → Escalate/Stage-in-Round. *"Round catches it in the ledger; we catch it in the inbox."*
3. Support reply → PROMISE_BREACH. *"Don't promise what engineering hasn't shipped."*
4. Clean pass → green. *"When it's fine, it gets out of your way."*
5. Inspector page / `audit_log.jsonl`. *"Compliance wants receipts, not magic."*
