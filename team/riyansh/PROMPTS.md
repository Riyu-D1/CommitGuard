# Riyansh — agent prompts (backend API + LLM · merge-master)

**How to use (every phase):**
1. Fresh branch from latest main, every time (even if you are already on a branch, because squash-merged branches must not be reused):
   `git checkout main && git pull && git checkout -b riyansh/phase<N>`
2. Paste ONE phase's entire fenced block into Codex/Devin. When it says done, run the VERIFY commands yourself.
3. Ship: `git add -A && git commit -m "riyansh phase <N>" && git push -u origin HEAD && gh pr create --fill`
   (If Devin opened the PR itself, skip this step.)
4. As soon as YOUR PR is merged, start the next phase. **Do not wait for teammates.** Lanes never overlap, so there's nothing to wait for.

**Merge duty (rolling, not batched):** merge any teammate PR within ~5 min of "PR up". Before you merge:
`git fetch && git checkout <their-branch> && cd backend && uv run python smoke_test.py` must print `ALL PASS`
(after Darsh Phase 1 lands; before that, check the 4 baseline results by eye). Squash-merge, then post "merged".
If two PRs are waiting, merge Darsh first, then Pranali, then yours.

**If the AI claims done but a VERIFY fails, or stops mid-task, reply with exactly:**
`Continue — complete every remaining numbered item, then run all VERIFY commands again.`

**Your files:** `backend/main.py`, `backend/llm_enrich.py`, `E2E.md`, `CONTRACT.md` (you are the only one editing it today),
and `plugin/` **only if** you call GO on the real Lightfern plugin at 12:30 (see the bottom of `team/pranali/PROMPTS.md`).
**Clock:** register Finance/Ops by 11:15 · 12:30 plugin GO/NO-GO · 14:30 code complete · 15:00 freeze.

---

## Phase 1 — complete API surface ✅ DONE (PR #1 + PR #2 merged 11:03)

Nothing to paste. Validation, `/verify-batch`, `/audit-log?type=&result=` (falls back until Darsh Phase 2),
OpenAPI summaries, and `{"error": ...}` bodies are all on main and verified.

## Phase 2 — llm_enrich.py + advisories (target: merged by 12:15)

Start only after any local Phase-1 polish on `main.py` is merged or thrown away, because this phase edits `main.py` too.

