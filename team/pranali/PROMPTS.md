# Pranali — Agent Prompts

Run your agent continuously: paste prompt IN FULL → agent builds → you verify at
http://localhost:8000 (backend running — ask Riyansh if not) → next prompt.

Your files: `demo/`, `pitch/`, `backend/scenarios.json`. NEVER touch
`backend/*.py` or `plugin/`.

---

## Prompt A — Demo v2: inline highlights (~10:45)

```
You are working on CommitGuard: a pre-send compliance firewall. `demo/index.html`
is a single-file vanilla HTML/JS app talking to a FastAPI backend at
localhost:8000 (contract in repo-root CONTRACT.md). It renders violation cards
from POST /verify-context. Violations may include span {text, start, end} —
character offsets into the submitted text.

Task — upgrade demo/index.html, keeping it ONE file, vanilla JS/CSS, no build step:
1. Under the textarea, render a read-only "draft preview" showing the text with
   each violation's span highlighted: red underline CRITICAL/HIGH, amber
   MEDIUM/LOW, matching card colors. Updates after each verify; textarea stays
   editable.
2. Clicking a card flashes its highlight; clicking a highlight flashes the card.
3. If a span's offsets don't line up, fall back to quoting span.text in the card.
4. Send each scenario's context_type (from /scenarios) in the /verify-context
   request instead of hardcoded "outgoing_email" — and when context_type is
   "incoming_invoice", show "Stage in Round" + "Escalate to CFO" buttons INSTEAD
   of Send/Apply-fixes.
5. Preserve the layout (left compose, right brain+audit rail) and dark theme.
I'll verify by clicking all 4 scenario buttons.
```

## Prompt B — Polish pass (~12:00)

```
Context: `demo/index.html` — CommitGuard demo UI, single file, backend at :8000.

Task — product-grade polish, still one file:
1. Violation cards: subtle fade-in, severity icon (▲ HIGH/CRITICAL, ● MEDIUM/LOW).
2. Header chip shows meta.engine ("rules" → "local checks", "rules+llm" →
   "AI-enriched") + latency beside it.
3. Toast on every /execute-action response: message + audit_log_id.
4. Company Brain panel: collapsible; each violation's evidence.brain_key rendered
   in monospace "receipt" style.
5. Cmd+Enter = Send (when enabled); Cmd+Shift+F = apply fixes.
No new dependencies, no frameworks.
```

## Prompt C — Inspector page: compliance console (~12:30)

```
Context: CommitGuard demo at `demo/index.html` (backend localhost:8000, contract
in CONTRACT.md). Judges are finance/ops people who love audit trails.

Task — create `demo/inspector.html`, a second single-file page (same dark theme
as index.html — read it first and reuse its CSS variables/patterns):
- Title: "CommitGuard Inspector — compliance console"
- Three panels in a clean grid:
  1. Company Brain — GET /brain, rendered as readable grouped cards (Financial
     Rules, Signed Contracts, Engineering Status, People), not raw JSON — each
     value labeled. Refresh button.
  2. Audit Trail — GET /audit-log?limit=30 auto-refreshing every 4s: table of
     ts / action_type / audit_log_id / result. Newest first, new rows highlighted.
  3. Live Health — GET /health every 4s: engine mode, checks count, brain keys.
- A nav link back to the main demo ("← Compose").
Single file, vanilla JS, no dependencies. The backend already serves it at
GET /inspector.html. Add a small "Inspector →" link in demo/index.html's header
pointing to /inspector.html.
```

## Prompt D — Encode my scenario texts (~13:00)

```
Context: `backend/scenarios.json` holds the 4 demo texts for CommitGuard. The
rules engine fires on specific trigger strings — my rewrites below PRESERVE all
triggers deliberately. Replace each "text" value with mine; keep keys, labels,
context_type unchanged.

[PASTE YOUR 4 TEXTS: sales_email, vendor_invoice, support_reply, clean_email]

Requirements:
- Valid JSON, structure otherwise identical.
- Then RUN: cd backend && uv run python smoke_test.py — sales_email must show 3
  violations (FINANCIAL_POLICY, MARGIN_BREACH, TREASURY_LOCK), vendor_invoice must
  show CRITICAL PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE, support_reply must show
  2 PROMISE_BREACH, clean_email must be CLEAN. If an expected violation is
  missing, tell me which trigger string was lost — do NOT silently "fix" my text.
```

## Prompt E — Submission + rehearsal sheet (~13:30)

```
Context: CommitGuard — pre-send compliance firewall for the "company brain".
Drafts and incoming invoices checked against contracts/treasury rules/engineering
status by a deterministic rules engine (<5ms, offline-capable) + optional OpenAI
structured-output enrichment. Violations cite evidence, one-click compliant
rewrites, audit trail. Demo catches: Net-60 vs Net-30, 15% vs 10% discount cap,
quarterly-billing breach, fraudulent IBAN change (CRITICAL), unshipped-feature
claims.

Task — two files:
1. `pitch/submission.md`: 100-word submission description; 5 "what we built"
   bullets; "why it matters" citing UK invoice & mandate fraud £41.3M/yr (UK
   Finance 2025), fake invoices = most common UK business fraud (Gov.uk Economic
   Crime Survey 2024, 11%); positioning: "Round catches bad invoices in the
   ledger; CommitGuard catches them — and bad promises — at the keyboard."
   Tone: confident, precise, zero hype adjectives.
2. `pitch/rehearsal-sheet.md`: 90-second run-of-show checklist (hook → 3 acts →
   kicker → close) with target seconds per beat; a tick-box scoring rubric
   (clear problem / demo worked / sponsor relevance / evidence shown / time kept);
   6 likely judge questions + one-line answers (from pitch/script.md Q&A).
```

## Prompt F — Judge one-pager (stretch, ~14:00)

```
Task: create `pitch/one-pager.html` — a single self-contained printable page (A4
portrait, light theme, prints cleanly) explaining CommitGuard for judges:
tagline, 3-bullet "what it catches", the £41.3M stat, a simple 3-box architecture
diagram (Text → Rules+Brain → Action) in pure HTML/CSS boxes, and "rules engine
runs in <5ms, fully offline; LLM optional" as the credibility line. No external
assets/fonts — system fonts only.
```
