# API Contract — DO NOT BREAK without flagging the team

This file is the stability boundary between Riyansh (main.py + llm_enrich.py),
Darsh (rules.py + actions.py + brain + scenarios), and Pranali (all frontend).
You may ADD fields; you may NOT rename or remove fields without a PR comment
that everyone acknowledges.

Backend base URL: `http://127.0.0.1:8000` (local, no auth, CORS open).
NOTE: use `127.0.0.1`, not `localhost` — on some Macs `localhost` resolves to
IPv6 `::1` where uvicorn doesn't listen; this bit us in testing.

---

## POST /verify-context

**Request**
```json
{
  "text": "string — the draft message or invoice text",
  "context_type": "outgoing_email | slack_message | incoming_invoice",
  "recipient": "optional string"
}
```

**Response**
```json
{
  "status": "CLEAN | VIOLATION_DETECTED",
  "risk_level": "LOW | MEDIUM | HIGH",
  "violations": [
    {
      "category": "FINANCIAL_POLICY | MARGIN_BREACH | TREASURY_LOCK | PAYMENT_REDIRECTION | CONTRACT_OVERAGE | APPROVAL_REQUIRED | PROMISE_BREACH | DUPLICATE_INVOICE | SENDER_DOMAIN_MISMATCH | URGENT_PAYMENT_CHANGE | UNVERIFIED_CLAIM | LEARNED_RULE (or any custom category passed to /learn)",
      "severity": "LOW | MEDIUM | HIGH | CRITICAL",
      "issue": "human-readable problem",
      "correction": "human-readable fix guidance",
      "suggested_rewrite": "string | null",
      "evidence": { "brain_key": "financial_rules.max_payment_terms", "expected": "Net-30", "found": "Net-60" },
      "span": { "text": "Net-60", "start": 13, "end": 19 }
    }
  ],
  "suggested_rewrite": "full-text rewrite | null",
  "actions": [
    { "type": "HOLD_PAYMENT | ESCALATE | REQUEST_APPROVAL | BLOCK_AND_REDACT | SUGGEST_REWRITE",
      "label": "human-readable next step (targets come from the brain, e.g. 'Escalate to Darsh')",
      "target": "person/channel from the brain | null",
      "payload": { "...": "context for executing the action" } }
  ],
  "meta": { "engine": "rules | rules+llm", "checks_run": 8, "latency_ms": 3.2 }
}
```

Client rules:
- `severity: CRITICAL` → block Send, offer Escalate only.
- `span` is optional per violation; when present, clients SHOULD underline it inline.
- `suggested_rewrite` (top level) is the one-click "Apply all fixes" text.
- `actions` is the engine's suggested next steps (from `actions.plan_actions`)
  — [] for clean items; deduped by type; pure suggestion, nothing executed.

## POST /execute-action

**Request**
```json
{ "action_type": "SEND_APPROVED | APPLY_REWRITE_AND_LOG | APPROVE_OVERRIDE | STAGE_INVOICE | ESCALATE_FRAUD",
  "payload": { "text": "...", "reason": "required for APPROVE_OVERRIDE", "...": "anything else" } }
```

**Response** `{ "success": true, "audit_log_id": "log_xxxx", "message": "..." }`

- `APPROVE_OVERRIDE` without `payload.reason` → HTTP 400.
- `STAGE_INVOICE` appends to `backend/round_staging_queue.json`.
- Every action appends to `backend/audit_log.jsonl`.

## GET /brain → the company_brain.json object
## GET /brain/policies → policy cards generated from the brain (dashboard brain panel)

**Response** — array of cards:
```json
[{ "title": "Discount cap",
   "rule": "Discounts above 10% need approval in #finance-approvals.",
   "brain_key": "financial_rules.max_unapproved_discount_percent",
   "example_violation": "Promising a 15% discount without sign-off." }]
```

## POST /ask — ask the brain a question (the onboarding test)

**Request**
```json
{ "question": "string, 3-300 chars after trimming" }
```

**Response**
```json
{ "answer": "plain-English answer grounded in the brain",
  "sources": [{ "brain_key": "financial_rules.max_unapproved_discount_percent",
                "value": 10 }],
  "matched": true,
  "meta": { "engine": "rules | rules+llm", "latency_ms": 1.2 } }
```