```
You are a senior backend engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first).

backend/llm_enrich.py is the OPTIONAL second stage after the deterministic rules engine (backend/rules.py). It must NEVER crash or raise (no API key, openai package missing, no network, timeout, bad JSON → return None), must never remove or change a rule finding, and must never change the demo's verdicts. backend/main.py imports `from llm_enrich import llm_enrich, llm_enabled` and calls llm_enrich(text, context_type, violations, brain) inside _verify(); keep both signatures identical.

IMPORTANT FACT: the current file sends an OpenAI strict json_schema whose objects lack "additionalProperties": false / full "required" lists. OpenAI rejects such schemas with a 400, so today the LLM layer silently fails on every call. The schema below is strict-mode valid. Use it exactly.

YOUR FILES ONLY: backend/llm_enrich.py and backend/main.py. Do NOT modify any other file. No new dependencies.

TASK:

1. LAZY CLIENT in llm_enrich.py: module-level _client = None. A _get_client() helper: if _client is None and os.environ.get("OPENAI_API_KEY") is set, `from openai import OpenAI` INSIDE the helper and construct OpenAI() inside try/except (any exception → return None). `import llm_enrich` must work with the openai package missing.

2. llm_enabled() → True only when OPENAI_API_KEY is set AND _get_client() returns a client.

3. llm_enrich(text, context_type, violations, brain) → Optional[dict]. The whole body sits inside try/except Exception → return None.
   - No client → return None immediately.
   - messages: system = "You are CommitGuard's secondary review layer. Deterministic rules already found the listed violations — do NOT repeat them. Report ONLY additional, concrete risks backed by the company brain (implied commitments, promises not backed by the brain, missing approvals). If there are none, return an empty list. Also produce a polished full rewrite that resolves ALL findings (rule + yours) while keeping the sender's tone; return null for full_rewrite if there is nothing to fix." user = json.dumps(brain), json.dumps(violations), context_type, and the draft text, clearly labelled.
   - Call client.chat.completions.create(model="gpt-4o-mini", temperature=0, timeout=4, messages=..., response_format={"type": "json_schema", "json_schema": {"name": "commit_guard_enrich", "strict": True, "schema": SCHEMA}})
   - SCHEMA (strict-mode valid, use exactly):
     {"type":"object","additionalProperties":false,"required":["violations","full_rewrite"],"properties":{
       "violations":{"type":"array","items":{"type":"object","additionalProperties":false,
         "required":["category","severity","issue","correction","suggested_rewrite","evidence"],
         "properties":{
           "category":{"type":"string"},
           "severity":{"type":"string","enum":["LOW","MEDIUM"]},
           "issue":{"type":"string"},"correction":{"type":"string"},
           "suggested_rewrite":{"type":["string","null"]},
           "evidence":{"type":"object","additionalProperties":false,"required":["brain_key","expected","found"],
             "properties":{"brain_key":{"type":"string"},"expected":{"type":"string"},"found":{"type":"string"}}}}}},
       "full_rewrite":{"type":["string","null"]}}}
   - json.loads the content. DEDUPE: drop any returned item whose category OR evidence.brain_key already appears in the rule violations. Tag survivors v["source"] = "llm".
   - Return {"violations": <survivors>, "full_rewrite": <str or None>}.

4. main.py _verify() — LLM output is ADVISORY ONLY (additive per CONTRACT.md):
   - status, risk_level and "violations" are computed from the RULE violations only, exactly as today. LLM items never go into "violations".
   - Add a new top-level response field "advisories": the llm "violations" list, or [] when the LLM is off/failed. Always present.
   - Top-level "suggested_rewrite": if status is CLEAN → None (always). Otherwise llm full_rewrite if it is a non-empty string, else rules.apply_fixes(...) as today.
   - Remove the old loop that copied LLM suggested_rewrite into rule violations by category (dead after dedupe).
   - meta: keep engine/checks_run/latency_ms; set engine="rules+llm" only when llm_enrich returned a dict; add meta.rules_ms = time spent in rules.run_rules only (rounded to 2 dp), so the UI can show the sub-5ms stat even when the LLM is on.

CONSTRAINTS: additive only; /verify-batch returns the same object shape per item (it shares _verify); must run with OPENAI_API_KEY unset.

WORKING RULES — follow exactly:
- Read backend/llm_enrich.py and backend/main.py completely BEFORE editing.
- Work the numbered items IN ORDER and complete ALL of them.
- Never silently skip an item — if truly blocked, stop and output "STOPPED AT ITEM <n>: <reason>".
- DONE WHEN: every item is complete AND every VERIFY command produces the stated output. Partial completion is a failure.
- FREEDOM: response fields, schema, signatures and the advisory-only rule are exact. Helper structure is yours.

VERIFY — run from backend/ and paste output:
- env -u OPENAI_API_KEY uv run python -c "import llm_enrich; print(llm_enrich.llm_enabled())" → False, no error
- env -u OPENAI_API_KEY uv run python smoke_test.py → 4 baseline results unchanged (ALL PASS if Darsh's assertions have landed)
- env -u OPENAI_API_KEY uv run python -c "import main; r=main._verify('we can offer Net-60','outgoing_email'); print(r['status'], r['advisories'], r['meta']['engine'], 'rules_ms' in r['meta'])" → VIOLATION_DETECTED [] rules True
- env -u OPENAI_API_KEY uv run python -c "import main; r=main._verify('Net-30, billed monthly with 50% upfront','outgoing_email'); print(r['status'], r['suggested_rewrite'])" → CLEAN None
- OPTIONAL, only if a key is available: OPENAI_API_KEY=... uv run python -c "import llm_enrich,json;print(llm_enrich.llm_enrich('we can do net-90 and 40% off, and we will refund anything','outgoing_email',[],json.load(open('company_brain.json'))))" → a dict (NOT None). If it prints None, print the caught exception temporarily to debug the schema, then remove the print.
```

## Phase 3 — E2E proof + CONTRACT update (start after Darsh Phase 3 is merged, ~13:30; target merged by 14:15)

