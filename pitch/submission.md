# CommitGuard — Submission

## 100-word description

UK businesses lost £41.3M to invoice and mandate fraud last year — and it starts
with a human typing "yes". CommitGuard is a pre-send firewall for the company
brain: every outgoing email, message, and incoming invoice is checked against the
company's own contracts, treasury rules, and engineering status before it leaves.
Violations are flagged inline with cited evidence, fixed in one click, and logged
to an audit trail. Deterministic checks run in under 5ms, fully offline — the LLM
is the fallback, not the firewall.

## What we built

- A deterministic rules engine (`backend/rules.py`) — 8+ checks for payment terms,
  discount caps, treasury locks, contract overages, bank-detail/IBAN mismatches,
  duplicate invoices, phishing signals, and unshipped-feature promises. Every
  violation carries a `brain_key` evidence receipt.
- An optional OpenAI structured-output enrichment stage (`gpt-4o-mini`,
  temperature 0, fail-open) that polishes rewrites without ever weakening a rule.
- A FastAPI backend serving verify + execute-action endpoints with a real audit
  log and a Round Treasury staging queue.
- Two thin clients: a Lightfern plugin (adapter + host-app integration) and a
  standalone compose UI — plus a compliance Inspector console (live brain view,
  audit trail, health).

## Why it matters

Fake invoices are the most common fraud hitting UK businesses (Gov.uk Economic
Crime Survey 2024: 11% of businesses, 27% hit by fraud overall). Round Treasury
catches bad invoices in the ledger. CommitGuard catches them — and the promises
behind them — at the keyboard, before they enter the system.

Stack: FastAPI · deterministic rules engine · OpenAI structured outputs
(optional) · Lightfern plugin runtime.
