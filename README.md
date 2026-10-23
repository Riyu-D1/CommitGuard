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
| `backend/rules.py` `actions.py` `company_brain.json` `smoke_test.py` | Darsh | Deterministic engine + action handlers + brain data |
| `backend/llm_enrich.py` | Riyansh | Optional OpenAI structured-output stage (fail-open) |
| `backend/main.py` | frozen/shared | Thin FastAPI orchestration — PR + flag to change |
| `plugin/` | Riyansh | Lightfern plugin + simulator (thin clients) |
| `demo/` | Pranali | Demo UI (`/`)+ Inspector compliance console (`/inspector.html`) |
| `pitch/` | Pranali | Script, submission, rehearsal sheet, backup video |
| `team/` | all | Per-person phase plans + agent prompts (`team/riyansh`, `team/darsh`, `team/pranali`) |
| `CONTRACT.md` | shared | API contract — read before coding |
| `TEAM_PLAN.md` | shared | Timeline, merge checkpoints, stretch queue |
| `PLAYBOOK.md` | shared | Strategy, judges, narrative |
