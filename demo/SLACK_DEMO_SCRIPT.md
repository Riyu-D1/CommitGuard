# CommitGuard — live Slack demo script

**Setup:** backend running (`cd backend && uv run uvicorn main:app --port 8000`;
optionally `uv run python seed_audit.py --reset` for a fresh audit trail).
Three teammates in one real Slack channel: **Alex** (sales lead), **Sam**
(ops/finance), **Priya** (support). CommitGuard checks every message before
it's sent. Type each message exactly — they're tuned to the brain.

## Beats, in order

| # | Who | Type this | Expected catch | Say to judges |
|---|-----|-----------|----------------|---------------|
| 1 | Alex (sales) | `quick check — told Acme Corp we can do Enterprise at £85/seat if they sign Friday, that's fine right?` | **PRICE_FLOOR** (£85 < £110 Enterprise floor) + **CONFIDENTIAL_LEAK** (customer name + figure) | "The brain knows our per-seat floors and our customer list — two policy breaks in one casual sentence." |
| 2 | Sam (ops) | `expensing the £6,800 monitoring tool — putting it on the company card this afternoon, too small to bug Amara right?` | **APPROVAL_REQUIRED** (£6,800 > £5,000 limit) | "It knows the CFO approval threshold — 'too small to bug Amara' is exactly the rationalization it exists for." |
| 3 | Priya (support) | `for the churn thread: Acme Corp was paying £48k/yr and Globex is at £31k ARR — numbers above for context` | **CONFIDENTIAL_LEAK** (customer names + revenue figures) | "Customer names next to revenue — a data-handling policy break, not a finance rule. Every flag cites its brain key." |
| 4 | Alex (sales) | `the investor asked for refs — gonna send them our client list + the Acme Corp contract so they can choose` | **CONFIDENTIAL_LEAK — CRITICAL** | "Sharing the client list externally is a CRITICAL block: Send is disabled, Escalate is the only option." |
| 5 | Sam (ops) | `for the new pilot I quoted £50/seat on Growth and told them I'd expense the £9,000 onboarding myself` | **PRICE_FLOOR** (£50 < £65 Growth floor) + **APPROVAL_REQUIRED** (£9k spend) | "Two different policy families in one message — pricing and spend — no LLM, just rules and evidence." |
| 6 | Priya (support) | `fyi the retro moved to Thursday 3pm, usual room — agenda's in the doc` | **CLEAN** | "And normal chatter passes — it isn't a keyword panic button, it knows the difference." |

## The learn moment — "it learns and updates itself"

1. **Alex types:** `btw I promised the prospect a rebate if legal pushes back`
   → **CLEAN** (deliberately — nothing covers rebates yet).
2. Say: *"It missed that one — fair. Watch a human teach it."* Add the learned
   rule with phrase `rebate` (via `POST /learn` once Riyansh's endpoint is live,
   or `rules.add_learned_rule({"phrase": "rebate"})`). The rule lands in
   `company_brain.json` under `learned_rules` with an `lr_` id.
3. **Alex types:** `same deal — offered them a rebate again, hope that's ok`
   → **LEARNED_RULE, HIGH**.
4. Say: *"It just learned. That rule now lives in the brain file and is
   enforced in every context, like it was always there."*

## Backup beats (if judges ask for fraud)

- `slack_urgent_fraud` scenario button → URGENT_PAYMENT_CHANGE +
  PAYMENT_REDIRECTION, both CRITICAL — the #1 invoice-fraud pattern.
- `vendor_invoice` scenario → mismatched IBAN vs the signed contract, CRITICAL.
