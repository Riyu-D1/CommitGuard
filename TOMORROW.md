# TOMORROW — the only doc you need

**Phase rule: everyone pastes one phase prompt → PR → wait until ALL 3 PRs are merged → next phase. Never start early.**

## Who owns what (touch nothing else)

| Person | Files | Extra duty |
|---|---|---|
| **Riyansh** | `backend/main.py`, `backend/llm_enrich.py` | Merge-master: merges **Darsh → Pranali → Riyansh**. Registers Finance/Ops by 11:15. 12:30 fallback call. |
| **Darsh** | everything else in `backend/` (rules.py, actions.py, company_brain.json, scenarios.json, tests) | Smoke test green before every commit |
| **Pranali** | `demo/` + `plugin/` + `pitch/` (all frontend) | Backup video ~14:00 · submits before 16:00 |

## Setup — before 10:45

```bash
git clone https://github.com/Riyu-D1/CommitGuard
cd CommitGuard && ./start.sh
```

Open http://127.0.0.1:8000 → 4 scenario buttons work = ready.

## Every phase

1. Copy your Phase-N prompt from `team/<you>/PROMPTS.md` — the ENTIRE fenced block, it has all context the AI needs — paste it → run its VERIFY step
2. `git checkout -b <you>/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin <you>/phase<N> && gh pr create --fill`
3. Post "phase N up" → wait for all merges → next phase

## Clock

- **11:15** — Riyansh registers Finance/Ops track
- **12:30** — Riyansh decides: real plugin vs demo-only. Ladder: plugin+backend → **plugin with rules.js+brain inlined** (if fetch is sandboxed) → badge→demo → demo/index.html → video
- **~14:00** — Pranali records backup video
- **14:30** — rehearse pitch
- **15:30** — freeze: demo-blockers only
- **15:45** — airplane-mode test (demo must work offline)
- **<16:00** — Pranali submits

Stuck >10 min → paste the error in chat, tag Riyansh.
Details: `TEAM_PLAN.md` · API contract: `CONTRACT.md`
