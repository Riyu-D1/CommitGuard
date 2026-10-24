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

# riyansh/sync-audit: TribalSync decisions + AuditTrace invoices.
TRIBAL_DEMO = {
    "tribal_decision_terms": ["FINANCIAL_POLICY"],
    "tribal_decision_discount": [],
    "tribal_decision_retainer": [],
    "tribal_nondecision": ["FINANCIAL_POLICY"],
}
AUDIT_DEMO = {
    "audit_inv_over_contract": ["INVOICE_OVER_CONTRACT"],
    "audit_inv_iban_fraud": ["PAYMENT_REDIRECTION"],
    "audit_inv_sort_code": ["BANK_DETAILS_MISMATCH"],
    "audit_inv_hidden_clause": ["HIDDEN_CLAUSE"],
    "audit_inv_duplicate": ["DUPLICATE_INVOICE"],
    "audit_inv_clean": [],
}
EXPECTED = {**BASELINE, **SLACK_DEMO, **FINANCE_DEMO,
            **TRIBAL_DEMO, **AUDIT_DEMO}

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
    (3000, "team_lead", ["Nadia Hussain"]),
    (12000, "cfo", ["Amara Osei"]),
    (60000, "exec", ["Amara Osei", "Tom Ellery"]),
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

# ==========================================================================
# riyansh/sync-audit: TribalSync decision -> proposal -> apply flow,
# AuditTrace invoice checks, and the brain_store patch/changelog writer.
# Everything writes to temp files only — the real brain and backend/
# brain_proposals.json / brain_changelog.jsonl must never change.
import shutil  # noqa: E402

import audit_trace  # noqa: E402
import brain_store  # noqa: E402
import tribal_sync  # noqa: E402


def _bs_get(key, brain_path=None):
    """Resolve a brain key via brain_store.get_path — tolerant of either
    call shape while the module settles: (key, brain_path=...) reading a
    brain file, or (brain_dict, key) resolving an in-memory brain."""
    try:
        return brain_store.get_path(key, brain_path=brain_path) \
            if brain_path else brain_store.get_path(key)
    except TypeError:
        brain = json.loads(Path(brain_path).read_text()) if brain_path \
            else main.COMPANY_BRAIN
        return brain_store.get_path(brain, key)


def _bs_changelog(path):
    """brain_store.changelog(path=...) -> list (limit is optional in the
    contract; fall back to an explicit one if the signature requires it)."""
    try:
        return brain_store.changelog(path=path) or []
    except TypeError:
        return brain_store.changelog(100, path=path) or []


# TribalSync detection: a confident decision resolves to
# (brain_key, old -> new); a hedged question must detect nothing.
for _name, _text, _key, _want_new in [
    ("tribal_detect_terms",
     "CFO here: from today, payment terms are Net-45 for all suppliers.",
     "financial_rules.max_payment_terms", "Net-45"),
    ("tribal_detect_discount",
     "New policy going forward: discounts over 15% need sign-off from Amara.",
     "financial_rules.max_unapproved_discount_percent", 15),
    ("tribal_detect_retainer",
     "We've decided — effective this month CloudScale Ltd's retainer "
     "moves to £5,500/mo.",
     "signed_contracts[CloudScale Ltd].approved_monthly_retainer_gbp", 5500),
]:
    _det = tribal_sync.detect_decision(_text, main.COMPANY_BRAIN)
    _old = _bs_get(_key)
    _ok = (_det is not None and _det.get("brain_key") == _key
           and _det.get("new") == _want_new and _det.get("old") == _old)
    print(f"\n=== {_name}: {'PASS' if _ok else 'FAIL'}")
    if _det:
        print(f"  {_det.get('brain_key')}: {_det.get('old')!r} -> "
              f"{_det.get('new')!r} (confidence={_det.get('confidence')}, "
              f"detector={_det.get('detector')!r}, cue={_det.get('cue')!r})")
    else:
        print("  (no decision detected)")
    if not _ok:
        failures.append(f"{_name}: expected {_key} {_old!r} -> {_want_new!r}, "
                        f"got {_det}")

_det = tribal_sync.detect_decision(
    "should we move to Net-45 for the Globex renewal?", main.COMPANY_BRAIN)
_ok = _det is None
print(f"\n=== tribal_detect_hedge: {'PASS' if _ok else 'FAIL'}")
if _det:
    print(f"  unexpected decision: {_det}")
if not _ok:
    failures.append("tribal_detect_hedge: hedged question must not produce "
                    f"a decision, got {_det}")

