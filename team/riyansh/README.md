# Riyansh — Plugin Lead + Tech Lead

Everyone codes via agents all day. Your workstream: `plugin/` (all) +
`backend/llm_enrich.py` + merge-master. **Your build lives in `PROMPTS.md` —
execute it top-to-bottom; the phases map to the day's schedule.**

## Your files (nobody else touches them)

- `plugin/` — adapter, simulator, real SDK port, SDK notes, E2E script
- `backend/llm_enrich.py` — optional OpenAI second stage

## Phase map

| Phase | Time | Prompts | Done when |
|---|---|---|---|
| 1 — Foundation | 10:45–11:15 | A (adapter.js) → B (simulator.html) | Full plugin UX verified against simulated host — before SDK is even understood |
| 2 — Real SDK | 11:15–13:00 | C (skeleton, fill `[SDK]` slots) → D (full cards in host) | Violation card renders in the real runtime → **M1** |
| 3 — LLM + hardening | 13:00–14:30 | E (llm_enrich.py) → F (E2E script) | rules+llm verified with/without key → **M2** |
| 4 — Conditional | — | G (badge fallback, only if called) · H (stretch) | — |

## Lead duties (parallel to your prompts)

- **10:45–11:15:** register team on **Finance/Ops track**. Non-negotiable.
- **Merge-master:** at each checkpoint merge `darsh/*` → `pranali/*` → `riyansh/*`.
  `main` must always run `cd backend && uv run uvicorn main:app --port 8000`.
- **12:30 fallback call:** no card in the real runtime by then → Prompt G + declare
  the level below. Say it out loud, move on.
- **15:30 freeze:** you call it, you enforce it.

## Fallback ladder
1. Full plugin card UI ← target
2. Badge "⚠ N violations" + "Open details" → localhost:8000 (Prompt G)
3. demo/index.html standalone
4. Pranali's backup video

## Golden rules
- Every prompt ends with VERIFY — do it, don't skip.
- `main` stays runnable after every merge.
- `simulator.html` is ALSO a demo asset — if the plugin path dies, it demos the
  exact same UX. Keep it working.
