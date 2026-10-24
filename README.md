# CommitGuard

**The pre-send firewall for the company brain.** Nothing leaves the company that the
brain can't back up.

Built for the Lightfern Company Brain Buildathon — Finance/Ops track.

## Quickstart

```bash
cd backend
uv venv --python 3.12 && uv pip install -r requirements.txt
export OPENAI_API_KEY=...        # optional — works fully without it
uv run uvicorn main:app --port 8000
```

- Demo UI: http://127.0.0.1:8000 (use 127.0.0.1 — some Macs resolve `localhost` to IPv6 where uvicorn doesn't listen)
- Smoke test (offline): `cd backend && uv run python smoke_test.py`
- Or one command: `./start.sh`

## Repo map

| Path | Owner | What |
|---|---|---|
| `backend/rules.py` `actions.py` `company_brain.json` `scenarios.json` `smoke_test.py` `bench.py` `seed_audit.py` | Darsh | Deterministic engine + action handlers + brain data + tests |
| `backend/main.py` `llm_enrich.py` | Riyansh | FastAPI orchestration + optional OpenAI stage (fail-open) |
| `demo/` `plugin/` `pitch/` | Pranali | All frontend: demo UI, Inspector, simulator/plugin, pitch assets |
| `team/` | all | Per-person phase plans + agent prompts (`team/riyansh`, `team/darsh`, `team/pranali`) |
| `TOMORROW.md` | shared | **Day-of runbook — the only doc you need open** |
| `CONTRACT.md` | shared | API contract — read before coding |
| `TEAM_PLAN.md` | shared | Timeline, merge checkpoints, stretch queue |
| `PLAYBOOK.md` | shared | Strategy, judges, narrative |
