# CommitGuard — Team Plan (Hackathon Day)
**Sat 24 Oct · Build 10:45→16:00 · Track: Finance/Ops (Round Treasury)**
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
| **Riyansh** — Plugin + Tech Lead | `plugin/` (all), `backend/llm_enrich.py`, merge-master | `backend/rules.py`, `actions.py`, `demo/` |
| **Darsh** — Backend rules, actions & brain | `backend/rules.py`, `backend/actions.py`, `backend/company_brain.json`, `backend/smoke_test.py`, `backend/bench.py` | `main.py`, `llm_enrich.py`, `demo/`, `plugin/`, `scenarios.json` |
| **Pranali** — Frontends + content | `demo/` (all), `pitch/` (all), `backend/scenarios.json` (data only) | `backend/*.py`, `plugin/` |

`backend/main.py` is **frozen/shared** — thin orchestration only, changes by PR with
a flag to the whole team. Shared docs (`CONTRACT.md`, `TEAM_PLAN.md`, `README.md`):
PR + flag in chat.

## Git workflow

- Branches: `riyansh/<thing>`, `darsh/<thing>`, `pranali/<thing>` — one feature per branch, small PRs.
- PR → `main`, **squash merge**, delete branch after.
- **Merge order at checkpoints: `darsh/*` → `pranali/*` → `riyansh/*`** (dependents merge last). Riyansh is merge-master.
- Merge `main` into your branch at every checkpoint — don't drift.
- Keep `main` runnable: `cd backend && uv run uvicorn main:app --port 8000` must always work on main.
- Rule for agents: "verify before you're done" is in every prompt — respect it.

## Shared stretch queue — grab when your list empties (claim in chat first!)

- [ ] `POST /verify-batch` endpoint (array of texts → array of results) — needs main.py flag
- [ ] Second client: `slack_message` context_type scenario + any rule tweaks
- [ ] `pitch/one-pager.html` judge handout (Pranali's Prompt F)
- [ ] Latency stat for pitch (Darsh's bench.py)
- [ ] Demo seed: pre-fill audit_log.jsonl with 5 realistic entries so Inspector isn't empty at demo time

## Timeline & merge checkpoints

| Time | Gate | Everyone |
|---|---|---|
| 09:30–10:45 | — | Venue, talks. Riyansh notes Lightfern plugin SDK shape from demo. All: skim your `team/<name>/README.md`. |
| 10:45–11:15 | **Register Finance/Ops track** (Riyansh) | Riyansh: plugin hello-world. Darsh: env up, `smoke_test.py` green. Pranali: demo runs at :8000 on venue wifi, starts submission blurb. |
| 11:15–13:00 | **M1 — working slice** | Riyansh: plugin calls `/verify-context` + renders 1 card. Darsh: rules v2 merged. Pranali: demo v2 (inline highlights) + scenario rewrites drafted. **12:30 = Riyansh's fallback call.** |
| 13:00–14:30 | **M2 — integrated** | Riyansh: buttons → `/execute-action` + LLM enrich. Darsh: action hardening + `/health`. Pranali: scenarios encoded, **backup video DONE**, pitch rehearsed. |
| 14:30–15:30 | **M3 — freeze** | Feature freeze. Pranali leads pitch rehearsal x3; others fix only demo-blockers. |
| 15:30–16:00 | Submit | Final PR merged. **Pranali submits** from `pitch/submission.md` — before 16:00, not at it. |

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
