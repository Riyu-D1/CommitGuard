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

# Finance/ops scenarios — 3 flagged, 3 clean (exact categories).
FINANCE_DEMO = {
    "fin_spend_approval": ["SPEND_OVER_LIMIT"],
    "fin_vendor_bank": ["NEW_VENDOR_BANK_CHANGE"],
    "fin_offcycle_unpaid": ["PAYMENT_OFF_CYCLE", "UNAPPROVED_PAYMENT"],
    "fin_within_limit": [],
    "fin_payment_run": [],
    "fin_chase_receivable": [],
}

EXPECTED = {**BASELINE, **SLACK_DEMO, **FINANCE_DEMO}

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

# darsh/finance-brain regression: 'pay ... invoice £12k' must tier-flag.
expect("rule_pay_invoice_spend",
       "I will pay the AWS invoice £12k today",
       "slack_message", must_have={"SPEND_OVER_LIMIT"})

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
    ("onboarding_spend_tiers", "who approves spend over £5k?", True),
    ("onboarding_due_month", "what's due out this month?", True),
    ("onboarding_runway", "what's our runway?", True),
    ("onboarding_overdue", "which invoices are overdue?", True),
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

# darsh/fin-check: spend-approval questions must answer with the tier model.
# The flat '£5k -> CFO' note hid the team-lead band and the CFO+CEO exec band.
for _name, _q, _need in [
    ("ask_spend_exec", "can I approve a £30,000 purchase?",
     ("Darsh", "Riyansh")),
    ("ask_spend_teamlead", "do I need approval to buy a £3,000 laptop?",
     ("Pranali",)),
    ("ask_headline_tiers", "what are the rules?", ("Darsh + Riyansh",)),
]:
    _r = rules.explain_policy(_q, main.COMPANY_BRAIN)
    _tier_ok2 = _r["matched"] and all(s in _r["answer"] for s in _need)
    print(f"\n=== {_name}: {'PASS' if _tier_ok2 else 'FAIL'}")
    print(f"  A: {_r['answer']}")
    if not _tier_ok2:
        failures.append(f"{_name}: answer missing {_need}: {_r['answer']}")

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

# darsh/finance-brain: unit tests — the amount parser and approval tiers.
_unit_ok = True
for _t, _want in [
    ("£12k", [12000]), ("£1.2m", [1200000]), ("£12,000", [12000]),
    ("£500", [500]), ("£6,800", [6800]), ("12,000", [12000]),
    ("2,500 gbp", [2500]), ("£48k/yr", [48000]), ("£4.5k", [4500]),
    ("INV-1043", []), ("Thursday 3pm", []), ("Net-30", []),
]:
    _got = sorted(v for _m, v in rules.gbp_amounts(_t))
    if _got != sorted(_want):
        _unit_ok = False
        failures.append(f"unit_parser {_t!r}: expected {_want}, got {_got}")
print(f"\n=== unit_amount_parser: {'PASS' if _unit_ok else 'FAIL'}")

_tier_ok = True
for _amt, _want_tier, _want_names in [
    (500, "self", ["self"]),
    (3000, "team_lead", ["Pranali"]),
    (12000, "cfo", ["Darsh"]),
    (60000, "exec", ["Darsh", "Riyansh"]),
]:
    _tier = rules.spend_tier(_amt, main.COMPANY_BRAIN)
    _got = (_tier["tier"], _tier["approvers"]) if _tier else (None, None)
    if _got != (_want_tier, _want_names):
        _tier_ok = False
        failures.append(f"unit_tier {_amt}: expected "
                        f"{(_want_tier, _want_names)}, got {_got}")
print(f"=== unit_approval_tiers: {'PASS' if _tier_ok else 'FAIL'}")

# darsh/finance-brain: plan_actions on the finance violations.
for _name, _key, _must, _target_type, _want_target in [
    ("actions_fin_spend", "fin_spend_approval",
     {"REQUEST_APPROVAL"}, "REQUEST_APPROVAL",
     main.COMPANY_BRAIN["people"]["cfo"]),
    ("actions_fin_unpaid", "fin_offcycle_unpaid",
     {"HOLD_PAYMENT", "REQUEST_APPROVAL"}, "HOLD_PAYMENT", "INV-1043"),
    ("actions_fin_bank", "fin_vendor_bank",
     {"HOLD_PAYMENT", "ESCALATE", "VERIFY_VENDOR"}, "ESCALATE",
     main.COMPANY_BRAIN["people"]["cfo"]),
]:
    _sc = main.SCENARIOS[_key]
    _out = main.verify_context(main.VerifyRequest(
        text=_sc["text"], context_type=_sc["context_type"]))
    _plan = actions.plan_actions(_out, main.COMPANY_BRAIN)
    _types = {a["type"] for a in _plan}
    _ok = _must <= _types and any(
        a["type"] == _target_type and a["target"] == _want_target
        for a in _plan)
    print(f"\n=== {_name}: {'PASS' if _ok else 'FAIL'}")
    for a in _plan:
        print(f"  {a['type']}: {a['label']} (target={a['target']})")
    if not _ok:
        failures.append(f"{_name}: expected {sorted(_must)} with "
                        f"{_target_type}->{_want_target}, got {sorted(_types)}")