# Apply flow flips a verdict — ALL ON TEMP FILES (same pattern as the
# learned-rules block). A Net-45 draft is flagged before the proposal is
# applied and clean after, the changelog records Net-30 -> Net-45, and a
# rejected proposal can never be applied.
_real_brain3 = (Path(main.BASE) / "company_brain.json").read_text()
_props_existed = (Path(main.BASE) / "brain_proposals.json").exists()
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as _tf:
    _tf.write(_real_brain3)
    _tmp_brain3 = _tf.name
_tmp_dir3 = tempfile.mkdtemp(prefix="cg_tribal_")
_tmp_props = str(Path(_tmp_dir3) / "brain_proposals.json")
_tmp_chg = str(Path(_tmp_dir3) / "brain_changelog.jsonl")
_draft = "we can offer Net-45 terms to close this"
# apply/reject audit via actions.audit -> keep it off the real audit_log.
_real_audit_path = actions.AUDIT_PATH
actions.AUDIT_PATH = Path(_tmp_dir3) / "audit_log.jsonl"

try:
    _err = None
    _before = _after = []
    _res = {}
    _entry = {}
    _patched_terms = None
    try:
        _before = rules.run_rules(
            _draft, json.loads(Path(_tmp_brain3).read_text()), "slack_message")
        _prop = tribal_sync.build_proposal(
            "CFO here: from today, payment terms are Net-45 for all "
            "suppliers.", main.COMPANY_BRAIN,
            meta={"feed_id": 1, "author": "U0", "source": "manual"},
            probes=[], proposals_path=_tmp_props)
        if _prop is None:
            raise ValueError("build_proposal returned None for a clear "
                             "CFO decision")
        _res = tribal_sync.apply_proposal(
            _prop["id"], decided_by="smoke", proposals_path=_tmp_props,
            brain_path=_tmp_brain3, changelog_path=_tmp_chg)
        _after = rules.run_rules(
            _draft, json.loads(Path(_tmp_brain3).read_text()), "slack_message")
        _log = _bs_changelog(_tmp_chg)
        _entry = _log[0] if _log else {}
        _patched_terms = _bs_get("financial_rules.max_payment_terms",
                                 _tmp_brain3)
    except Exception as _e:
        _err = _e
    _flip_ok = (_err is None
                and "FINANCIAL_POLICY" in {v["category"] for v in _before}
                and "FINANCIAL_POLICY" not in {v["category"] for v in _after}
                and bool(_res.get("applied"))
                and _entry.get("old") == "Net-30"
                and _entry.get("new") == "Net-45"
                and _patched_terms == "Net-45")
    print(f"\n=== tribal_apply_flip: {'PASS' if _flip_ok else 'FAIL'}")
    print(f"  before apply: {sorted(v['category'] for v in _before)}")
    print(f"  after apply:  {sorted(v['category'] for v in _after)}")
    print(f"  applied={_res.get('applied')}, changelog[0]: "
          f"{_entry.get('old')!r} -> {_entry.get('new')!r}, "
          f"temp brain max_payment_terms={_patched_terms!r}")
    if _err:
        print(f"  raised {_err!r}")
    if not _flip_ok:
        failures.append(
            "tribal_apply_flip: expected FINANCIAL_POLICY -> clean on the "
            "temp brain, applied=True, changelog Net-30->Net-45"
            + (f" (raised {_err!r})" if _err else ""))

    _err = None
    _status = None
    _raised = False
    try:
        _prop2 = tribal_sync.build_proposal(
            "New policy going forward: discounts over 15% need sign-off "
            "from Amara.", json.loads(Path(_tmp_brain3).read_text()),
            meta={"feed_id": 2, "author": "U0", "source": "manual"},
            probes=[], proposals_path=_tmp_props)
        if _prop2 is None:
            raise ValueError("build_proposal returned None for the "
                             "discount decision")
        _rej = tribal_sync.reject_proposal(
            _prop2["id"], decided_by="smoke", proposals_path=_tmp_props)
        _status = _rej.get("status") if isinstance(_rej, dict) else None
        if _status is None and Path(_tmp_props).exists():
            _status = next((p.get("status") for p in
                            json.loads(Path(_tmp_props).read_text())
                            if p.get("id") == _prop2["id"]), None)
        try:
            tribal_sync.apply_proposal(
                _prop2["id"], decided_by="smoke", proposals_path=_tmp_props,
                brain_path=_tmp_brain3, changelog_path=_tmp_chg)
        except ValueError:
            _raised = True
    except Exception as _e:
        _err = _e
    _reject_ok = _err is None and _status == "rejected" and _raised
    print(f"\n=== tribal_reject: {'PASS' if _reject_ok else 'FAIL'}")
    print(f"  status={_status!r}, apply_on_rejected_raised={_raised}")
    if _err:
        print(f"  raised {_err!r}")
    if not _reject_ok:
        failures.append(
            "tribal_reject: rejected proposal must keep status 'rejected' "
            f"and applying it must raise ValueError (status={_status!r}, "
            f"raised={_raised}" + (f", err={_err!r})" if _err else ")"))

    _untouched_ok = (
        (Path(main.BASE) / "company_brain.json").read_text() == _real_brain3
        and (Path(main.BASE) / "brain_proposals.json").exists()
        == _props_existed)
    print(f"\n=== tribal_brain_untouched: "
          f"{'PASS' if _untouched_ok else 'FAIL'}")
    if not _untouched_ok:
        failures.append("tribal_brain_untouched: real company_brain.json "
                        "changed or backend/brain_proposals.json appeared")
