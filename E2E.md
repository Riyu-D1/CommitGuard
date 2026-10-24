# E2E Demo Runbook — CommitGuard live in Slack

Goal: type a message in a real Slack channel → CommitGuard checks it against
the company brain within ~3s → a threaded Block Kit warning appears under
flagged messages, a ✅ reaction on clean ones. Everything also lands in the
demo UI feed, `/feed`, and the audit log.

## 1. Create the Slack app (one time, ~5 min)

1. <https://api.slack.com/apps> → **Create New App** → **From scratch** →
   name `CommitGuard`, pick the demo workspace.
2. **OAuth & Permissions** → **Bot Token Scopes** → add:
   - `channels:history` — read new channel messages
   - `channels:read` — resolve the channel
   - `chat:write` — post the threaded warning
   - `reactions:write` — ✅ on clean messages (optional — without it the bot
     skips reactions silently)
3. **Install to Workspace** → allow → copy the **Bot User OAuth Token**
   (`xoxb-…`).
4. In Slack, open (or create) the demo channel → type `/invite @CommitGuard`.
5. Channel ID: click the channel name → **About** → **Channel ID** at the
   bottom (`C…`).

## 2. Configure

```bash
cp backend/.env.example backend/.env
```

Fill in:

```dotenv
SLACK_BOT_TOKEN=xoxb-…
SLACK_CHANNEL_ID=C…
SLACK_REPLY=1
```

`backend/.env` is gitignored and loaded by the app itself (tiny stdlib
parser — real env vars win). `SLACK_REPLY` other than `1` = monitor-only:
messages still flow into the feed and audit log, the bot never posts or
reacts.

## 3. Run