- `matched: false` → `answer` says it's not in the company brain yet and
  `sources` is empty — a human can teach it via `POST /learn`.
- `422 {"error": ...}` when question is missing, or under 3 / over 300 chars.
- With `OPENAI_API_KEY` set the `answer` wording may be LLM-polished
  (`meta.engine: "rules+llm"`); `sources` and `matched` always come from the
  deterministic brain lookup and are never touched by the LLM.

## POST /brain/reload → re-read company_brain.json from disk (live-brain demo trick; 422 keeps old brain)

## Learning ("you missed this" → new rule)

The brain grows a `learned_rules` list:
`{ id, phrase, category, severity, issue, correction, created_ts, source_feed_id }`.
Every learned rule is enforced immediately by the deterministic engine: the
phrase is matched case-insensitively (word-boundary) in every context_type and
produces a violation whose `category` is the rule's category (`LEARNED_RULE` by
default) with `evidence.brain_key = "learned_rules[<id>]"`.

### POST /learn

**Request**
```json
{
  "phrase": "required, 3-120 chars — the text signature to catch",
  "category": "LEARNED_RULE (default) — may be any existing category",
  "severity": "HIGH (default) | CRITICAL | MEDIUM",
  "issue": "optional — defaults to a human-reviewer message",
  "correction": "optional — defaults to remove/rephrase guidance",
  "source_feed_id": "optional int — feed item this rule came from"
}
```

**Response** — `201` with the stored rule (id + created_ts filled in). Deduped
on lower-cased phrase: re-learning the same phrase returns the existing rule.
`422 {error}` on bad input. The in-memory brain reloads before the response, so
the very next /verify-context call enforces the rule.

### GET /brain/learned → `{ "rules": [...], "exceptions": [...] }`, each newest first

`rules` is `brain.learned_rules` (taught via /learn or override `missed`);
`exceptions` is `brain.learned_exceptions` (override `false_positive`).

### GET /brain/learned/rules → plain learned-rules array, newest first

The pre-`{rules, exceptions}` shape — for clients built against the old
`/brain/learned` list response.

## GET /audit-log?limit=N → newest-first array of audit entries
## GET /scenarios → { key: { label, context_type, text } } from backend/scenarios.json
## GET /health → { ok, engine: "rules"|"rules+llm", checks, brain_keys, feed: { mode: "slack"|"simulated", channel, last_poll_ts, error? } }
## GET / → demo/index.html · GET /inspector.html → demo/inspector.html

## Live feed (Slack monitor; see backend/slack_feed.py)

A background thread checks every new message in a Slack channel when
`SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` are set (polls conversations.history
every 3s; `SLACK_REPLY=1` also posts one threaded Block Kit warning per
flagged message — ending in a `🤖 Actions: <label> · <label>` context line
from the actions plan — a softer `💡 Worth a check` thread reply per
rule-clean message that still has LLM advisories, and a ✅ reaction only
when a message is truly clean (no advisories); default OFF). With either
unset it runs **simulated mode** — cycling backend/scenarios.json every 8s —
so the demo works offline. Every item also appends to
`backend/feed_log.jsonl` (gitignored) and writes a `FEED_CHECK`
row to the audit trail. The token is never returned or logged.

**Questions are not checked.** A message starting with `?` or `ask:`
(case-insensitive), or mentioning the bot user (`<@BOT_ID>`), is treated as
a question: it's answered via the same logic as `POST /ask` (deterministic
brain lookup, optional LLM rewording), logged as a feed item with
`kind: "question"`, audited as `FEED_ASK`, and — when `SLACK_REPLY=1` —
answered in the thread with Block Kit: the answer, plus one
`Source: <brain_key> = <value>` context line per cited source. Unmatched
questions say the brain doesn't cover it yet. Everything else gets
`kind: "check"` and the normal verify pipeline.

Env vars may be set in the real environment or in `backend/.env`
(gitignored; stdlib parser, real env wins — see `backend/.env.example`).
Slack writes honor the API's 429 `Retry-After` header; bot/subtype/own
messages are ignored so the monitor can't loop on itself.

### GET /slack/status
```json
{ "mode": "slack | simulated", "channel": "C… | null",
  "token": "set | missing", "reply_enabled": true,
  "last_poll_ts": "ISO-8601 | null", "last_error": "string | null" }
```
`token` is only ever the string `"set"` or `"missing"` — never the value.