# riyansh/chaser: receivables ageing + chase drafting. Pure-read cases run on
# the live brain; writes go to a temp copy so company_brain.json is untouched.
import chaser  # noqa: E402
from datetime import date  # noqa: E402

_today = date.today()
_rep = chaser.ageing(main.COMPANY_BRAIN, today=_today)
_ch_ok = (_rep["open_count"] >= 4
          and all(i["bucket"] in chaser.BUCKETS for i in _rep["items"])
          and _rep["total_outstanding_gbp"] >= _rep["overdue_gbp"]
          and all(i["days_overdue"] >= 0 for i in _rep["items"]))
print(f"\n=== chaser_ageing: {'PASS' if _ch_ok else 'FAIL'}")
print(f"  outstanding=£{_rep['total_outstanding_gbp']:,} "
      f"overdue=£{_rep['overdue_gbp']:,} buckets="
      + json.dumps({k: v['count'] for k, v in _rep['buckets'].items()}))
if not _ch_ok:
    failures.append("chaser_ageing: bad ageing totals/buckets")

_d = chaser.draft_chase(main.COMPANY_BRAIN, "INV-1048", feed_items=[])
_d_ok = (not _d.get("error") and _d.get("draft_only") is True
         and _d.get("subject") and _d.get("body")
         and "INV-1048" in json.dumps(_d)
         and any("due_date" in c for c in _d["cites"])
         and _d["tone"] in chaser.TONES)
print(f"\n=== chaser_draft: {'PASS' if _d_ok else 'FAIL'} "
      f"(engine={_d.get('engine')}, tone={_d.get('tone')})")
print(f"  subject: {_d.get('subject')}")
if not _d_ok:
    failures.append(f"chaser_draft: {_d.get('error') or 'missing fields'}")

_dd = chaser.draft_chase(main.COMPANY_BRAIN, "Acme", feed_items=[])
_acme_ok = (_dd.get("invoice_id") == "INV-1041"          # most overdue Acme
            and _dd.get("tone") == "final_notice"
            and _dd.get("escalate_to")
            == main.COMPANY_BRAIN["people"]["cfo"])
print(f"\n=== chaser_tone_ladder: {'PASS' if _acme_ok else 'FAIL'}")
if not _acme_ok:
    failures.append("chaser_tone_ladder: expected final_notice + CFO "
                    f"escalation, got {_dd.get('tone')}")

_ask_chase = main._ask_brain("who owes us money")
_ask_ok = _ask_chase.get("matched") and _ask_chase.get("answer") \
    and any(s["brain_key"] == "finance.invoices"
            for s in _ask_chase.get("sources", []))
print(f"\n=== chaser_ask: {'PASS' if _ask_ok else 'FAIL'}")
print(f"  A: {_ask_chase.get('answer', '')[:110]}")
if not _ask_ok:
    failures.append("chaser_ask: receivables question didn't hit chaser")

# paid/promise detection + chase_log persistence on a temp brain copy.
_real_brain3 = (Path(main.BASE) / "company_brain.json").read_text()
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as _tf:
    _tf.write(_real_brain3)
    _tmp_brain3 = _tf.name
try:
    _b3 = json.loads(Path(_tmp_brain3).read_text())
    _u1 = chaser.record_signal(_b3, "Globex paid INV-1048 — wire landed",
                               brain_path=_tmp_brain3)
    _b3r = json.loads(Path(_tmp_brain3).read_text())
    _g = next(i for i in _b3r["finance"]["invoices"] if i["id"] == "INV-1048")
    _entry = chaser.log_chase("INV-1049", brain_path=_tmp_brain3)
    _b4 = json.loads(Path(_tmp_brain3).read_text())
    _ini = next(i for i in _b4["finance"]["invoices"] if i["id"] == "INV-1049")
    _sig_ok = (_g["status"] == "paid" and _g.get("chase_paid_from") == "overdue"
               and any(u["kind"] == "paid" for u in _u1)
               and any(e["kind"] == "chase" for e in _ini["chase_log"])
               and chaser.record_signal(
                   _b4, "Initech still hasn't paid INV-1049",
                   brain_path=_tmp_brain3) == []
               and (Path(main.BASE) / "company_brain.json").read_text()
               == _real_brain3)
finally:
    os.unlink(_tmp_brain3)
print(f"\n=== chaser_signals: {'PASS' if _sig_ok else 'FAIL'}")
if not _sig_ok:
    failures.append("chaser_signals: paid/promise/log persistence failed")

# CHASE_INVOICE hand on a message naming an open receivable.
_out_ch = main.verify_context(main.VerifyRequest(
    text="Globex still hasn't paid INV-1048", context_type="slack_message"))
_chase_act = [a for a in _out_ch["actions"] if a["type"] == "CHASE_INVOICE"
              and a["target"] == "INV-1048"]
print(f"\n=== chaser_action: {'PASS' if _chase_act else 'FAIL'}")
for a in _out_ch["actions"]:
    print(f"  {a['type']}: {a['label']} (target={a['target']})")
if not _chase_act:
    failures.append("chaser_action: no CHASE_INVOICE planned for a named "
                    "overdue receivable")

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)
print("\nALL PASS")
