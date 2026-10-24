# Riyansh — backend API + LLM · merge-master

**Your files:** `backend/main.py`, `backend/llm_enrich.py`, `E2E.md`, `CONTRACT.md`, and `plugin/` only if you call GO at 12:30.
**Never touch:** other backend files (Darsh) · `demo/` `pitch/` (Pranali)

## The day (rolling phases, no all-3 barrier)

Phase 1 ✅ merged (PR #1, #2). Remaining: **Phase 2** (llm_enrich + advisories, target merged by 12:15) →
**Phase 3** (E2E.md + CONTRACT update, after Darsh Phase 3 merges, target 14:15) → **Phase 4** freeze duty.
Always start a phase with `git checkout main && git pull && git checkout -b riyansh/phase<N>`.

## Merge duty

Merge each teammate PR within ~5 min of "PR up". Before merging: check out their branch and run
`cd backend && uv run python smoke_test.py`, which must print `ALL PASS` once Darsh Phase 1 is in.
Two waiting? Darsh → Pranali → yours. `main` must always run.

## Lead duties

- **11:15** register Finance/Ops track. Non-negotiable.
- **12:30** plugin GO/NO-GO. GO → you run the conditional plugin prompt (bottom of `team/pranali/PROMPTS.md`) after your Phase 2. NO-GO → demo-only, don't look back.
- **14:30** code complete: on the demo laptop pull main, restart, smoke + bench, `uv run python seed_audit.py --reset`, tell Pranali "ready to record".
- **15:00** freeze. Demo-blockers only.

## Stuck?

`smoke_test.py` is the safety net. Paste errors back to your agent; >10 min → debug yourself or cut the feature.