finally:
    actions.AUDIT_PATH = _real_audit_path
    try:
        os.unlink(_tmp_brain3)
    except OSError:
        pass
    shutil.rmtree(_tmp_dir3, ignore_errors=True)

# riyansh/sync-audit: AuditTrace invoice checks come through the live
# verify path (main._verify appends audit_trace.audit_violations and dedupes
# against rule hits citing the same brain_key).
expect("audit_over_contract",
       "INVOICE CS-1201\nCloudScale Ltd\nMonthly retainer: £5,400\n"
       "Please pay to IBAN GB29REVOLUT12345689",
       "incoming_invoice", must_have={"INVOICE_OVER_CONTRACT"},
       must_not_have={"PAYMENT_REDIRECTION"})
expect("audit_iban_fraud",
       "INVOICE CS-1202\nCloudScale Ltd — £5,000 due\n"
       "Updated account: IBAN GB22BARC99887766554",
       "incoming_invoice", must_have={"PAYMENT_REDIRECTION"},
       must_not_have={"BANK_DETAILS_MISMATCH"})
expect("audit_sort_code",
       "INVOICE PPD-441\nPinnacle Print & Design — services £1,800\n"
       "Remit to sort code 40-11-22, account number 99887766",
       "incoming_invoice", must_have={"BANK_DETAILS_MISMATCH"})
expect("audit_hidden_clause",
       "INVOICE PPD-442\nPinnacle Print & Design — £1,800\n"
       "Includes 8% CPI uplift from this billing cycle",
       "incoming_invoice", must_have={"HIDDEN_CLAUSE"})
expect("audit_duplicate",
       "INVOICE INV-1039\nAmazon Web Services\nCloud hosting — £1,140\n"
       "Please pay to IBAN GB99AWSX12345678",
       "incoming_invoice", must_have={"DUPLICATE_INVOICE"})
expect("audit_slack_overage",
       "heads up — CloudScale Ltd invoiced £5,400 for this month's retainer",
       "slack_message", must_have={"INVOICE_OVER_CONTRACT"})

out = expect("audit_clean",
             "INVOICE PPD-440\nPinnacle Print & Design — £1,800 monthly "
             "retainer\nIBAN GB33LOYD22334455\nPayment terms: Net-30",
             "incoming_invoice")
if out["status"] != "CLEAN":
    failures.append("audit_clean: status must be CLEAN")

# audit_trace.parse_invoice — every extractable field on one dense invoice.
_pi_text = ("INVOICE CS-1299\nCloudScale Ltd — monthly retainer £5,000\n"
            "Pay to IBAN GB29REVOLUT12345689\n"
            "Sort code 40-11-22, account number 99887766\n"
            "Payment terms: Net-30\n"
            "Includes 8% CPI uplift from this billing cycle")
_pi_err = None
try:
    try:
        _inv = audit_trace.parse_invoice(_pi_text, main.COMPANY_BRAIN)
    except TypeError:
        _inv = audit_trace.parse_invoice(_pi_text)
except Exception as _e:
    _inv, _pi_err = {}, _e


def _pi(d, *names):
    """First populated value among aliased field names."""
    for n in names:
        v = d.get(n) if isinstance(d, dict) else None
        if v not in (None, ""):
            return v
    return None


_pi_vendor = _pi(_inv, "vendor", "vendor_name", "supplier", "contract")
_pi_no = _pi(_inv, "invoice_no", "invoice_number", "invoice_id", "invoice",
             "ref", "number")
