# TODAY — the only doc you need (4-hour build: 11:05 → 15:00 freeze → submit by 15:45)

**Phase rule (changed 11:05): rolling phases.** Paste your Phase-N prompt → PR → as soon as YOUR PR is merged,
start Phase N+1. **Don't wait for teammates.** Lanes never overlap, so lockstep only added idle time.
The only real cross-dependency is Riyansh Phase 3 (E2E), which runs after Darsh Phase 3 merges.

## Who owns what (touch nothing else)

| Person | Files | Extra duty |
|---|---|---|
| **Riyansh** | `backend/main.py`, `backend/llm_enrich.py`, `E2E.md`, `CONTRACT.md`, `plugin/` (only if GO at 12:30) | Merge-master (rolling, ≤5 min per PR). Registers Finance/Ops by 11:15. 12:30 plugin call. 14:30 demo-data reset. |
| **Darsh** | everything else in `backend/` (rules.py, actions.py, company_brain.json, scenarios.json, smoke_test.py, bench.py, seed_audit.py) | `smoke_test.py` → ALL PASS before every commit |
| **Pranali** | `demo/` + `pitch/` | Critical path. Backup video 14:30 · submits by 15:45 |

## Every phase

1. `git checkout main && git pull && git checkout -b <you>/phase<N>` (always from fresh main, never reuse a branch)
2. Restart the server after pulling: Ctrl-C, then `./start.sh` from the repo root
3. Paste the ENTIRE fenced block for Phase N from `team/<you>/PROMPTS.md` into Codex/Devin → run its VERIFY yourself
4. `git add -A && git commit -m "<you> phase <N>" && git push -u origin HEAD && gh pr create --fill` (skip if Devin opened the PR)
5. Post "<you> phase N up". Riyansh merges within ~5 min, then you start the next phase.

## Schedule (targets = PR merged)

| Time | Riyansh | Darsh | Pranali |
|---|---|---|---|
| 11:05–11:15 | **Register Finance/Ops track** | pull main, `smoke_test.py` | pull main, `./start.sh` |
| 11:15 | P2 llm_enrich + advisories → **12:15** | P1 smoke gate + 3 fraud rules → **12:00** | P1 demo UI → **12:45** |
| 12:30 | **Plugin GO/NO-GO.** GO → Riyansh runs the plugin prompt | P2 actions → **12:40** | (P1 continues) |
| 12:45 | merges / plugin (if GO) | P3 context filter + brain → **13:30** | P2 Inspector dashboard → **13:45** |
| 13:30 | P3 E2E.md + CONTRACT → **14:15** | P4 bench/seed/risk_score → **14:15** (skip if not started by 13:45) | P3 pitch package → **14:20** |
| **14:30** | **Code complete.** Demo laptop: pull, restart, smoke + bench, `seed_audit.py --reset` → "ready" | fix-only | record backup video on final main (14:30–14:50) |
| **15:00** | **FREEZE**: demo-blockers only | | rehearse x3 (15:00–15:30) |
| 15:30 | | | airplane-mode test |
| **by 15:45** | | | **submit** `pitch/submission.md` |

Plugin ladder (12:30 call): plugin+backend → plugin badge that opens the demo → demo/index.html only → video.
The inlined `rules.js` port is only an option if started before 13:00.

## Cut list (if behind at 13:30, cut from the top)

1. Darsh P4 (bench + seed scripts already exist; Riyansh runs them by hand)
2. Riyansh P3 E2E.md (smoke test + bench output are enough proof)
3. Darsh P3 brain expansion (item 3) and UNVERIFIED_CLAIM (item 2). Keep context filtering.
4. Inspector row-expand (keep stats strip + audit table)
Never cut: demo UI P1, Inspector stats + audit trail, pitch P3, backup video.

## Demo mode

Run the demo with `OPENAI_API_KEY` **unset** unless Riyansh has tested LLM mode end-to-end (rules-only is deterministic and instant).
Use 127.0.0.1, never localhost.

Stuck >10 min → paste the error in chat, tag Riyansh.
Details: `TEAM_PLAN.md` · API contract: `CONTRACT.md`
