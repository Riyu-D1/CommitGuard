# Riyansh — Plugin Lead + Technical Lead

Head of project. You own `plugin/`, the LLM enrichment path in `backend/main.py`
(`_llm_enrich` only — Darsh owns everything else in backend), merge-master duties,
and all final technical calls (fallback decisions, freeze time).

## Your extra duties as lead

- **10:45–11:15:** register the team on the **Finance/Ops track** before the deadline. Non-negotiable.
- **Merge-master:** at each checkpoint you merge PRs in order: `darsh/*` (backend) → `pranali/*` (demo/scenarios) → `riyansh/*` (plugin). `main` must always run: `cd backend && uv run uvicorn main:app --port 8000`.
- **12:30 fallback call:** if the plugin can't render a violation card by 12:30, declare the fallback level (bottom of this file) and move on — don't negotiate with the SDK.
- **15:30 freeze:** you call it, you enforce it.

## Interface you build against

Backend `http://localhost:8000`, contract in `CONTRACT.md`. Flow: capture draft text →
`POST /verify-context` (debounced ~700ms) → render cards → buttons → `POST /execute-action`.
Card: severity color, category, issue, evidence line (`brain_key` = expected · found), correction.
Buttons: Apply fixes / Send anyway (needs reason) / Escalate to CFO (CRITICAL only) / Stage in Round.
CRITICAL severity → hide Send + Send-anyway.

## Phases

### Phase 0 — before 10:45
- [ ] `cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt && uv run uvicorn main:app --port 8000` → curl `/verify-context` once
- [ ] `export OPENAI_API_KEY=...` — confirm `meta.engine` reports `rules+llm` on a verify call
- [ ] Branch `riyansh/setup`; fill `plugin/README.md` SDK notes during the 10:00 Lightfern demo
- [ ] **Prompt A** (PROMPTS.md): build `plugin/` adapter scaffold

### Phase 1 — 10:45→11:15
- [ ] Register track. Watch Lightfern demo for: how plugins load, UI surface (panel/inline/toolbar), how to read draft text, lifecycle events
- [ ] Ask their team early: "how do I read the current draft text and render a custom panel?"
- [ ] Hello-world plugin renders *anything* → PR `riyansh/setup` → **M0 merge**

### Phase 2 — 11:15→13:00 (M1 gate)
- [ ] **Prompt B**: plugin calls `/verify-context` on draft change, renders 1 violation card
- [ ] PR `riyansh/verify-render` → merge at M1
- [ ] **12:30:** fallback decision — say it out loud, move on

### Phase 3 — 13:00→14:30 (M2 gate)
- [ ] **Prompt C**: all 4 buttons wired, CRITICAL lockout, audit feed
- [ ] **Prompt D**: LLM enrichment pass in `_llm_enrich` (your AI-lead task — temperature 0, strict schema, tone-preserving rewrite)
- [ ] PRs `riyansh/actions` + `riyansh/llm` → merge at M2

### Phase 4 — 14:30→16:00 (M3 freeze)
- [ ] Demo-blocker fixes only. Rehearse your 20s segment (the plugin live part).
- [ ] Final PR merged. Confirm smoke test green on clean `main`.

## Fallback ladder (you own this call)

1. Full plugin card UI ← target
2. Plugin badge "⚠ N violations" + button opening `localhost:8000`
3. demo/index.html standalone — "the same check runs anywhere text leaves the company"
4. Pranali's backup video
