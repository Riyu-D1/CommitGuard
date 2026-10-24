# CommitGuard

CommitGuard watches your team's Slack and stops messages that break company
policy, citing the company brain, and learns new rules when a human
corrects it.

Built for the Lightfern Company Brain Buildathon — Finance/Ops track.

## How it works

```mermaid
flowchart LR
    slack[Slack channel] --> poll[CommitGuard poller]
    poll --> engine[Deterministic rules engine]
    brain[(company brain<br/>company_brain.json)] --> engine
    poll -->|"? / ask: / @bot"| ask[Ask-the-brain]
    brain --> ask
    engine -->|violations + cited evidence| reply[Threaded Block Kit reply]
    ask -->|sourced answer| reply
    engine --> dash[Dashboard · /feed · audit log]
    ask --> dash
    reply -->|human override: "you missed this"| learn[/learn]
    learn -->|learned_rules, enforced immediately| brain
```

## Quickstart

```bash
cp backend/.env.example backend/.env   # Slack tokens optional — no .env = simulated mode
scripts/run_demo.sh                    # API + dashboard on 127.0.0.1:8000
open http://127.0.0.1:8000             # the dashboard
```

Works fully offline with every token unset. Use `127.0.0.1`, not
`localhost` — some Macs resolve `localhost` to IPv6 where uvicorn doesn't
listen.

## Judging criteria → where it lives

| Criterion | What we built | Where |
|---|---|---|
| **Onboarding test** | A new hire asks `? can I give a 20% discount?` in Slack (or `POST /ask`) and gets a plain-English answer that cites the exact brain keys it came from | `POST /ask`, `GET /brain/policies`, Slack question replies in `slack_feed.py` |
| **Structured + unstructured** | Free-text messages checked against the structured brain — contracts, pricing floors, approval limits, trusted sender domains — every violation cites `brain_key`, expected vs found | `rules.py`, `company_brain.json` |
| **Brain and hands** | The brain decides; the hands act: every verify result carries an `actions` plan (`HOLD_PAYMENT`, `ESCALATE`, `REQUEST_APPROVAL`, … with brain-sourced targets), `STAGE_INVOICE` queues payments for Round Treasury, `ESCALATE_FRAUD`, `APPLY_REWRITE_AND_LOG`, and every check lands in an append-only audit trail. AuditTrace parses invoices and reconciles every field against the signed contract — rate/amount overage, IBAN/sort-code/account mismatches (BEC signature), hidden uplift clauses, re-billed invoices, terms drift | `actions.py` `plan_actions`, `POST /execute-action`, `actions` on `/verify-context` + `/feed`, `audit_trace.py` |
| **Learns and updates itself** | "You missed this" on any feed item teaches a `learned_rules` entry; "that's fine" teaches a `learned_exceptions` entry — both enforced by the deterministic engine from the next request. TribalSync goes further: an authoritative decision in the feed ("CFO: from today, terms are Net-45") becomes a pending brain-patch proposal with evidence and predicted impact — a human applies or rejects it (Slack thread `apply`/`reject` or HTTP), and every mutation lands in the brain changelog | `POST /learn`, `POST /feed/{id}/override`, `GET /brain/learned`, `tribal_sync.py`, `brain_store.py`, `GET /brain/proposals`, `GET /brain/changelog` |

Detection is deterministic — regex + dictionary checks against the brain in
under 5ms, fully offline (see `backend/bench.py`). An optional OpenAI layer
polishes wording only; it can never flip a verdict.

## Verify it yourself

```bash
cd backend && uv run python smoke_test.py    # prints ALL PASS
curl -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "who approves a £7,000 spend?"}'
```

## Repo map

| Path | Owner | What |
|---|---|---|
| `backend/rules.py` `actions.py` `company_brain.json` `scenarios.json` `smoke_test.py` `bench.py` `seed_audit.py` `onboarding.py` | Darsh | Deterministic engine + action handlers + brain data + tests |
| `backend/main.py` `llm_enrich.py` `slack_feed.py` `brain_store.py` `tribal_sync.py` `audit_trace.py` `scripts/` | Riyansh | FastAPI orchestration, optional OpenAI stage (fail-open), Slack feed + questions, atomic brain writer (single-writer + changelog + on-change hooks), TribalSync decision→patch proposals, AuditTrace invoice reconciliation, demo scripts |
| `demo/` `plugin/` `pitch/` | Pranali | All frontend: demo UI, Inspector, simulator/plugin, pitch assets |
| `team/` | all | Per-person phase plans + agent prompts (`team/riyansh`, `team/darsh`, `team/pranali`) |
| `TOMORROW.md` | shared | **Day-of runbook — the only doc you need open** |
| `CONTRACT.md` | shared | API contract — read before coding |
| `E2E.md` | shared | Live-Slack demo runbook |
| `TEAM_PLAN.md` | shared | Timeline, merge checkpoints, stretch queue |
| `PLAYBOOK.md` | shared | Strategy, judges, narrative |
