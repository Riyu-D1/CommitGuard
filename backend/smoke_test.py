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

# Slack demo scenarios — every one is asserted (categories, order-insensitive).
SLACK_DEMO = {
    "slack_urgent_fraud": ["PAYMENT_REDIRECTION", "URGENT_PAYMENT_CHANGE"],
    "slack_demo_price_floor": ["CONFIDENTIAL_LEAK", "PRICE_FLOOR"],
    "slack_demo_expense": ["APPROVAL_REQUIRED"],
    "slack_demo_rev_leak": ["CONFIDENTIAL_LEAK"],
    "slack_demo_clientlist": ["CONFIDENTIAL_LEAK"],
    "slack_demo_spend_seats": ["APPROVAL_REQUIRED", "PRICE_FLOOR"],
    "slack_demo_clean": [],
}

EXPECTED = {**BASELINE, **SLACK_DEMO}

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
    if key not in EXPECTED:
        continue  # unlisted scenarios print but don't gate
    got = sorted(v["category"] for v in out["violations"])
    if got != sorted(EXPECTED[key]):
        failures.append(f"{key}: expected {sorted(EXPECTED[key])}, got {got}")
    if key == "vendor_invoice" and not any(
            v["category"] == "PAYMENT_REDIRECTION" and v["severity"] == "CRITICAL"
            for v in out["violations"]):
        failures.append("vendor_invoice: missing a CRITICAL PAYMENT_REDIRECTION")
    if not EXPECTED[key] and out["status"] != "CLEAN":
        failures.append(f"{key}: status must be CLEAN")

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

# "urgently" must hit the same urgency pattern as "urgent".
expect("rule_urgently",
       "Please pay invoice 4411 to our new IBAN GB00 1234 urgently",
       "incoming_invoice", must_have={"URGENT_PAYMENT_CHANGE"})

# darsh/learn: runtime learned rules — temp brain copy, add "rebate", verify
# it fires, verify re-adding dedupes, verify the real brain is untouched.
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

_real_brain = (Path(main.BASE) / "company_brain.json").read_text()
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as _tf:
    _tf.write(_real_brain)
    _tmp_brain = _tf.name

try:
    _lr = rules.add_learned_rule(
        {"phrase": "rebate",
         "issue": "Rebate offers require CFO sign-off.",
         "correction": "Remove the rebate offer or get CFO approval."},
        brain_path=_tmp_brain)
    _lr_brain = json.loads(Path(_tmp_brain).read_text())
    _lr_violations = rules.run_rules("We can offer a rebate on renewal.",
                                     _lr_brain, "outgoing_email")
    _lr_again = rules.add_learned_rule({"phrase": "REBATE"},
                                       brain_path=_tmp_brain)
    _lr_ok = ("LEARNED_RULE" in {v["category"] for v in _lr_violations}
              and _lr_again["id"] == _lr["id"]
              and len(_lr_brain.get("learned_rules", [])) == 1
              and (Path(main.BASE) / "company_brain.json").read_text()
              == _real_brain)
finally:
    os.unlink(_tmp_brain)

print(f"\n=== rule_learned: {'PASS' if _lr_ok else 'FAIL'}")
for v in _lr_violations:
    print(f"  [{v['severity']}] {v['category']}: {v['issue']}")
if not _lr_ok:
    failures.append("rule_learned: expected LEARNED_RULE hit + idempotent "
                    "re-add + real brain untouched")

# darsh/onboarding: explain_policy answers must be grounded — every cited
# brain_key must actually resolve inside company_brain.json.
import re  # noqa: E402


def _brain_has(brain, key):
    """Resolve 'a.b.c', 'a.b[Name]' and 'a.b[0]' style keys against the brain."""
    cur = brain
    for part in (p for p in re.split(r"[.\[\]]", key) if p):
        if isinstance(cur, dict):
            if part not in cur:
                return False
            cur = cur[part]
        elif isinstance(cur, list):
            hit = cur[int(part)] if part.isdigit() and int(part) < len(cur) \
                else next((i for i in cur if isinstance(i, dict)
                           and part in (i.get("vendor_name"), i.get("feature"),
                                        i.get("id"))), None)
            if hit is None:
                return False
            cur = hit
        else:
            return False
    return True


