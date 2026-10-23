# CommitGuard — Hackathon Playbook
**Company Brain Buildathon · Sat 24 Oct 2026 · The Building Centre, London**

---

## 1. Event intel

| | |
|---|---|
| Build window | 10:45 → 16:00 (**~5 hours**) |
| Team + track submission deadline | **11:15** (decide before you arrive) |
| Submission | 16:00 · Prizes 16:30 |
| Host / Open Track | **Lightfern** — 5-person London startup, ex-OpenAI London founders (Doug Li). "Cursor for email": autocomplete, inline editing, zero data retention, values *craft/individuality/authenticity* |
| Finance/Ops Track | **Round Treasury** — AI treasury + AP automation. Their product *already* advertises "automated fraud checks" catching "unusual amounts or sudden changes to a supplier's bank details" and "complete audit trail" |
| Sales Track | **Jumpstart** — early-career hiring platform |
| Tech partner | **OpenAI** (credits provided — use `gpt-4o-mini`, mention Structured Outputs) |

## 2. Positioning

> **CommitGuard is the pre-send firewall for the company brain.**
> Everyone here is building the *read* side of the company brain — we built the *write* side.
> Nothing leaves the company that the brain can't back up.

Tagline options: "Spellcheck for commitments." / "Grammarly checks your grammar; CommitGuard checks your promises."

Why it lands with *each* judge:
- **Round Treasury**: their fraud checks live *inside* the ledger. CommitGuard is the upstream last mile — it catches the £41.3M/year problem (UK invoice & mandate fraud, UK Finance 2025) at the keyboard, before an invoice or promise ever enters the system. Our `STAGE_INVOICE` action literally writes to a `round_staging_queue.json` — name-drop it as "the staging queue Round's AP agent would pick up."
- **Lightfern**: we run on the same surface they own — the moment of writing. Autocomplete finishes your sentence; CommitGuard makes sure you can stand behind it. Rules engine is local + zero-retention, matching their ethos.
- **Jumpstart/Sales**: the sales track angle is "reps over-promise" — CommitGuard is a promise firewall. Our act-1 demo *is* a sales email.
- **OpenAI**: Structured Outputs with strict JSON schema, but the talking point is that the **LLM is the fallback, not the firewall** — deterministic checks first (sub-5ms, auditable, offline), LLM only for nuance and rewriting.

Pitch stat: *"Invoice and mandate fraud cost UK businesses £41.3M last year; fake invoices are the single most common fraud type; 43% of businesses don't even know it exists. Round catches it in the ledger. We catch it where it starts — at the keyboard."*

## 3. Track choice

**Submit to Finance/Ops (Round Treasury).** Our strongest demo (invoice fraud) is squarely in their domain, and we mirror their feature vocabulary back at them. The sales and promise angles give us Open-track coverage for free.

## 4. Demo narrative — three acts + a green pass

Run at `http://localhost:8000` (demo.html — works with **no OpenAI key and no wifi**):

1. **Sales email** (Net-60, 15% discount, quarterly billing) → 3 violations appear inline as they type, each with the *brain receipt* (`financial_rules.max_payment_terms = Net-30`). One click → compliant rewrite. *"The rep just saved the deal's margin without knowing the rules existed."*
2. **Vendor invoice** (CloudScale: £85/hr vs £70 contracted, £6,200 vs £5,000 retainer, **different IBAN**) → CRITICAL `PAYMENT_REDIRECTION`: *"the signature of mandate fraud."* Send is disabled; buttons become **Escalate to CFO** / **Stage in Round**. *"Round would catch this in the ledger. We caught it in the inbox."*
3. **Support reply** ("SOC 2 is complete, SSO is live") → `PROMISE_BREACH` x2: brain says "in audit, expected November" / "in development." *"The brain isn't just rules — it's operational truth. Don't promise what engineering hasn't shipped."*
4. **Clean pass** (Net-30, 10%, 50% upfront) → green: *"And when it's fine, it gets out of your way — like a good autocomplete."*

Kicker: open `audit_log.jsonl` — every block, fix, and override is a JSON line. *"Compliance people don't want magic, they want a trail."*

