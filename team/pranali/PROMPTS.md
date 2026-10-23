# Pranali — Agent Prompts

Paste each prompt IN FULL into the coding agent, one at a time. The agent does the
technical work — your job is checking the result by clicking through
http://localhost:8000 (backend must be running — ask Riyansh if it isn't).

Your files: `demo/` and `pitch/` and `backend/scenarios.json`.
Never edit `backend/*.py` or `plugin/`.

---

## Prompt A — Demo v2: inline highlights (~11:15)

```
You are working on CommitGuard: a pre-send compliance firewall. `demo/index.html`
is a single-file vanilla HTML/JS app talking to a FastAPI backend at
localhost:8000 (contract in repo-root CONTRACT.md). It renders violation cards
returned by POST /verify-context. Violations may include span {text, start, end}
— character offsets into the submitted text.

Task — upgrade demo/index.html, keeping it ONE file, vanilla JS/CSS, no build step:
1. Under the textarea, render a read-only "draft preview" showing the text with
   each violation's span highlighted: red underline for CRITICAL/HIGH, amber for
   MEDIUM/LOW, matching card colors. Updates after each verify; textarea stays
   editable.
2. Clicking a card flashes its highlight; clicking a highlight flashes the card.
3. If a span's offsets don't line up, fall back to quoting span.text in the card.
4. Send each scenario's context_type (from /scenarios) in the /verify-context
   request instead of the hardcoded "outgoing_email" — when context_type is
   "incoming_invoice", show "Stage in Round" + "Escalate to CFO" buttons
   INSTEAD of Send/Apply-fixes.
5. Preserve the existing layout (left compose, right brain+audit rail) and dark
   theme.
After: I will click all 4 scenario buttons and confirm highlights + cards appear.
```

## Prompt B — Polish pass (~12:30, only if A is done)

```
Context: `demo/index.html` — CommitGuard demo UI, single file, backend at :8000.

Task — product polish, still one file:
1. Violation cards: subtle fade-in animation, severity icon (▲ HIGH/CRITICAL,
   ● MEDIUM/LOW).
2. Header chip shows meta.engine ("rules" → label "local checks", "rules+llm" →
   "AI-enriched") with the latency next to it.
3. Toast on every /execute-action response showing message + audit_log_id.
4. Company Brain panel: collapsible; each violation's evidence.brain_key rendered
   in a monospace "receipt" style.
5. Cmd+Enter = Send (when enabled), Cmd+Shift+F = apply fixes.
No new dependencies, no frameworks.
```

## Prompt C — Encode my scenario texts (~13:00)

```
Context: `backend/scenarios.json` holds the 4 demo texts for CommitGuard. The
rules engine fires on specific trigger strings — my rewrites below PRESERVE all
triggers deliberately. Replace the file's "text" values with mine, keeping each
key, label, and context_type unchanged.

[PASTE YOUR 4 TEXTS HERE — sales_email, vendor_invoice, support_reply, clean_email]

Requirements for the agent:
- Valid JSON, keep file structure identical otherwise.
- Then RUN: cd backend && uv run python smoke_test.py — sales_email must show 3
  violations (FINANCIAL_POLICY, MARGIN_BREACH, TREASURY_LOCK), vendor_invoice must
  show CRITICAL PAYMENT_REDIRECTION plus 2 CONTRACT_OVERAGE, support_reply must
  show 2 PROMISE_BREACH, clean_email must be CLEAN. If any expected violation is
  missing, tell me exactly which trigger string was lost — do NOT "fix" my text
  silently.
```

## Prompt D — Submission blurb (~11:00)

```
Context: CommitGuard — a pre-send compliance firewall for the "company brain".
Outgoing emails/messages and incoming invoices are checked against a structured
company knowledge base (contracts, treasury rules, engineering status) by a
deterministic rules engine (<5ms, works offline) with optional OpenAI structured-
output enrichment. Violations cite their evidence, offer one-click compliant
rewrites, and write an audit trail. Live demo catches: Net-60 vs Net-30 policy,
15% vs 10% discount cap, a quarterly-billing breach, a fraudulent IBAN change on
a vendor invoice (CRITICAL), and support claiming unshipped features.

Task: write `pitch/submission.md` containing:
- a 100-word submission description (judges' first read)
- 5 bullets: "what we built"
- a "why it matters" paragraph citing: UK invoice & mandate fraud = £41.3M/yr
  (UK Finance 2025); fake invoices = most common UK business fraud (Gov.uk
  Economic Crime Survey 2024, 11% of businesses); position vs Round Treasury —
  "Round catches bad invoices in the ledger; CommitGuard catches bad invoices and
  bad promises at the keyboard, before they enter the system."
Tone: confident, precise, zero hype adjectives.
```

## Prompt E — Judging-sheet for rehearsal (filler, ~14:00)

```
Write `pitch/rehearsal-sheet.md` for CommitGuard (pre-send compliance firewall,
Finance/Ops track, judges from Round Treasury/Lightfern/OpenAI). Sections:
1. 90-second run-of-show checklist (hook → 3 demo acts → kicker → close) with
   target seconds per beat.
2. A scoring rubric a teammate can tick during rehearsal: clear problem (1-5),
   demo worked (1-5), sponsor relevance (1-5), evidence shown (1-5), time kept (±s).
3. 6 likely judge questions with one-line answers (from pitch/script.md Q&A).
Keep it one page.
```
