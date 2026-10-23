# CommitGuard — 90-second pitch script

**Hook (15s)**
"Last year UK businesses lost £41 million to invoice and mandate fraud — the single
most common fraud they face. But it's not just invoices: every day, employees write
checks the company can't cash — payment terms the CFO never approved, discounts that
kill margin, product promises engineering hasn't shipped."

**What it is (15s)**
"CommitGuard is the pre-send firewall for the company brain. It checks every outgoing
message — and every incoming invoice — against the company's own knowledge: contracts,
treasury rules, engineering status. Before it leaves the building."

**Demo (45s)** — three acts, narrate over live clicks
1. Sales email → "As they type, three violations — Net-60 vs the CFO's Net-30 policy,
15% vs the 10% discount cap, quarterly billing that's locked. Each one cites its
source in the brain. One click — compliant rewrite."
2. Invoice → "This invoice looks fine — until you check the brain. Wrong rate, wrong
amount, and the IBAN doesn't match the signed contract. That's the signature of
mandate fraud. Send is disabled — escalate to the CFO, or stage it for Round's
approval queue."
3. Support reply → "SOC 2 'complete'? The brain says it's still in audit. SSO 'live'?
Still in development. Don't promise what hasn't shipped."

**Close (15s)**
"The LLM is the fallback, not the firewall — deterministic checks run in under 5
milliseconds, fully offline, every one citing its evidence. Round catches bad invoices
in the ledger. We catch them — and bad promises — where they're born: at the keyboard.
And every decision lands in an audit trail, because compliance wants receipts, not magic."

---

## Q&A crib

- *Why not just prompt an LLM?* Non-deterministic, slow, unauditable. Rules first,
  LLM optional — the demo works on airplane mode.
- *False positives?* Severity tiers; "send anyway" demands a reason on the record.
  Guardrails, not handcuffs.
- *Privacy?* Rules run fully local; zero data retention — same posture as Lightfern.
- *Where does the brain come from?* Synced from contracts/Xero/NetSuite/status pages —
  we consume it, we don't replace it.
- *Who's the buyer?* Same as Round's: CFO/finance ops. We're a partner, not a rival.
