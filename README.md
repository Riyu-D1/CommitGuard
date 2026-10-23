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

- Demo UI: http://localhost:8000
- Smoke test (offline): `cd backend && uv run python smoke_test.py`

## Repo map

| Path | Owner | What |
|---|---|---|
| `backend/` | Darsh (rules/actions) + Riyansh (`_llm_enrich`) | FastAPI + deterministic rules engine + company_brain.json |
| `plugin/` | Riyansh | Lightfern Mac app plugin (thin client) |
| `demo/` | Pranali | Standalone demo UI (served at `/`) |
| `pitch/` | Pranali | Script, Q&A, submission blurb, backup video |
| `team/` | all | Per-person phase plans + agent prompts (`team/riyansh`, `team/darsh`, `team/pranali`) |
| `CONTRACT.md` | shared | API contract — read before coding |
| `TEAM_PLAN.md` | shared | Timeline, merge checkpoints, fallbacks |
| `PLAYBOOK.md` | shared | Strategy, judges, narrative |
