# Riyansh — Plugin Lead + Tech Lead

Everyone codes via agents all day. Your workstream: `plugin/` + `backend/llm_enrich.py`
+ merge-master for all PRs. You also own the two authority calls: **12:30 fallback**
and **15:30 freeze**.

## Your files (nobody else touches them)

- `plugin/` — everything
- `backend/llm_enrich.py` — the optional OpenAI second stage
- `plugin/simulator.html` — your secret weapon (below)

## The simulator trick

Don't wait for the SDK. Prompt A builds a **fake draft surface** (`simulator.html`)
that mimics what the plugin will do — read text, verify, render cards, buttons.
By the time the real SDK is revealed (~10:45) your UI logic is DONE; you only port
it. That's the difference between finishing at 13:00 vs 15:30.

## Extra duties as lead

- **10:45–11:15:** register team on **Finance/Ops track**. Non-negotiable.
- **Merge-master:** checkpoint order `darsh/*` → `pranali/*` → `riyansh/*`. `main` must always run `uv run uvicorn main:app --port 8000` from `backend/`.
- **12:30:** if no violation card renders in the real plugin, declare fallback level and move on.
- **15:30:** freeze — you call it, you enforce it.

## Phases (stay on your agent constantly)

### Phase 0 — before 10:45
- [ ] `cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt && uv run uvicorn main:app --port 8000`
- [ ] `export OPENAI_API_KEY=...` → `curl localhost:8000/health` shows `rules+llm`
- [ ] Branch `riyansh/setup`; **Prompt A** (adapter + simulator) — start it during the talks if you can

### Phase 1 — 10:45→11:15
- [ ] Register track. Note from Lightfern demo: plugin manifest format, draft-text access, UI surface, lifecycle
- [ ] Fill `plugin/README.md` SDK notes section; hello-world plugin renders *anything* → PR `riyansh/setup` → M0 merge

### Phase 2 — 11:15→13:00 (M1)
- [ ] **Prompt B**: port simulator UI into the real plugin — verify → card render
- [ ] **12:30 fallback call** — say it, log it in TEAM_PLAN, move
- [ ] PR `riyansh/plugin-v1` → merge at M1

### Phase 3 — 13:00→14:30 (M2)
- [ ] **Prompt C**: buttons + CRITICAL lockout + audit feed in plugin
- [ ] **Prompt D**: LLM enrichment in `llm_enrich.py` (temperature 0, strict schema, tone-preserving rewrite)
- [ ] PRs `riyansh/actions` + `riyansh/llm` → merge at M2

### Phase 4 — 14:30→16:00 (M3)
- [ ] Demo-blockers only. Rehearse your 20s of pitch. Final merge.

### Stretch queue (if you finish early — pick from TEAM_PLAN shared list first)
- Second client: Slack-message context_type demo path in the plugin/simulator
- `plugin/` polish: severity animations, keyboard shortcut to apply fixes

## Fallback ladder (your call at 12:30)
1. Full plugin card UI ← target
2. Badge "⚠ N violations" + "Open details" → localhost:8000
3. demo/index.html standalone
4. Pranali's backup video