```bash
scripts/run_demo.sh          # or: cd backend && uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Watch for the startup lines:

```text
commitguard feed: mode=slack channel=C… token=set reply=on
slack auth.test ok: user=commitguard team=…
```

Sanity check:

```bash
curl http://127.0.0.1:8000/slack/status
# → {"mode":"slack","channel":"C…","token":"set","reply_enabled":true, …}
```

Open the dashboard at <http://127.0.0.1:8000/> (inspector console at
`/inspector.html`).

## 4. Demo messages — type these in the channel

Text for each is in `backend/scenarios.json` (also shown by `GET /scenarios`).

| You paste into Slack | What appears in Slack | In the app |
| --- | --- | --- |
| `vendor_invoice` text | 🛑 thread: "CommitGuard caught 1 issue" — CRITICAL `PAYMENT_REDIRECTION` | feed item + `FEED_CHECK` audit row |
| `sales_email` text | ⚠️ thread: "caught 3 issues" — `FINANCIAL_POLICY`, `MARGIN_BREACH`, `TREASURY_LOCK` | same |
| `support_reply` text | ⚠️ thread: "caught 2 issues" — 2× `PROMISE_BREACH` | same |
| `clean_email` text | ✅ reaction only — **no thread reply**, channel stays clean | same |
| *(bonus)* `slack_urgent_fraud` text | 🛑 thread: "caught 2 issues" — `PAYMENT_REDIRECTION` + `URGENT_PAYMENT_CHANGE` | same |
| `? can I give a 20% discount?` | 💡 thread: the answer + `Source: <brain_key> = <value>` per citation | feed item `kind: "question"` + `FEED_ASK` audit row |
| reply `missed: <phrase>` in a warning thread | 📚 "Learned: …" — the phrase is a rule now | `learned_rules` entry + `FEED_OVERRIDE` row |
| reply `fine` in a warning thread | 📚 "Learned: …" — a `learned_exceptions` entry suppresses that category for the phrase | same |
| `CFO: from today payment terms are Net-45` | 📋 thread: pending brain-patch proposal card — reply `apply` or `reject` in the thread | feed item carries `proposal`/`proposal_id` (`GET /brain/proposals`); `apply` flips the earlier flagged Net-45 draft's verdict to clean |

Questions — `?…`, `ask:…`, or any `@CommitGuard` mention — are answered from
the brain, never run through the rules engine, and count under `questions`
in `/feed/stats`. Same path as `POST /ask`.

Thread commands — `missed: <phrase>` teaches a rule, `fine` marks the item a
false positive (learned exception). Both run the same logic as
`POST /feed/{id}/override` and get a `📚 Learned: …` reply. Threads the bot
has posted in are polled via `conversations.replies` for 30 min after
posting, at most once every 5s, honoring `Retry-After`.

Each thread reply is one Block Kit message: a header, then per violation a
section with the issue, a context line citing the brain
(`Brain says: <expected> · Found: <found>`), a `> fix` quote, and a closing
`🤖 Actions: <label> · <label>` context line — the next steps the engine
plans, with targets from the brain (e.g. `Hold payment — do not pay ·
Escalate to Amara Osei`). A rule-clean message that still carries LLM
advisories gets a softer `💡 Worth a check` reply instead — advisories are
advisory only, never framed as violations; the ✅ reaction is only for
truly clean messages (no advisories).

Brain proposals — a feed message that reads as an authoritative decision
(`CFO: from today payment terms are Net-45`) creates a pending brain-patch
proposal — never auto-applied — posted into the message's thread as a Block
Kit card. Reply `apply`/`reject` in the thread (same loop guards as
`missed:`/`fine`) or call `POST /brain/proposals/{id}/apply|reject`; browse
them via `GET /brain/proposals?status=pending`. Applying writes the patch
through `brain_store` (atomic, logged in `GET /brain/changelog`), reloads
the brain, and re-verifies the affected feed items — so the earlier Net-45
draft that was flagged against the Net-30 rule visibly flips to clean.

Invoice audit — `incoming_invoice` texts and invoice-ish Slack messages
(vendor, invoice no, or IBAN + amount present) also run
`backend/audit_trace.py` on top of the rules engine, which can add
`INVOICE_OVER_CONTRACT` (HIGH — fires on any overage; evidence carries
`delta_gbp`), `BANK_DETAILS_MISMATCH` (CRITICAL), `HIDDEN_CLAUSE` (HIGH),
`DUPLICATE_INVOICE` (CRITICAL), and `TERMS_MISMATCH` (MEDIUM) violations,
deduped per category/`brain_key` so baseline verdicts never double-count.
Push an invoice through the feed with `POST /feed/inject` plus
`"context_type": "incoming_invoice"`; follow-up execute-action types
`HOLD_PAYMENT`, `VERIFY_VENDOR`, `REQUEST_CREDIT_NOTE`, `REQUEST_APPROVAL`
handle the response.

## 5. Simulated fallback (no Slack app needed)

If `SLACK_BOT_TOKEN` or `SLACK_CHANNEL_ID` is missing the backend logs
`commitguard feed: mode=simulated (…)` and cycles `backend/scenarios.json`
every 8s through the same verify pipeline — the feed UI, `/feed`,
`/feed/stats`, and audit trail still demo end-to-end. `/slack/status` shows
`"token": "missing"`. Nothing is posted to Slack.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Nothing appears in Slack | `/invite @CommitGuard` in the channel; `SLACK_REPLY=1`; check `last_error` in `/slack/status` |
| `invalid_auth` in `last_error` | token regenerated or wrong workspace — reinstall app, update `.env` |
| `channel_not_found` / `not_in_channel` | wrong `C…` id, or bot not invited |
| clean messages get no ✅ | app lacks `reactions:write` — add the scope and reinstall (skipped silently otherwise) |
| `CERTIFICATE_VERIFY_FAILED` | `uv pip install certifi`, or export `SSL_CERT_FILE` to a CA bundle |
| bursts get dropped | the client honors Slack's `Retry-After`; bursts may just appear a few seconds late |