```
You are a senior engineer working in the CommitGuard repository (read AGENTS.md and CONTRACT.md first).

YOUR FILES ONLY: create E2E.md at repo root, and edit CONTRACT.md. Do NOT modify any other file.

TASK:

A. Before running anything, back up the demo data: `cp backend/audit_log.jsonl /tmp/audit.bak 2>/dev/null; cp backend/round_staging_queue.json /tmp/stage.bak 2>/dev/null`. Restart the server so it runs current main: `pkill -f "uvicorn main:app"; cd backend && (nohup uv run uvicorn main:app --port 8000 > /tmp/cg.log 2>&1 &) ; sleep 3` with OPENAI_API_KEY unset.

B. Write E2E.md, a numbered runbook a judge or teammate can follow to prove the whole system works. RUN every command and paste the REAL output under it (audit ids and timestamps will differ per run, so say so once at the top):
1. Setup: clone → cd backend && uv venv --python 3.12 && uv pip install -r requirements.txt → uv run uvicorn main:app --port 8000 (or ./start.sh from root)
2. curl -s 127.0.0.1:8000/health → {"ok":true,"engine":"rules",...}
3. For EACH key in backend/scenarios.json: the exact curl POST /verify-context (with that scenario's own context_type; build the JSON with python3 -c or jq so newlines are escaped) and the observed categories. The 4 baseline results must be: sales_email → FINANCIAL_POLICY + MARGIN_BREACH + TREASURY_LOCK · vendor_invoice → CRITICAL PAYMENT_REDIRECTION + 2× CONTRACT_OVERAGE · support_reply → 2× PROMISE_BREACH · clean_email → CLEAN. Include any extra scenarios (e.g. slack_urgent_fraud) as they actually behave.
4. One curl per new rule from Darsh's phases (DUPLICATE_INVOICE, SENDER_DOMAIN_MISMATCH, URGENT_PAYMENT_CHANGE, UNVERIFIED_CLAIM). Copy the inline test texts from backend/smoke_test.py. If a category does not fire, write "NOT IMPLEMENTED ON MAIN" instead of inventing output.
5. POST /execute-action: STAGE_INVOICE with payload {"invoice":"E2E-<unix seconds>","text":"..."} twice (second → duplicate rejected, if Darsh Phase 2 is merged), then show the round_staging_queue.json entry; ESCALATE_FRAUD (message names the CFO); APPROVE_OVERRIDE without reason → HTTP 400; with reason → success:true.
6. GET /audit-log?limit=3 → newest first; GET /audit-log?type=STAGE_INVOICE → only STAGE_INVOICE rows.
7. GET / → 200, GET /inspector.html → 200, GET /docs → 200.
8. `cd backend && uv run python smoke_test.py` → ALL PASS; `uv run python bench.py` → paste the table (this is the pitch's latency stat).
9. Offline note: every step above ran with OPENAI_API_KEY unset and no network.

C. CONTRACT.md (additive only): add the new categories that actually exist on main (DUPLICATE_INVOICE, SENDER_DOMAIN_MISMATCH, URGENT_PAYMENT_CHANGE, UNVERIFIED_CLAIM; check backend/rules.py and list only those present) to the category list; document the top-level "advisories" array (LLM-only notes, never affect status), meta.rules_ms, the optional per-violation "risk_score", the GET /audit-log ?type= and ?result= filters, the duplicate-action response {"success": false, "error": "duplicate", ...}, and that unknown action_type → 400 (only if actions.py does that on main).

D. Finally restore the demo data: `cp /tmp/audit.bak backend/audit_log.jsonl 2>/dev/null; cp /tmp/stage.bak backend/round_staging_queue.json 2>/dev/null` (both files are gitignored).

WORKING RULES — follow exactly:
- Cover ALL sections. Never fabricate an output; paste what each command ACTUALLY returned.
- DONE WHEN: E2E.md has real outputs for every section, CONTRACT.md is updated, demo data restored. Partial completion is a failure.
- FREEDOM: extra edge-case curls and timing output are welcome.

VERIFY: `cd backend && uv run python smoke_test.py` → ALL PASS; `git diff --stat` shows only E2E.md and CONTRACT.md.
```

## Phase 4 — freeze duty (not an agent task)

- **14:30 code complete.** On the DEMO laptop: `git checkout main && git pull`, restart `./start.sh`,
  `cd backend && uv run python smoke_test.py` (ALL PASS) and `uv run python bench.py`. Post the bench avg/p95 to Pranali.
- Reset demo data so the Inspector looks real and has no test junk:
  `cd backend && uv run python seed_audit.py --reset` (if Darsh Phase 4 didn't land: `rm -f audit_log.jsonl round_staging_queue.json && uv run python seed_audit.py`).
- Decide the demo LLM mode: **recommended: run the demo with `OPENAI_API_KEY` unset** (deterministic and instant). Only set the key if Phase 2's optional VERIFY returned a dict AND a full click-through of all 4 scenarios still shows the same verdicts.
- **15:00 FREEZE.** After this, demo-blockers only, and every merge needs a green smoke test first.
