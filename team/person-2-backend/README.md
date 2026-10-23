# Person 2 — Backend Lead (rules engine + brain + actions)

**Mission:** make the brain smarter and the enforcement bulletproof. You own `backend/*.py` and `backend/company_brain.json`. `scenarios.json` data is Person 3's — coordinate before touching it.

**North star: the LLM is the fallback, not the firewall.** Every check that can be deterministic must be. `meta.engine: "rules"` should demo perfectly with no API key.

## Phases

### Phase 0 — before 10:45
- [ ] `cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt`
- [ ] `uv run uvicorn main:app --port 8000` → verify all 4 `/scenarios` pass via `smoke_test.py`
- [ ] Branch `p2/setup`

### Phase 1 — 10:45→11:15
- [ ] Skim `CONTRACT.md` — you are its guardian; flag any breaking change anyone proposes
- [ ] Quick wins list (below) — pick order, don't start yet if talks need attention

### Phase 2 — 11:15→13:00 (M1 gate)
- [ ] **Rules v2** — pick 3–4 highest-demo-value additions:
  - [ ] Duplicate invoice detection (same invoice # + vendor seen twice → CRITICAL; keep a `seen_invoices.json` store, POST `/execute-action` STAGE_INVOICE records it)
  - [ ] Sender-domain vs contract check (invoice text with an email whose domain ≠ vendor domain → HIGH)
  - [ ] "Urgency + bank change" combo escalates severity (fraud pattern)
  - [ ] Promise detection beyond feature claims: "we will <verb> by <date>" in text → needs brain support or flag as UNVERIFIED_PROMISE (MEDIUM)
  - [ ] Multi-currency amounts (`$`, `€` already partially handled — normalize)
- [ ] Keep every violation carrying `evidence {brain_key, expected, found}` — that's the demo magic
- [ ] Extend `smoke_test.py` to cover new checks; keep total rule latency <50ms
- [ ] PR `p2/rules-v2` → merge at M1

### Phase 3 — 13:00→14:30 (M2 gate)
- [ ] LLM enrich pass: tighten prompt (temperature 0, 8s timeout, fail-open already handled); ensure `suggested_rewrite` per-violation gets filled from LLM when available
- [ ] `POST /brain/reload` already exists — test the live-brain demo trick (edit JSON → reload → new rule fires)
- [ ] `/execute-action` hardening: dedupe staged invoices; `APPROVE_OVERRIDE` requires reason (done); `ESCALATE_FRAUD` message uses CFO name from brain (done — verify)
- [ ] Optional stretch: `GET /health` returning `{ok, engine, checks}` for demo confidence
- [ ] PR `p2/llm-actions` → merge at M2

### Phase 4 — 14:30→16:00 (M3 freeze)
- [ ] Freeze. Fix only demo-blockers. Backup: confirm `smoke_test.py` green on a clean checkout.

## Guardrails

- Never let a code path crash on malformed input — fail-open to rules-only.
- No new dependencies without asking the team (uv add, pin versions).
- If you add a response field, append `CONTRACT.md` in the same PR.