for _name, _q, _want in [
    ("onboarding_discount", "can I give a 20% discount?", True),
    ("onboarding_seat_price", "what's the lowest price per seat?", True),
    ("onboarding_expense", "do I need approval to expense £6,000?", True),
    ("onboarding_clientlist", "can I send the client list to an investor?", True),
    ("onboarding_bank_change", "a vendor sent a change of bank details — "
                               "what do I do?", True),
    ("onboarding_unknown", "does the office have a coffee machine?", False),
]:
    _res = rules.explain_policy(_q, main.COMPANY_BRAIN)
    _src_ok = all(_brain_has(main.COMPANY_BRAIN, s["brain_key"])
                  for s in _res["sources"])
    _ok = (_res["matched"] == _want and bool(_res["answer"])
           and _src_ok and (_res["sources"] or not _want))
    print(f"\n=== {_name}: {'PASS' if _ok else 'FAIL'}")
    print(f"  Q: {_q}")
    print(f"  A: {_res['answer']}")
    for s in _res["sources"]:
        print(f"  source: {s['brain_key']}")
    if not _ok:
        failures.append(f"{_name}: matched={_res['matched']} (want {_want}) "
                        f"sources_ok={_src_ok}")

# darsh/hands: learned exceptions — suppress exactly one category for one
# phrase, on a temp brain copy; the real brain file must be untouched.
_real_brain2 = (Path(main.BASE) / "company_brain.json").read_text()
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as _tf:
    _tf.write(_real_brain2)
    _tmp_brain2 = _tf.name

_exc_text = main.SCENARIOS["slack_demo_price_floor"]["text"]
try:
    _ex = rules.add_learned_exception(
        {"phrase": "£85/seat", "category": "PRICE_FLOOR",
         "note": "approved once for the Acme renewal"},
        brain_path=_tmp_brain2)
    _ex2 = rules.add_learned_exception(
        {"phrase": "£85/seat", "category": "PRICE_FLOOR"},
        brain_path=_tmp_brain2)  # same phrase+category -> same id
    _ex_brain = json.loads(Path(_tmp_brain2).read_text())
    _ex_brain["learned_exceptions"].append({"phrase": 123, "category": 4.5})  # bad rule
    _sup = rules.run_rules(_exc_text, _ex_brain, "slack_message")
    _sup_cats = {v["category"] for v in _sup}
    _unsup = rules.run_rules(
        "fyi the retro moved to Thursday 3pm", _ex_brain, "slack_message")
    _exc_ok = ("PRICE_FLOOR" not in _sup_cats          # suppressed
               and "CONFIDENTIAL_LEAK" in _sup_cats    # everything else stays
               and _ex2["id"] == _ex["id"]             # dedupe
               and _unsup == []                        # clean still clean
               and (Path(main.BASE) / "company_brain.json").read_text()
               == _real_brain2)                        # real brain untouched
    print(f"\n=== exception_suppress: {'PASS' if _exc_ok else 'FAIL'}")
    for v in _sup:
        print(f"  [{v['severity']}] {v['category']}: {v['issue']}")
    if not _exc_ok:
        failures.append("exception_suppress: PRICE_FLOOR should be suppressed, "
                        f"CONFIDENTIAL_LEAK kept; got {sorted(_sup_cats)}")
finally:
    os.unlink(_tmp_brain2)

# darsh/hands: plan_actions — the brain acts, not just flags.
import actions  # noqa: E402

for _name, _key, _must, _must_not, _target_check in [
    ("actions_invoice_fraud", "vendor_invoice",
     {"HOLD_PAYMENT", "ESCALATE"}, set(), "ESCALATE"),
    ("actions_expense", "slack_demo_expense",
     {"REQUEST_APPROVAL"}, {"HOLD_PAYMENT"}, "REQUEST_APPROVAL"),
    ("actions_clean", "clean_email", set(),
     {"HOLD_PAYMENT", "ESCALATE", "REQUEST_APPROVAL", "BLOCK_AND_REDACT",
      "SUGGEST_REWRITE"}, None),
]:
    _sc = main.SCENARIOS[_key]
    _out = main.verify_context(main.VerifyRequest(
        text=_sc["text"], context_type=_sc["context_type"]))
    _plan = actions.plan_actions(_out, main.COMPANY_BRAIN)
    _types = {a["type"] for a in _plan}
    _ok = _must <= _types and not (_must_not & _types)
    if _target_check == "ESCALATE":
        _ok = _ok and any(a["type"] == "ESCALATE"
                          and a["target"] == main.COMPANY_BRAIN["people"]["cfo"]
                          for a in _plan)
    if _target_check == "REQUEST_APPROVAL":
        _ok = _ok and any(
            a["type"] == "REQUEST_APPROVAL"
            and a["target"] == main.COMPANY_BRAIN["people"]
            ["finance_approval_channel"] for a in _plan)
    print(f"\n=== {_name}: {'PASS' if _ok else 'FAIL'}")
    for a in _plan:
        print(f"  {a['type']}: {a['label']} (target={a['target']})")
    if not _ok:
        failures.append(f"{_name}: expected {sorted(_must)} actions, "
                        f"got {sorted(_types)}")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)
print("\nALL PASS")
