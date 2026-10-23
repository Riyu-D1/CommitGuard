# CommitGuard — Rehearsal Sheet

## 90-second run-of-show

| Beat | Seconds | Line / action |
|---|---|---|
| Hook | 0–15 | "UK businesses lost £41M to invoice fraud last year — and it starts with a human typing yes. But it's not just invoices: every day employees write checks the company can't cash." |
| Act 1 — sales email | 15–27 | Click sales_email → "As they type: Net-60 vs the CFO's Net-30, 15% vs the 10% cap, quarterly billing that's locked. Each cites its source in the brain. One click — compliant rewrite." → Apply all fixes |
| Act 2 — invoice fraud | 27–45 | Click vendor_invoice → "Looks fine — until the brain. Wrong rate, wrong amount, and the IBAN doesn't match the signed contract. That's the signature of mandate fraud. Send is gone — escalate to the CFO, or stage it for Round's queue." |
| Act 3 — promise breach | 45–55 | Click support_reply → "SOC 2 'complete'? Still in audit. SSO 'live'? Still in development. Don't promise what hasn't shipped." |
| Clean pass | 55–60 | Click clean_email → "And when it's fine — green. It gets out of your way." |
| Kicker | 60–70 | Show Inspector/audit log → "Every block, fix, and override lands in an audit trail. Compliance wants receipts, not magic." |
| Close | 70–90 | "The LLM is the fallback, not the firewall — deterministic checks in under 5ms, fully offline. Round catches bad invoices in the ledger; we catch them — and bad promises — at the keyboard." |

## Scoring rubric (teammate ticks during rehearsal)

- [ ] Clear problem — a judge could repeat it back (1–5)
- [ ] Demo worked — zero dead clicks (1–5)
- [ ] Sponsor relevance — Round's language used (1–5)
- [ ] Evidence receipts shown — brain_key visible on screen (1–5)
- [ ] Time kept — total ≤ 90s (actual: ___)

## Judge Q&A (one-liners)

- *Why not just prompt an LLM?* Non-deterministic, slow, unauditable. Rules first — the demo works on airplane mode.
- *False positives?* Severity tiers; "send anyway" requires a reason on the record. Guardrails, not handcuffs.
- *Privacy?* Rules run fully local; zero data retention — same posture as Lightfern.
- *Where's the brain from?* Synced from contracts/Xero/NetSuite/status pages — we consume it, not replace it.
- *Who pays?* Same buyer as Round: CFO / finance ops. We're a partner, not a rival.
- *Plugin or product?* Both — the check runs anywhere text leaves the company; the plugin is one client.
