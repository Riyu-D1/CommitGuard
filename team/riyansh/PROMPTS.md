# Riyansh — backend API + LLM · merge-master

**Your files:** `backend/main.py`, `backend/llm_enrich.py`
**Never touch:** other backend files (Darsh) · `demo/` `plugin/` `pitch/` (Pranali)

**Merge duty each phase:** merge PRs in order **Darsh → Pranali → yours**. Pull main, run `cd backend && uv run python smoke_test.py` before your own merge.

**Extra:** register Finance/Ops before 11:15 · 12:30 fallback call · 15:30 freeze.

## The loop

```
1. Paste the phase prompt → run its VERIFY step
2. git checkout -b riyansh/phase<N> && git add -A && git commit -m "phase <N>" && git push -u origin riyansh/phase<N> && gh pr create --fill
3. Post "phase N up" → merge all 3 PRs (Darsh, Pranali, you) → next phase
```

---

## Phase 1 — API hardening

```
In backend/main.py only. Additive — never change existing response shapes:
- CORS is already enabled — verify it's there, don't duplicate it.
- Validate POST /verify-context: non-empty text; context_type in {outgoing_email, slack_message, incoming_invoice, general} (match CONTRACT.md exactly) → else 422 {"error": "..."}.
- New POST /verify-batch: {items: [{text, context_type}]} → {"results": [...]} reusing existing logic.
VERIFY: cd backend && uv run python smoke_test.py → all pass. curl 127.0.0.1:8000/health + one POST /verify-batch.
```

## Phase 2 — LLM enrichment

```
Rewrite backend/llm_enrich.py:
- gpt-4o-mini, temperature 0, 4s timeout, strict JSON schema for an array of violations matching CONTRACT.md fields.
- OPENAI_API_KEY unset/timeout/any error → return [] silently. Never crash, never slow the endpoint.
- LLM violations may only ADD findings — dedupe against rule findings by brain_key.
VERIFY: smoke_test.py green with the key set AND unset.
```

## Phase 3 — E2E proof

```
Create E2E.md at repo root: a numbered runbook that proves the full flow — health, all 4 scenarios with expected violations, stage-invoice action, audit-log entries appearing. Run every command yourself, paste real outputs. Fix only YOUR files; flag other bugs in chat.
```

## Phase 4 — freeze duty

Run `smoke_test.py` + `bench.py` on main, merge last PRs. If the Lightfern SDK is usable, fill the `[SDK:]` slots in Pranali's conditional plugin prompt and hand it to her.
