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
  "meta": { "engine": "rules | rules+llm", "checks_run": 8, "latency_ms": 3.2 }
}
```

Client rules:
- `severity: CRITICAL` → block Send, offer Escalate only.
- `span` is optional per violation; when present, clients SHOULD underline it inline.
- `suggested_rewrite` (top level) is the one-click "Apply all fixes" text.

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

### GET /brain/learned → learned rules array, newest first

## GET /audit-log?limit=N → newest-first array of audit entries
## GET /scenarios → { key: { label, context_type, text } } from backend/scenarios.json
## GET /health → { ok, engine: "rules"|"rules+llm", checks, brain_keys, feed: { mode: "slack"|"simulated", channel, last_poll_ts, error? } }
## GET / → demo/index.html · GET /inspector.html → demo/inspector.html

## Live feed (Slack monitor; see backend/slack_feed.py)

A background thread checks every new message in a Slack channel when
`SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID` are set (polls conversations.history
every 3s; `SLACK_REPLY=1` also posts one threaded Block Kit warning per
flagged message and a ✅ reaction per clean one, default OFF). With either
unset it runs **simulated mode** — cycling backend/scenarios.json every 8s —
so the demo works offline. Every item also appends to
`backend/feed_log.jsonl` (gitignored) and writes a `FEED_CHECK`
row to the audit trail. The token is never returned or logged.

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
```json
{
  "id": 12, "ts": "ISO-8601 UTC", "source": "slack | simulated | manual",
  "channel": "C… | null", "user": "U… | label | null", "text": "...",
  "status": "CLEAN | VIOLATION_DETECTED", "risk_level": "LOW|MEDIUM|HIGH",
  "violations": [ ...same shape as /verify-context... ],
  "suggested_rewrite": "string | null", "advisories": [ ... ],
  "meta": { "engine": "...", "checks_run": 8, "latency_ms": 1.2, "rules_ms": 0.9 }
}
```

### GET /feed/stats
`{ total, flagged, critical, clean, by_category: {CATEGORY: n}, last_ts, mode,
learned }` — `learned` is the number of rules in `brain.learned_rules`.

### POST /feed/inject
`{ "text": "...", "user": "optional" }` → runs the same verify pipeline
(context_type `slack_message`), stores it with `source: "manual"`, returns the
feed item. 422 on empty text.

### POST /feed/{id}/override
Human verdict on a feed item — the "you missed this" teaching path.

**Request**
```json
{ "decision": "missed | false_positive",
  "phrase": "required when decision=missed — becomes the learned rule",
  "note": "optional free text" }
```

**Response**
```json
{ "override": { "type": "override", "ts": "...", "feed_id": 3,
                "decision": "missed", "phrase": "...", "note": "...",
                "rule_id": "lr_1 | null" },
  "rule": "stored learned rule | null",
  "recheck": "fresh verify result for the item's text | null" }
```

- `missed` → runs the /learn logic with `source_feed_id=id`, re-verifies the
  item's text, and updates the stored feed item so it flips to its new verdict
  (typically CLEAN → VIOLATION_DETECTED).
- `false_positive` → records the verdict only; `rule` and `recheck` are null.
- Every call appends an `override` record to `backend/feed_log.jsonl` and a
  `FEED_OVERRIDE` row to the audit trail.
- 404 unknown feed id · 422 bad decision or missing phrase.