_pi_iban = _pi(_inv, "iban", "bank_iban")
_pi_sort = _pi(_inv, "sort_code", "sortcode")
_pi_acct = _pi(_inv, "account_no", "account_number", "account")
_pi_terms = _pi(_inv, "terms", "payment_terms", "net_terms")
_pi_clause = _pi(_inv, "clause", "hidden_clause", "uplift", "clause_text")
_pi_checks = {
    "vendor": "cloudscale" in str(_pi_vendor).lower(),
    "invoice_no": "cs1299" in re.sub(r"[\s-]", "", str(_pi_no)).lower(),
    "iban": "GB29REVOLUT12345689"
            in str(_pi_iban).replace(" ", "").upper(),
    "sort_code": "401122" in re.sub(r"\D", "", str(_pi_sort)),
    "account_no": "99887766" in re.sub(r"\D", "", str(_pi_acct)),
    "terms": "30" in str(_pi_terms),
    "clause": bool(_pi_clause)
              and any(w in str(_pi_clause).lower()
                      for w in ("cpi", "uplift", "8%")),
}
_pi_ok = _pi_err is None and all(_pi_checks.values())
print(f"\n=== audit_parse_invoice: {'PASS' if _pi_ok else 'FAIL'}")
for _k, _v_ in (_inv or {}).items():
    print(f"  {_k}: {_v_!r}")
for _k, _v_ in _pi_checks.items():
    if not _v_:
        print(f"  missing/wrong field: {_k}")
if _pi_err:
    print(f"  raised {_pi_err!r}")
if not _pi_ok:
    failures.append(
        "audit_parse_invoice: unpopulated/wrong fields "
        f"{sorted(k for k, ok in _pi_checks.items() if not ok)} in {_inv!r}"
        + (f" (raised {_pi_err!r})" if _pi_err else ""))

# riyansh/sync-audit: brain_store unit — get_path resolves indexed keys,
# apply_patch enforces expected_old (optimistic concurrency) and is
# idempotent, revert_all restores the temp brain and empties the changelog.
_real_brain5 = (Path(main.BASE) / "company_brain.json").read_text()
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as _tf:
    _tf.write(_real_brain5)
    _tmp_brain5 = _tf.name
_tmp_dir5 = tempfile.mkdtemp(prefix="cg_brainstore_")
_tmp_chg5 = str(Path(_tmp_dir5) / "brain_changelog.jsonl")

_bs_err = None
_g1 = _p1 = _p2 = _g2 = _log2 = None
_conflict = False
try:
    _g1 = _bs_get("signed_contracts[CloudScale Ltd].bank_iban", _tmp_brain5)
    _p1 = brain_store.apply_patch("financial_rules.max_payment_terms",
                                  "Net-45", meta={"expected_old": "Net-30"},
                                  brain_path=_tmp_brain5,
                                  changelog_path=_tmp_chg5)
    _p2 = brain_store.apply_patch("financial_rules.max_payment_terms",
                                  "Net-45", meta={"expected_old": "Net-45"},
                                  brain_path=_tmp_brain5,
                                  changelog_path=_tmp_chg5)
    try:
        brain_store.apply_patch("financial_rules.max_payment_terms",
                                "Net-60", meta={"expected_old": "Net-30"},
                                brain_path=_tmp_brain5,
                                changelog_path=_tmp_chg5)
    except ValueError:
        _conflict = True
    brain_store.revert_all(brain_path=_tmp_brain5,
                           changelog_path=_tmp_chg5)
    _g2 = _bs_get("financial_rules.max_payment_terms", _tmp_brain5)
    _log2 = _bs_changelog(_tmp_chg5)
except Exception as _e:
    _bs_err = _e
finally:
    try:
        os.unlink(_tmp_brain5)
    except OSError:
        pass
    shutil.rmtree(_tmp_dir5, ignore_errors=True)

_bs_ok = (_bs_err is None
          and _g1 == "GB29REVOLUT12345689"
          and isinstance(_p1, dict) and _p1.get("old") == "Net-30"
          and isinstance(_p2, dict) and _p2.get("changed") is False
          and _conflict
          and _g2 == "Net-30"
          and not _log2
          and (Path(main.BASE) / "company_brain.json").read_text()
          == _real_brain5)
print(f"\n=== brain_store_patch_revert: {'PASS' if _bs_ok else 'FAIL'}")
print(f"  get_path(bank_iban)={_g1!r}, patch1.old={(_p1 or {}).get('old')!r}, "
      f"patch2.changed={(_p2 or {}).get('changed')!r}, "
      f"stale_expected_old_raised={_conflict}, "
      f"reverted={_g2!r}, changelog_empty={not _log2}")
if _bs_err:
    print(f"  raised {_bs_err!r}")
if not _bs_ok:
    failures.append(
        "brain_store_patch_revert: expected iban resolved, patch old=Net-30, "
        "idempotent re-patch changed=False, stale expected_old -> ValueError, "
        f"revert restores Net-30 + empties changelog (iban={_g1!r}, "
        f"p1={_p1!r}, p2={_p2!r}, conflict={_conflict}, reverted={_g2!r}, "
        f"log={_log2!r}" + (f", err={_bs_err!r})" if _bs_err else ")"))

if failures:
    print("\nFAILURES:")
    for f in failures:
        print(f"  {f}")
    sys.exit(1)
print("\nALL PASS")