### GET /feed?since=<id>&limit=50
Newest-first array of feed items; `since` returns only items with `id > since`.

Check items (`kind: "check"` — the default):
```json
{
  "id": 12, "ts": "ISO-8601 UTC", "kind": "check",
  "source": "slack | simulated | manual",
  "channel": "C… | null", "user": "U… | label | null", "text": "...",
  "status": "CLEAN | VIOLATION_DETECTED", "risk_level": "LOW|MEDIUM|HIGH",
  "violations": [ ...same shape as /verify-context... ],
  "suggested_rewrite": "string | null", "advisories": [ ... ],
  "actions": [ ...same shape as /verify-context... ],
  "meta": { "engine": "...", "checks_run": 8, "latency_ms": 1.2, "rules_ms": 0.9 }
}
```

Question items (`kind: "question"`) carry the ask result instead of a
verdict:
```json
{
  "id": 13, "ts": "ISO-8601 UTC", "kind": "question",
  "source": "slack | manual",
  "channel": "C… | null", "user": "U… | null",
  "text": "? can I give a 20% discount?",
  "question": "can I give a 20% discount?",
  "status": "QUESTION", "risk_level": "LOW", "violations": [],
  "answer": "Discounts are capped at 10% — anything bigger needs approval.",
  "sources": [{ "brain_key": "financial_rules.max_unapproved_discount_percent",
                "value": 10 }],
  "matched": true,
  "suggested_rewrite": null, "advisories": [], "actions": [],
  "meta": { "engine": "rules | rules+llm", "latency_ms": 0.8 }
}
```
Items written before `kind` existed have no `kind` — treat missing as
`"check"`.

### GET /feed/stats
`{ total, flagged, critical, clean, questions, by_category: {CATEGORY: n},
last_ts, mode, learned }` — `questions` counts `kind: "question"` items
(excluded from flagged/clean); `learned` is the number of rules in
`brain.learned_rules`.

### POST /feed/inject
`{ "text": "...", "user": "optional" }` → runs the same verify pipeline
(context_type `slack_message`), stores it with `source: "manual"`, returns the
feed item. A `?`/`ask:` text is answered, not checked (`kind: "question"`).
422 on empty text.

### POST /feed/{id}/override
Human verdict on a feed item — the "you missed this" / "that's fine" teaching paths.

**Request**
```json
{ "decision": "missed | false_positive",
  "phrase": "required when decision=missed — becomes the learned rule;
             optional for false_positive (defaults to the matched span text)",
  "category": "optional — the violation category to suppress;
               defaults to the item's first violation category",
  "note": "optional free text" }
```

**Response**
```json
{ "override": { "type": "override", "ts": "...", "feed_id": 3,
                "decision": "missed", "phrase": "...", "note": "...",
                "rule_id": "lr_1 | le_1 | null" },
  "rule": "stored learned rule | null",
  "exception": "stored learned exception | null",
  "recheck": "fresh verify result for the item's text | null" }
```

- `missed` → runs the /learn logic with `source_feed_id=id`, re-verifies the
  item's text, and updates the stored feed item so it flips to its new verdict
  (typically CLEAN → VIOLATION_DETECTED).
- `false_positive` → stores a `learned_exceptions` entry (`{id, phrase,
  category, note?, source_feed_id, created_ts}`) via
  `rules.add_learned_exception`, reloads the brain, and re-verifies the item —
  `recheck` drops the suppressed category whenever the phrase appears in the
  text. Exceptions are enforced by the deterministic engine like everything
  else. 422 when the category can't be inferred (item has no violations) or
  no phrase can be derived (no span text).
- Every call appends an `override` record to `backend/feed_log.jsonl` and a
  `FEED_OVERRIDE` row to the audit trail.
- 404 unknown feed id · 422 bad decision or missing phrase.

### Slack thread commands (SLACK_REPLY=1)

Replying inside a CommitGuard thread runs the same override logic:
`missed: <phrase>` → `decision="missed"` (teaches a rule); `fine` →
`decision="false_positive"` (learns an exception for that item). The bot
answers `📚 Learned: …` in the thread. Threads the bot has posted in are
polled via `conversations.replies` for 30 min after posting, at most once
every 5s; 429 `Retry-After` is honored.
