# Day 1 rules — what CommitGuard enforces

_Generated from `company_brain.json` — every rule cites its source._

## Payment terms
Terms capped at Net-30; extended terms need 50% upfront.
- Source: `financial_rules.max_payment_terms`
- Trips on: Offering Net-60 to close a deal.

## Discount cap
Discounts above 10% need approval in #finance-approvals.
- Source: `financial_rules.max_unapproved_discount_percent`
- Trips on: Promising a 15% discount without sign-off.

## Treasury lock
Quarterly billing disabled for cash runway optimization; enforce 50% upfront.
- Source: `financial_rules.treasury_lock`
- Trips on: Offering quarterly billing.

## Commitment approval
Commitments over £25,000 need CFO approval.
- Source: `financial_rules.cfo_approval_required_over_gbp`
- Trips on: Confirming a £30k deal directly.

## Refund cap
Refunds or credits over £500 need approval.
- Source: `financial_rules.refund_or_credit_cap_gbp`
- Trips on: Offering a £900 refund.

## Fraud controls
Urgency + bank-detail changes always require out-of-band verification.
- Source: `financial_rules.fraud_controls`
- Trips on: Processing an urgent bank-detail change.

## Expense limit
Any spend over £5,000 needs CFO approval first.
- Source: `internal_policies.expense_approval_limit_gbp`
- Trips on: Putting a £6,800 tool on the company card.

## Pricing floor
Never quote below the per-seat floor: Starter £40/seat, Growth £65/seat, Enterprise £110/seat.
- Source: `internal_policies.pricing_floor_gbp_per_seat`
- Trips on: Quoting Enterprise at £85/seat.

## Confidential data
No customer names + revenue figures in public channels; never share the client list externally.
- Source: `internal_policies.confidential_data`
- Trips on: Posting 'Acme Corp pays £48k/yr' in a public channel.

## Trusted senders
Supplier email only counts from: cloudscale.co.uk, northwind-analytics.com, yourcompany.com, meridian-sec.com.
- Source: `known_sender_domains`
- Trips on: An invoice from @cloudscale-pay.com.

## Contract — CloudScale Ltd
Retainer £5,000/mo, £70/hr, IBAN GB29REVOLUT12345689.
- Source: `signed_contracts[CloudScale Ltd]`
- Trips on: Paying CloudScale Ltd to a different IBAN.

## Contract — Northwind Analytics
Retainer £3,200/mo, £95/hr, IBAN GB14MONODE87654321.
- Source: `signed_contracts[Northwind Analytics]`
- Trips on: Paying Northwind Analytics to a different IBAN.

## Contract — Meridian Security Ltd
Retainer £4,200/mo, £80/hr, IBAN GB77NWBK11223344.
- Source: `signed_contracts[Meridian Security Ltd]`
- Trips on: Paying Meridian Security Ltd to a different IBAN.

## Status — Stripe Webhook Latency Fix
Merged to production (PR #409)
- Source: `engineering_status[Stripe Webhook Latency Fix]`
- Trips on: Claiming 'Stripe Webhook Latency Fix' is done and live.

## Status — SOC 2 Type II report
In audit, expected November 2026
- Source: `engineering_status[SOC 2 Type II report]`
- Trips on: Claiming 'SOC 2 Type II report' is done and live.

## Status — SSO / SAML support
In development, no committed date
- Source: `engineering_status[SSO / SAML support]`
- Trips on: Claiming 'SSO / SAML support' is done and live.

## Status — Bulkhead v2
Planning — not started
- Source: `engineering_status[Bulkhead v2]`
- Trips on: Claiming 'Bulkhead v2' is done and live.
