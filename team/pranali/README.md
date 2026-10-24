# Pranali — frontend (everything the judges see)

**Your folders today:** `demo/` · `pitch/`  (`plugin/` moved to Riyansh: only needed if he calls GO at 12:30)
**Never touch:** `backend/` (Darsh + Riyansh)
**Want different demo wording?** Write the text, hand it to Darsh. `backend/scenarios.json` is his file.

## The day: you are the critical path

Rolling phases: start the next one as soon as YOUR PR merges, no waiting for the others.
Always start with `git checkout main && git pull && git checkout -b pranali/phase<N>`, then restart `./start.sh`.

| Phase | What | Merged by |
|---|---|---|
| 1 | Demo UI (cards, receipts, highlights, every action logged) | 12:45 |
| 2 | Inspector dashboard (stats strip, audit trail with evidence, brain) | 13:45 |
| 3 | Pitch package (uses real numbers from main) | 14:20 |
| 4 | Backup video, rehearsal, submit (you, not an agent) | see below |

Running 20 min late on a phase? Ship what works, move on.
Any error → screenshot → paste to Riyansh. **Never debug code yourself.**

## The two commands you'll ever need

```bash
./start.sh                       # from repo root: starts everything (Ctrl-C + rerun after every git pull)
open http://127.0.0.1:8000       # the demo (use 127.0.0.1, not localhost)
```

## Your non-agent moments

- **14:30–14:50**: record 2-min backup video on final main, after Riyansh says "ready" (demo data reset)
- **15:00–15:30**: rehearse pitch x3 (`pitch/script.md`, `pitch/rehearsal-sheet.md`)
- **15:30**: airplane-mode test: wifi off → demo still works → tell Riyansh if not
- **by 15:45**: submit `pitch/submission.md`. Before 16:00, not at it.