Live-brain trick (if time): `POST /brain/reload` after editing `company_brain.json` — *"add a rule, it enforces everywhere instantly."*

## 5. Architecture

```
Lightfern plugin (thin) ──┐
demo.html (fallback)   ──┼─▶ POST /verify-context ─▶ rules.py (deterministic, <5ms)
Slack/Notion/etc (future)─┘         │                    └▶ OpenAI enrich (optional, 8s timeout, fail-open)
                                    ▼
                           POST /execute-action ─▶ audit_log.jsonl (+ round_staging_queue.json)
```

Files: `backend/main.py` (API), `backend/rules.py` (deterministic checks w/ evidence citations + span fixes), `backend/company_brain.json` (the brain), `backend/scenarios.json` (demo data), `demo/index.html` (compose-box UI), `backend/smoke_test.py`. Run from `backend/`: `uv run uvicorn main:app --port 8000`.

**Plugin integration:** keep all logic in this backend. The Lightfern plugin only needs: get draft text → POST `/verify-context` → render cards → button → POST `/execute-action`. If the SDK fights you, ship demo.html and say "the same check runs anywhere text leaves the company — the plugin is one client."

## 6. Hour-by-hour (tomorrow)

- **09:30–10:45** Talks. Note the Lightfern plugin API shape; flag questions for their team early.
- **10:45–11:15** Register team + **Finance/Ops track**. Get plugin hello-world rendering *anything*.
- **11:15–13:00** Wire plugin → `/verify-context` → violation cards → Apply-fixes button → `/execute-action`.
- **13:00–14:30** Polish: severity colors, evidence lines, Escalate/Stage buttons. Record a **backup screen-recording** of demo.html working (insurance).
- **14:30–15:30** Rehearse the 90-sec pitch 3x. Freeze features.
- **15:30–16:00** Submit. Test once more on venue wifi AND on hotspot/offline.

## 7. Pitch script (~90s)

"Last year UK businesses lost £41 million to invoice and mandate fraud — and it's the most common fraud they face. But that's just the money that leaves. Every day, employees make promises the company can't keep: payment terms the CFO never approved, discounts that kill margin, features that haven't shipped.

CommitGuard is the pre-send firewall for the company brain. [demo] As you type, every claim is checked against the brain — contracts, treasury rules, engineering status — in under 5 milliseconds, deterministically, no LLM required. When it finds a contradiction, it shows you the receipt, fixes it in one click, and writes it to the audit trail. The LLM is only there to polish the rewrite.

Round Treasury catches bad invoices in the ledger. We catch them — and bad promises — where they're born: at the keyboard."

## 8. Q&A prep

- *"Why not just prompt an LLM?"* → Non-deterministic, slow, unauditable. Rules first, LLM optional — fail-open design.
- *"False positives?"* → Severity tiers + 'Send anyway' requires a reason written to the log. Guardrails, not handcuffs.
- *"Privacy?"* → Rules run fully local; zero retention, aligned with Lightfern's posture.
- *"Scaling?"* → Brain syncs from Xero/NetSuite/contract store; rules are generated, not handwritten.
- *"Who pays?"* → CFO/CRO: it sells to the same buyer as Round — we're a natural partner, not a competitor.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Venue wifi dies / OpenAI down | Rules engine is offline; demo.html needs only localhost. Pre-record backup video. |
| Plugin SDK is rough/undocumented | Backend does everything; demo.html is a full fallback client. Ask Lightfern team at 10:45 sharp. |
| OpenAI key missing | `OPENAI_API_KEY` unset → engine reports `rules`, rewrites are template-based. Demo still 100%. |
| Time crunch | Backend is already done — hackathon hours go entirely to plugin + polish + pitch. |
| Live-demo freeze | `smoke_test.py` proves scenarios offline; screenshot the four passes. |

## 10. Pre-flight checklist

- [ ] `cd commitguard && uv run uvicorn main:app --port 8000` → demo at localhost:8000
- [ ] `uv run python smoke_test.py` → 4 scenarios pass
- [ ] `export OPENAI_API_KEY=...` (optional — engine shows `rules+llm`)
- [ ] Charger, hotspot ready, backup video on desktop
- [ ] Know the 90-sec pitch cold
