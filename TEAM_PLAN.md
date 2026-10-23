# CommitGuard — Team Plan (Hackathon Day)
**Sat 24 Oct · Build 10:45→16:00 · Track: Finance/Ops (Round Treasury)**
Register team + track BEFORE the 11:15 deadline — do it in the first 15 min.

Read `PLAYBOOK.md` for pitch/judge strategy. Read `CONTRACT.md` before writing any code.

---

## Roles & file ownership

| Person | Owns | Never touches |
|---|---|---|
| **P1 — Plugin** | `plugin/` | `backend/`, `demo/` (except CONTRACT discussion) |
| **P2 — Backend** | `backend/*.py`, `backend/company_brain.json` | `demo/`, `plugin/` |
| **P3 — Demo & Pitch** | `demo/`, `pitch/`, `backend/scenarios.json` (data only) | `backend/*.py`, `plugin/` |

Shared files (`CONTRACT.md`, `TEAM_PLAN.md`, `README.md`): edits by PR only, flag in chat.

## Git workflow

- Branches: `p1/<thing>`, `p2/<thing>`, `p3/<thing>` — one feature per branch, small PRs.
- PR → `main`, **squash merge**, delete branch after.
- **Merge order at checkpoints: backend → demo → plugin** (dependents merge last).
- Rebase/merge `main` into your branch at every checkpoint — don't drift.
- Keep `main` runnable at all times: `cd backend && uv run uvicorn main:app --port 8000` must always work on main.

## Timeline & merge checkpoints

| Time | Gate | Everyone |
|---|---|---|
| 09:30–10:45 | — | Venue, talks. P1 notes Lightfern plugin SDK shape from demo. All: skim PLAN files. |
| 10:45–11:15 | **Register Finance/Ops track** | P1: plugin hello-world (renders anything). P2: env up, `smoke_test.py` green. P3: demo runs at :8000 on venue wifi. |
| 11:15–13:00 | **M1 — working slice** | P1: plugin calls `/verify-context` + renders 1 violation card. P2: rules v2 merged. P3: demo v2 (inline highlights + evidence lines). |
| 13:00–14:30 | **M2 — integrated** | P1: Apply-fix + Escalate/Stage buttons call `/execute-action`. P2: LLM enrich + `/brain/reload` + audit hardening. P3: scenarios final, backup screen-recording DONE. |
| 14:30–15:30 | **M3 — freeze** | Feature freeze. P3 leads pitch rehearsal x3; P1/P2 fix only demo-blockers. |
| 15:30–16:00 | Submit | Final PR merged. Submit. P3 submits text from `pitch/submission.md`. |

## Definition of done — M1 (the "it works" gate)

- [ ] `POST /verify-context` returns violations for all 4 scenarios (rules-only OK)
- [ ] Plugin OR demo renders at least one violation card live
- [ ] One action (`APPLY_REWRITE_AND_LOG`) writes to `audit_log.jsonl`

## Definition of done — M2 (the "wow" gate)

- [ ] All 4 demo scenarios pass end-to-end in the plugin (or demo.html fallback)
- [ ] CRITICAL invoice → Escalate + Stage-in-Round buttons work
- [ ] Evidence lines show `brain_key` receipts on every violation
- [ ] Backup video recorded (insurance against wifi failure)
- [ ] 90-sec pitch rehearsed twice

## Fallback ladder (if the plugin SDK fights us)

1. Full Lightfern plugin (target)
2. Plugin renders minimal banner + opens demo.html for details
3. demo.html only, framed as "the same check runs anywhere text leaves the company"
4. Backup screen recording (worst case — still submit)

Decide at **12:30 sharp**: if plugin can't render a card by then, escalate down the ladder and don't look back.
