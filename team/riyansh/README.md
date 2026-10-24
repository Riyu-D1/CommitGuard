# Riyansh — backend API + LLM · merge-master

**Your files:** `backend/main.py`, `backend/llm_enrich.py`
**Never touch:** other backend files (Darsh) · `demo/` `plugin/` `pitch/` (Pranali)

## The day

Paste phase prompts from `PROMPTS.md` in order (1 → 4). Between phases you merge
everyone's PRs: **Darsh → Pranali → yours**. Run
`cd backend && uv run python smoke_test.py` before your own merge — `main` must
always stay runnable.

## Lead duties

- **11:15** — register Finance/Ops track. Non-negotiable.
- **10:00 SDK demo** — note the real plugin API; if viable, fill the `[SDK:]`
  slots in Pranali's conditional plugin prompt and hand it to her.
- **12:30** — fallback call: no real plugin by then → demo-only, don't look back.
- **15:30** — freeze. Demo-blockers only.

## Stuck?

`smoke_test.py` is the safety net. Paste errors back to your agent; >10 min →
debug yourself or cut the feature.
