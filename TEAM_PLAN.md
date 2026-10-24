# CommitGuard — Team Plan (Hackathon Day)
**Sat 24 Oct · Build 11:05→15:00 freeze (4h) · submit by 15:45 · Track: Finance/Ops (Round Treasury)**
Register team + track BEFORE the 11:15 deadline — do it in the first 15 min.

Read `PLAYBOOK.md` for pitch/judge strategy. Read `CONTRACT.md` before writing any code.
**On the day itself, `TOMORROW.md` is the operating doc — this file is the deep plan.**

---

## Operating model — everyone codes constantly

All three run coding agents in parallel all day. The file-ownership table below
exists so three agents never touch the same file → PRs merge clean every time.

## Roles & file ownership

| Person | Owns | Never touches |
|---|---|---|
| **Riyansh** — Backend API + LLM · merge-master | `backend/main.py`, `backend/llm_enrich.py`, `E2E.md`, `CONTRACT.md`, `plugin/` (only if 12:30 GO) | other backend files, `demo/`, `pitch/` |
| **Darsh** — Backend rules, actions & data | `backend/rules.py`, `actions.py`, `company_brain.json`, `scenarios.json`, `smoke_test.py`, `bench.py`, `seed_audit.py` | `main.py`, `llm_enrich.py`, `demo/`, `plugin/`, `pitch/` |
| **Pranali** — All frontend | `demo/` (all), `pitch/` (all) | `backend/` (everything), `plugin/` (moved to Riyansh today) |

Shared docs (`CONTRACT.md`, `TEAM_PLAN.md`, `README.md`, `TOMORROW.md`): PR + flag in chat.

## Git workflow

- Branches: `riyansh/phase<N>`, `darsh/phase<N>`, `pranali/phase<N>`. **Always cut from fresh main** (`git checkout main && git pull && git checkout -b ...`); never reuse a squash-merged branch.
- **Rolling phases:** start your next phase as soon as your own PR merges; no all-3 barrier.
- PR → `main`, **squash merge**, delete branch after.
- Riyansh merges each PR within ~5 min of "PR up", after `smoke_test.py` prints ALL PASS on that branch. If several wait: `darsh/*` → `pranali/*` → `riyansh/*`.
- Keep `main` runnable: `cd backend && uv run uvicorn main:app --port 8000` must always work on main.
- Rule for agents: "verify before you're done" is in every prompt — respect it.

## Shared stretch queue — grab when your list empties (claim in chat first!)

- [ ] `POST /verify-batch` endpoint (array of texts → array of results) — needs main.py flag
- [ ] Second client: `slack_message` context_type scenario + any rule tweaks
- [ ] `pitch/one-pager.html` judge handout (Pranali)
- [ ] Latency stat for pitch (Darsh's bench.py)
- [ ] Demo seed: pre-fill audit_log.jsonl with 5 realistic entries so Inspector isn't empty at demo time

## Timeline & merge checkpoints (4-hour version: full table in `TOMORROW.md`)

| Time | Gate | Everyone |
|---|---|---|
| 11:05–11:15 | **Register Finance/Ops track** (Riyansh) | All: pull main, server runs, smoke test prints the 4 baseline results. |
| 11:15–12:45 | **M1 — working slice** | Darsh P1 (smoke gate + fraud rules) by 12:00, P2 (actions) by 12:40. Riyansh P2 (llm advisories) by 12:15. Pranali P1 (demo UI) by 12:45. **12:30 = plugin GO/NO-GO.** |
| 12:45–14:30 | **M2 — integrated** | Darsh P3 by 13:30, P4 by 14:15 (optional). Pranali P2 Inspector by 13:45, P3 pitch by 14:20. Riyansh P3 E2E by 14:15. **14:30 code complete.** |
| 14:30–15:00 | **M3 — record** | Riyansh resets demo data (`seed_audit.py --reset`); Pranali records backup video on final main. |
| 15:00 | **FREEZE** | Demo-blockers only. Rehearse x3 (15:00–15:30), airplane test 15:30. |
| by 15:45 | Submit | **Pranali submits** from `pitch/submission.md`, before 16:00, not at it. |

## Definition of done — M1 (the "it works" gate)

- [ ] `POST /verify-context` returns violations for all 4 scenarios (rules-only OK)
- [ ] Plugin OR demo renders at least one violation card live
- [ ] "Apply all fixes" logs `APPLY_REWRITE_AND_LOG` (with the violations) to `audit_log.jsonl` (built in Pranali P1; it did not log before)
- [ ] `smoke_test.py` asserts the baseline and exits non-zero on drift (Darsh P1)

## Definition of done — M2 (the "wow" gate)

- [ ] All 4 demo scenarios pass end-to-end in the plugin (or demo.html fallback)
- [ ] CRITICAL invoice → Escalate + Stage-in-Round buttons work
- [ ] Evidence lines show `brain_key` receipts on every violation
- [ ] Inspector stats strip + audit trail with expandable evidence (Pranali P2)
- [ ] Backup video recorded on final main (14:30–14:50)
- [ ] 90-sec pitch rehearsed x3 (15:00–15:30)

## Fallback ladder (if the plugin SDK fights us)

1. Full Lightfern plugin (target)
2. Plugin renders minimal banner + opens demo.html for details
3. demo.html only, framed as "the same check runs anywhere text leaves the company"
4. Backup screen recording (worst case — still submit)

Decide at **12:30 sharp**: if plugin can't render a card by then, escalate down the ladder and don't look back.
If GO, Riyansh (not Pranali) runs the plugin prompt; Pranali stays on demo → Inspector → pitch.
