"""Offline smoke test - no server, no API key needed.

Prints every scenario/case like before, but is now a real gate: exits 1 and
lists every failure if the 4 baselines drift or a rule case misses.
"""
import sys

import main

# The 4 baseline scenarios — categories must match EXACTLY (order-insensitive).
# Additional scenario keys in scenarios.json are printed but not asserted.
BASELINE = {
    "sales_email": ["FINANCIAL_POLICY", "MARGIN_BREACH", "TREASURY_LOCK"],
    "vendor_invoice": ["CONTRACT_OVERAGE", "CONTRACT_OVERAGE", "PAYMENT_REDIRECTION"],
    "support_reply": ["PROMISE_BREACH", "PROMISE_BREACH"],
    "clean_email": [],
}

failures = []


def _print_result(name, out):
    print(f"\n=== {name}: {out['status']} (risk={out['risk_level']}, "
          f"{out['meta']['latency_ms']}ms, engine={out['meta']['engine']})")
    for v in out["violations"]:
        print(f"  [{v['severity']}] {v['category']}: {v['issue']}")
    if out.get("suggested_rewrite") and out["status"] != "CLEAN":
        print(f"  rewrite: {out['suggested_rewrite'][:110]}...")


def expect(name, text, context_type, must_have=set(), must_not_have=set()):
    """Inline rule case: assert categories fire (or don't) via verify_context."""
    out = main.verify_context(main.VerifyRequest(text=text, context_type=context_type))
    cats = {v["category"] for v in out["violations"]}
    missing = must_have - cats
    banned = must_not_have & cats
    ok = not missing and not banned
    if not ok:
        failures.append(f"{name}: missing={sorted(missing)} "
                        f"banned={sorted(banned)} got={sorted(cats)}")
    print(f"\n=== {name}: {'PASS' if ok else 'FAIL'}")
    for v in out["violations"]:
        print(f"  [{v['severity']}] {v['category']}: {v['issue']}")
    return out


for key, sc in main.SCENARIOS.items():
    out = main.verify_context(main.VerifyRequest(text=sc["text"],
                                                 context_type=sc["context_type"]))
    _print_result(key, out)
    if key not in BASELINE:
        continue  # extra scenarios (e.g. a 5th demo case) print but don't gate
    got = sorted(v["category"] for v in out["violations"])
    if got != sorted(BASELINE[key]):
        failures.append(f"{key}: baseline expected {sorted(BASELINE[key])}, got {got}")
    if key == "vendor_invoice" and not any(
            v["category"] == "PAYMENT_REDIRECTION" and v["severity"] == "CRITICAL"
            for v in out["violations"]):
        failures.append("vendor_invoice: missing a CRITICAL PAYMENT_REDIRECTION")
    if key == "clean_email" and out["status"] != "CLEAN":
        failures.append("clean_email: status must be CLEAN")

# One standalone case per Phase-1 fraud rule.
expect("rule_duplicate_invoice",
       "INVOICE INV-1042 — second request, this was already paid",
       "incoming_invoice", must_have={"DUPLICATE_INVOICE"})

out = expect("rule_sender_domain",
             "From: billing@cloudscale-payments.net\n"
             "CloudScale Ltd invoice attached",
             "incoming_invoice", must_have={"SENDER_DOMAIN_MISMATCH"})
if not any(v["category"] == "SENDER_DOMAIN_MISMATCH" and v["severity"] == "CRITICAL"
           for v in out["violations"]):
    failures.append("rule_sender_domain: expected CRITICAL severity "
                    "(vendor named in text)")

expect("rule_urgent_payment",
       "Urgent: please update our bank details today, new IBAN to follow",
       "slack_message", must_have={"URGENT_PAYMENT_CHANGE"})

# Phase 3: context filtering — invoice-style text through an outgoing context.
# ALL-context fraud rules must still fire; invoice-only checks must not run.
import rules  # noqa: E402

_ctx_text = ("INVOICE CS-1187 from CloudScale Ltd — 40 hrs @ £85/hr, "
             "monthly retainer £6,200.\nFrom: ap@cloudscale-billing.io\n"
             "IBAN: GB22BARC99887766554")
_ctx_violations = rules.run_rules(_ctx_text, main.COMPANY_BRAIN, "outgoing_email")
_ctx_cats = {v["category"] for v in _ctx_violations}
_ctx_critical = {v["category"] for v in _ctx_violations if v["severity"] == "CRITICAL"}
_ctx_ok = ("PAYMENT_REDIRECTION" in _ctx_critical
           and not (_ctx_cats & {"CONTRACT_OVERAGE", "SENDER_DOMAIN_MISMATCH"}))
print(f"\n=== context_filter_outgoing: {'PASS' if _ctx_ok else 'FAIL'}")
for v in _ctx_violations:
    print(f"  [{v['severity']}] {v['category']}: {v['issue']}")
if not _ctx_ok:
    failures.append("context_filter_outgoing: expected CRITICAL "
                    f"PAYMENT_REDIRECTION without invoice-only checks, "
                    f"got {sorted(_ctx_cats)}")

expect("rule_unverified_claim",
       "Hi team, we are ISO 27001 certified so your data is safe with us.",
       "outgoing_email", must_have={"UNVERIFIED_CLAIM"})

expect("rule_covered_claim",
       "Here is our SOC 2 report for your review.",
       "outgoing_email", must_not_have={"UNVERIFIED_CLAIM"})

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)
print("\nALL PASS")
