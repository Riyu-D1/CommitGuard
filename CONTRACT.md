# API Contract — DO NOT BREAK without flagging the team

This file is the stability boundary between Riyansh (plugin + llm_enrich.py),
Darsh (rules.py + actions.py + brain), and Pranali (demo + scenarios). You may
ADD fields; you may NOT rename or remove fields without a PR comment that
everyone acknowledges.

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
      "category": "FINANCIAL_POLICY | MARGIN_BREACH | TREASURY_LOCK | PAYMENT_REDIRECTION | CONTRACT_OVERAGE | APPROVAL_REQUIRED | PROMISE_BREACH",
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
## GET /audit-log?limit=N → newest-first array of audit entries
## GET /scenarios → { key: { label, context_type, text } } from backend/scenarios.json
## GET /health → { ok, engine: "rules"|"rules+llm", checks, brain_keys }
## GET / → demo/index.html · GET /inspector.html → demo/inspector.html
