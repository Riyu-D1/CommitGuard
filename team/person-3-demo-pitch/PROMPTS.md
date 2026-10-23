# Person 3 — Agent Prompts

Paste into your coding agent one task at a time. You own `demo/`, `pitch/`, and
`backend/scenarios.json`. Never edit `backend/*.py` or `plugin/`.

---

## Prompt A — Demo v2: inline highlights (use ~11:15)

```
Context: CommitGuard pre-send firewall. `demo/index.html` is a single-file vanilla
HTML/JS app that talks to a FastAPI backend at localhost:8000 (contract in repo-root
CONTRACT.md). It renders violation cards from POST /verify-context. Violations may
include span {text, start, end} — character offsets into the submitted text.

Task — upgrade demo/index.html:
1. Under the textarea, render a "draft preview" div that shows the text with each
   violation's span range highlighted (red underline for CRITICAL/HIGH, amber for
   MEDIUM/LOW), colored to match the card. Keep the textarea editable; the preview
   is read-only and updates after each verify.
2. Clicking a card scrolls/flashes its highlight. Clicking a highlight flashes the card.
3. Keep it robust: if a span's offsets don't match, fall back to quoting span.text.
4. Do NOT add frameworks or build steps — single file, vanilla JS/CSS. Preserve the
   existing layout (left compose, right brain+audit rail).
5. Send each scenario's context_type field (it exists in /scenarios response) in the
   /verify-context request instead of hardcoding "outgoing_email".
Verify by running the backend and clicking all 4 scenario buttons.
```

## Prompt B — Demo polish pass (use ~12:30)

```
Context: `demo/index.html` — CommitGuard demo UI, single file, backend at :8000.

Task — product-grade polish, still one file:
1. Violation cards: add subtle entrance animation, severity icon (▲ HIGH/CRITICAL,
   ● MEDIUM), and a copy button on the evidence line.
2. Header chip shows engine from meta.engine ("rules" = local deterministic,
   "rules+llm" = LLM-enriched) with a tooltip; latency displayed next to it.
3. Toasts for every /execute-action result showing message + audit_log_id.
4. Right rail: make Company Brain collapsible with the specific brain_key of each
   violation hyperlinked to scroll to that key in the JSON if visible (best-effort).
5. Keyboard: Cmd+Enter triggers Send (when enabled), Cmd+Shift+F applies fixes.
Keep the dark aesthetic. No new dependencies.
```

## Prompt C — Scenario refinement (use ~13:00; coordinate with P2 first!)

```
Context: CommitGuard demo data lives in `backend/scenarios.json` — 4 scenarios the
demo UI loads. The rules engine in `backend/rules.py` fires on regex patterns; every
scenario text MUST trigger its intended violations. The brain is
`backend/company_brain.json` — read it before editing.

Task — tighten scenario text for realism (the demo's credibility depends on it):
1. vendor_invoice: make it read like a real PDF-parsed invoice (header, line items,
   VAT line, payment instructions) while KEEPING the trigger strings: a non-contract
   IBAN, £85/hr rate (>£70 contracted), £6,200+ total (>£5,000 retainer),
   "updated bank details" phrasing.
2. sales_email: keep Net-60, 15% discount, quarterly billing; make it read like a
   real sales follow-up.
3. support_reply: keep claims that SOC 2 is "complete and certified" and SSO "is
   live" (both must hit PROMISE_BREACH via engineering_status).
4. clean_email: must stay CLEAN — only Net-30, ≤10% discount, monthly billing.
CRITICAL: after editing run `uv run python smoke_test.py` from backend/ — every
scenario must produce its intended status. If a rewrite broke a trigger, fix the text.
```

## Prompt D — Submission blurb (use ~11:00, then refine)

```
Context: CommitGuard is our hackathon project — a pre-send compliance firewall for
the "company brain". Drafts of emails/messages and incoming invoices are checked
against a structured company knowledge base (contracts, treasury rules, engineering
status) by a deterministic rules engine (<5ms, offline-capable) with optional LLM
enrichment via OpenAI structured outputs. Violations show cited evidence, offer
one-click compliant rewrites, and write an audit trail. Demo caught: Net-60 terms vs
Net-30 policy, 15% vs 10% discount cap, quarterly billing breach, a fraudulent IBAN
change on a vendor invoice (CRITICAL), and support claiming unshipped features.

Task: write `pitch/submission.md` containing:
- 100-word submission description (judges' first read)
- A 5-line "what we built" bullet list
- A "why it matters" para citing: UK invoice & mandate fraud = £41.3M/yr (UK Finance),
  fake invoices = most common UK business fraud (Gov.uk Economic Crime Survey 2024),
  and positioning vs Round Treasury (they catch it in the ledger, we catch it at the keyboard).
Tone: confident, precise, zero hype adjectives.
```
