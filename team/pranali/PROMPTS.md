# Pranali — Agent Prompts (the full frontend + content build)

**How to use:** work top-to-bottom through the phases. Paste each prompt into your
agent IN FULL — self-contained, the agent codes, you verify at
http://localhost:8000 by clicking. Backend must be running —
`cd backend && uv run uvicorn main:app --port 8000` (ask Riyansh if it isn't).

**Your files:** everything in `demo/` + `pitch/` + `backend/scenarios.json` (data only).
**Never touch:** `backend/*.py`, `plugin/`.
**Contract:** `CONTRACT.md` at repo root — the backend API is fixed.

---

# PHASE 1 — Flagship demo UI (10:45–13:00)
Goal: `demo/index.html` becomes a product — the thing judges screenshot.

## Prompt A — Rebuild the compose experience (the big one)

```
You are building part of CommitGuard, a hackathon project: a "pre-send firewall"
that checks outgoing drafts and incoming invoices against a company knowledge
base ("the brain") and flags violations inline, with one-click compliant fixes.

CONTEXT: Backend at http://localhost:8000, API in repo-root CONTRACT.md — READ IT
FIRST. `demo/index.html` exists — read it, keep its dark theme and CSS variable
names, but you may restructure the markup freely. Single file, vanilla HTML/CSS/JS,
NO frameworks, NO external assets/fonts/CDNs (must work offline on localhost).

BUILD THE FULL UI — exact spec:

LAYOUT
- Top header: "CommitGuard" wordmark + tagline "the pre-send firewall" + right side:
  engine chip (from meta.engine: "rules" -> "local checks" green dot / "rules+llm"
  -> "AI-enriched" blue dot), health dot polling GET /health every 5s (green/red),
  and an "Inspector →" link to /inspector.html.
- Two-column grid: LEFT (58%) compose panel; RIGHT (42%) rail with two stacked
  panels: "Company Brain" and "Audit Log".

COMPOSE PANEL
- Row of scenario buttons fetched from GET /scenarios (label as button text);
  clicking fills the body textarea AND stores that scenario's context_type.
- Inputs: To, Subject, then large body textarea (the draft).
- Draft preview area (read-only div BELOW the textarea): renders the same text
  with each violation's span {start,end} underlined — wavy red underline for
  CRITICAL/HIGH, wavy amber for MEDIUM/LOW — using text-decoration or a
  background span wrap. Rebuilt after every verify. If span offsets don't match
  the text (defensive), skip highlight for that violation and quote span.text in
  the card instead.
- Status row: colored dot + status text + right-aligned meta line
  ("<latency_ms>ms · <checks_run> checks"). States: idle (grey), checking…
  (amber pulse), CLEAR — brain-backed send (green), N violations — risk X (red),
  backend offline (grey, previous results stay visible — never clear cards on
  error).

VIOLATION CARDS (the star of the show)
Each card, stacked below status row:
- 3px left border: CRITICAL #f85149, HIGH #f0883e, MEDIUM #d29922, LOW #8b98a9.
- Top line: severity+category chip (uppercase, colored).
- Issue text (main body).
- Evidence receipt, monospace, subtle background: "brain: <evidence.brain_key>
  = <expected>  ·  found: <found>" — this must look like a receipt/quote.
- Correction: prefixed "→ ", green.
- Subtle fade-in animation (0.2s). Clicking a card flashes its preview highlight;
  clicking a highlight flashes the corresponding card.

ACTION ROW (context-aware — implement exactly)
- "Apply all fixes": enabled only when top-level suggested_rewrite exists →
  replaces body text, re-verifies, toast result.
- "Send": enabled only when status CLEAN → SEND_APPROVED → toast.
- "Send anyway": hidden if any CRITICAL violation → prompt() for reason →
  APPROVE_OVERRIDE (cancel = abort) → toast showing audit_log_id.
- "Escalate to CFO" + "Stage in Round": shown ONLY when context_type is
  "incoming_invoice" OR a CRITICAL exists → ESCALATE_FRAUD / STAGE_INVOICE → toast.
- Toasts: bottom-center, message + audit_log_id, 3s auto-dismiss, queue if multiple.

RIGHT RAIL
- "Company Brain": collapsible; GET /brain rendered as indented key/value tree
  (not raw JSON string) — monospace, dimmed values; refresh button.
- "Audit Log": GET /audit-log?limit=8 every 4s; one line each:
  "<action_type> · <audit_log_id> · <short ts>"; newest entries flash once.

KEYBOARD: Cmd+Enter = Send when enabled; Cmd+Shift+F = Apply all fixes.

ERROR HANDLING: every fetch in try/catch; failure -> "backend offline" status,
keep last UI, health dot red. No uncaught rejections ever.

VERIFY: all 4 scenarios behave exactly: sales_email → 3 cards each with an
evidence receipt + working Apply all fixes that re-verifies CLEAN; vendor_invoice
→ CRITICAL card, Send gone, Escalate+Stage visible; support_reply → 2 cards;
clean_email → instant green CLEAR + Send works. Kill backend → "backend offline"
state, health dot red, cards remain. Report results.
```

## Prompt B — Micro-polish pass (only after A verifies)

```
Context: `demo/index.html` — CommitGuard flagship UI just rebuilt and verified
(backend localhost:8000, CONTRACT.md). Keep it one file, no dependencies.

TASK — finishing touches:
1. Scenario buttons: show a tiny colored tag for context_type on each
   (invoice = orange tag, email = blue tag).
2. Card expand/collapse for long issue texts (>200 chars) with "more/less".
3. Copy-to-clipboard icon button on each evidence receipt line.
4. Word/char count under the textarea; verify triggers only when text changed
   since last check (skip duplicate calls).
5. Empty-state illustration for the rail's audit log when empty
   ("no actions yet — every decision lands here").
6. Title bar: page <title> "CommitGuard — the pre-send firewall"; add favicon via
   inline SVG data URI (simple shield glyph, monochrome).
VERIFY: click through all scenarios again; confirm no console errors.
```

---

# PHASE 2 — Inspector page + scenario content (13:00–14:00)

## Prompt C — Compliance Inspector page

```
Context: CommitGuard demo. Backend serves GET /inspector.html (route exists;
file is yours to create at `demo/inspector.html`). Endpoints: GET /brain,
GET /audit-log?limit=N, GET /health — per CONTRACT.md. Same dark aesthetic as
demo/index.html — read it and reuse the CSS variables/patterns. Single file,
vanilla JS, no dependencies.

BUILD `demo/inspector.html` — "CommitGuard Inspector — compliance console":
- Header: title + "← Compose" link back to / + live clock (updates each second).
- Three-column grid (stack on narrow):
  1. "Company Brain" — GET /brain rendered as grouped labeled cards:
     FINANCIAL RULES card (each rule key prettified: max_payment_terms →
     "Max payment terms"), SIGNED CONTRACTS card per vendor (name bold, retainer,
     rate, IBAN masked except last 4 — "••••5689"), ENGINEERING STATUS list
     (feature + status + date; status containing "merged"/"production" gets a
     green dot, others amber), PEOPLE. Refresh button.
  2. "Audit Trail" — GET /audit-log?limit=30, auto-refresh every 4s. Table:
     TIME | ACTION | LOG ID | RESULT. Newest first; rows that appeared since last
     poll flash once. Empty state: "No actions yet — every decision lands here."
  3. "Live Health" — GET /health every 4s: engine mode chip, checks count,
     brain_keys as small tags, response time of the health call in ms.
- Footer stat line: "rules engine <5ms · fully offline · zero data retention".
VERIFY: open /inspector.html — three panels populate; run a demo action in the
main page (e.g., click Send on clean_email) — watch it appear in Audit Trail
within 4s. Report.
```

## Prompt D — Encode my scenario rewrites

```
Context: `backend/scenarios.json` holds the 4 demo texts (mine — the "writing"
part is my job). The rules engine fires on specific trigger strings — my
rewrites below PRESERVE the triggers deliberately.

MY REWRITTEN TEXTS:
[PASTE YOUR 4 TEXTS: sales_email, vendor_invoice, support_reply, clean_email]

TASK:
1. Replace each scenario's "text" with mine. Keep keys, labels, context_type
   byte-identical. Valid JSON only.
2. RUN: `cd backend && uv run python smoke_test.py` and report — required:
   sales_email → FINANCIAL_POLICY + MARGIN_BREACH + TREASURY_LOCK ·
   vendor_invoice → CRITICAL PAYMENT_REDIRECTION + 2 CONTRACT_OVERAGE ·
   support_reply → 2 PROMISE_BREACH · clean_email → CLEAN.
3. If any expected violation is missing: tell me EXACTLY which trigger string
   was lost (diff against the old text) — do NOT "fix" my text yourself.
```

---

# PHASE 3 — Submission + pitch artifacts (14:00–14:45)

## Prompt E — Submission + rehearsal sheet

```
Context: CommitGuard — a pre-send compliance firewall for the "company brain".
Outgoing drafts and incoming invoices are checked against a structured company
knowledge base (contracts, treasury rules, engineering status) by a deterministic
rules engine (<5ms, runs fully offline) with an optional OpenAI structured-output
enrichment stage. Violations cite their evidence, offer one-click compliant
rewrites, and write an audit trail. The demo catches: Net-60 vs Net-30 policy,
15% vs 10% discount cap, quarterly-billing breach, a fraudulent IBAN change on a
vendor invoice (CRITICAL — send is blocked), and support claiming unshipped
features.

TASK — write two files:
1. `pitch/submission.md`:
   - 100-word submission description (judges' first read — lead with the fraud
     stat, not the tech).
   - 5 bullets "what we built".
   - "Why it matters" paragraph citing: UK invoice & mandate fraud = £41.3M/yr
     (UK Finance 2025); fake invoices = most common fraud hitting UK businesses
     (Gov.uk Economic Crime Survey 2024 — 11% of businesses, 27% hit by fraud
     overall); positioning vs sponsor: "Round Treasury catches bad invoices in
     the ledger. CommitGuard catches them — and the promises behind them — at
     the keyboard, before they enter the system."
   - Stack line: "FastAPI + deterministic rules engine + OpenAI structured
     outputs (optional) + Lightfern plugin runtime."
   Tone: confident, precise, ZERO hype adjectives (no "revolutionary/seamless").
2. `pitch/rehearsal-sheet.md`:
   - 90-second run-of-show table: BEAT | SECONDS | LINE — hook (15s: £41.3M stat)
     → act 1 sales email (12s) → act 2 invoice fraud (18s) → act 3 promise breach
     (10s) → clean pass (5s) → audit kicker (10s) → close (20s: "the LLM is the
     fallback, not the firewall" + Round positioning).
   - Tick-box rubric for a teammate scoring rehearsal: clear problem / demo
     worked / sponsor relevance / evidence receipts shown / time kept.
   - 6 likely judge Q&As (from pitch/script.md) condensed to one line each.
```

## Prompt F — Judge one-pager

```
TASK: create `pitch/one-pager.html` — a single self-contained printable A4
portrait page (light theme, prints cleanly, system fonts only, no external
assets) titled "CommitGuard — the pre-send firewall":
- Top: name + one-line pitch + the £41.3M stat.
- "What it catches": 4 compact rows (Policy breaches · Contract overages ·
  Payment redirection / mandate fraud · Unshipped-feature promises) each with a
  one-line example.
- Center: simple 3-box horizontal flow diagram in pure HTML/CSS boxes with
  arrows: "Text (email/Slack/invoice)" → "Deterministic rules × Company Brain"
  → "Fix / Block / Escalate + audit trail".
- Bottom band: "rules engine <5ms, fully offline · LLM optional (OpenAI
  structured outputs) · zero data retention".
Keep it genuinely printable: @media print rules, no dark backgrounds.
```

---

# NON-AGENT TASKS (yours, not the agent's — schedule around the phases)

- **Scenario text rewrites** (do during Phase 1 while agent builds Prompt A):
  write the 4 texts in a notes doc. The invoice must look REAL (line items, VAT,
  remittance block) while keeping: a wrong IBAN, £85/hr, £6,200+ total,
  "updated bank details". Sales email keeps: Net-60, 15% discount, quarterly
  billing. Support keeps: SOC 2 "complete and certified", SSO "is live". Clean
  keeps ONLY: Net-30, 10% discount, monthly/50% upfront. Then hand to agent via
  Prompt D.
- **Backup video** (~14:00): screen-record all 3 acts + clean pass, 60–90s,
  save `pitch/backup-demo.mp4`. Mandatory insurance — do not skip.
- **Pitch rehearsal** (14:30–15:30): 2 timed run-throughs with the team using
  rehearsal-sheet.md. You deliver the pitch.
- **Submit** (<16:00): paste from submission.md. Before 16:00, not at it.
- **Airplane-mode test** (~15:45): wifi off → demo still verifies → if not,
  tell Riyansh immediately.
