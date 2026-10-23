"""CommitGuard deterministic rules engine.

Every outgoing payload is checked against company_brain.json with plain,
auditable logic. Each violation carries an `evidence` block pointing at the
exact brain key that fired it, so nothing is ever "the model said so".
"""

import re
from typing import Any

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _v(category, severity, issue, correction, evidence, span=None, fix=None):
    v = {
        "category": category,
        "severity": severity,
        "issue": issue,
        "correction": correction,
        "evidence": evidence,
        "suggested_rewrite": None,
    }
    if span:
        v["span"] = span
    if fix:
        v["fix"] = fix
    return v


def _parse_net_days(value: str):
    m = re.search(r"(\d+)", str(value))
    return int(m.group(1)) if m else None


def check_payment_terms(text: str, brain: dict) -> list:
    rules = brain.get("financial_rules", {})
    max_days = _parse_net_days(rules.get("max_payment_terms", "Net-30"))
    if max_days is None:
        return []
    out = []
    for m in re.finditer(r"(?i)\bnet[\s-]?(\d+)\b", text):
        offered = int(m.group(1))
        if offered > max_days:
            out.append(_v(
                "FINANCIAL_POLICY", "HIGH",
                f"Net-{offered} payment terms exceed the CFO limit of Net-{max_days}.",
                f"Offer Net-{max_days} terms, or require 50% upfront for extended terms.",
                {"brain_key": "financial_rules.max_payment_terms",
                 "expected": f"Net-{max_days}", "found": f"Net-{offered}"},
                span={"text": m.group(0), "start": m.start(), "end": m.end()},
                fix=f"Net-{max_days}",
            ))
    return out


def check_discount_cap(text: str, brain: dict) -> list:
    rules = brain.get("financial_rules", {})
    cap = rules.get("max_unapproved_discount_percent")
    if cap is None:
        return []
    out = []
    patterns = [
        r"(\d+(?:\.\d+)?)\s?%\s?discount",
        r"discount\s+of\s+(\d+(?:\.\d+)?)\s?%",
        r"(\d+(?:\.\d+)?)\s?percent\s+discount",
        r"(\d+(?:\.\d+)?)\s?%\s+off\b",
    ]
    seen = set()
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            pct = float(m.group(1))
            if pct > cap and pct not in seen:
                seen.add(pct)
                out.append(_v(
                    "MARGIN_BREACH", "HIGH",
                    f"{pct:g}% discount exceeds the {cap:g}% unapproved cap.",
                    f"Cap the discount at {cap:g}% or get CFO sign-off in "
                    f"{brain.get('people', {}).get('finance_approval_channel', '#finance-approvals')}.",
                    {"brain_key": "financial_rules.max_unapproved_discount_percent",
                     "expected": f"<= {cap}%", "found": f"{pct:g}%"},
                    span={"text": m.group(0), "start": m.start(), "end": m.end()},
                    fix=m.group(0).replace(m.group(1), str(int(cap)), 1),
                ))
    return out


def check_treasury_lock(text: str, brain: dict) -> list:
    rules = brain.get("financial_rules", {})
    if "treasury_lock" not in rules:
        return []
    if re.search(r"(?i)\b(quarterly\s+(billing|invoic\w+)|bill(ed|ing)?\s+quarterly|pay\s+quarterly)\b", text):
        m = re.search(r"(?i)\b(quarterly\s+(billing|invoic\w+)|bill(ed|ing)?\s+quarterly|pay\s+quarterly)\b", text)
        return [_v(
            "TREASURY_LOCK", "HIGH",
            "Quarterly billing is disabled for cash runway optimization.",
            "Offer monthly billing with 50% upfront instead.",
            {"brain_key": "financial_rules.treasury_lock",
             "expected": "monthly / 50% upfront", "found": m.group(0)},
            span={"text": m.group(0), "start": m.start(), "end": m.end()},
            fix="monthly billing with 50% upfront",
        )]
    return []


def _find_vendor(text: str, brain: dict):
    for c in brain.get("signed_contracts", []):
        name = c["vendor_name"]
        first_word = name.split()[0]
        if re.search(rf"(?i)\b{re.escape(first_word)}\b", text) or \
           re.search(rf"(?i)\b{re.escape(name)}\b", text):
            return c
    return None


_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b")


def _norm_iban(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


def check_bank_details(text: str, brain: dict) -> list:
    contract = _find_vendor(text, brain)
    if not contract:
        return []
    ibans = _IBAN_RE.findall(text)
    contract_iban = _norm_iban(contract["bank_iban"])
    out = []
    for ib in ibans:
        if _norm_iban(ib) != contract_iban:
            out.append(_v(
                "PAYMENT_REDIRECTION", "CRITICAL",
                f"Bank details for {contract['vendor_name']} do not match the signed contract. "
                "This is the signature of invoice/mandate fraud.",
                "STOP. Do not pay. Verify with the vendor over a known phone number, "
                "then escalate to the CFO.",
                {"brain_key": f"signed_contracts[{contract['vendor_name']}].bank_iban",
                 "expected": contract["bank_iban"], "found": ib},
                span={"text": ib},
            ))
    if not ibans and re.search(r"(?i)(new|updated|changed)\s+(bank|payment|account)\s+(details|account|info)", text):
        out.append(_v(
            "PAYMENT_REDIRECTION", "HIGH",
            f"Message requests bank-detail changes for {contract['vendor_name']}.",
            "Any bank-detail change must be verified out-of-band before payment.",
            {"brain_key": f"signed_contracts[{contract['vendor_name']}].bank_iban",
             "expected": contract["bank_iban"], "found": "change requested"},
        ))
    return out


def _money_amounts(text: str):
    for m in re.finditer(r"[£$€]\s?([\d,]+(?:\.\d{2})?)", text):
        yield m, float(m.group(1).replace(",", ""))
    for m in re.finditer(r"\b([\d,]+(?:\.\d{2})?)\s?(?:gbp|pounds|usd|eur)\b", text, re.I):
        yield m, float(m.group(1).replace(",", ""))


def check_amounts_vs_contract(text: str, brain: dict) -> list:
    contract = _find_vendor(text, brain)
    if not contract:
        return []
    out = []
    for m in re.finditer(r"[£$€]?\s?(\d+)\s?(?:/|per)\s?h(?:ou)?r", text, re.I):
        rate = int(m.group(1))
        if rate > contract["hourly_rate_gbp"]:
            out.append(_v(
                "CONTRACT_OVERAGE", "HIGH",
                f"£{rate}/hr exceeds the contracted rate of £{contract['hourly_rate_gbp']}/hr "
                f"for {contract['vendor_name']}.",
                f"Reject the rate uplift; contracted rate is £{contract['hourly_rate_gbp']}/hr.",
                {"brain_key": f"signed_contracts[{contract['vendor_name']}].hourly_rate_gbp",
                 "expected": contract["hourly_rate_gbp"], "found": rate},
                span={"text": m.group(0)},
            ))
    retainer = contract["approved_monthly_retainer_gbp"]
    for m, amt in _money_amounts(text):
        if amt > retainer * 1.2 and amt != float(contract["hourly_rate_gbp"]):
            out.append(_v(
                "CONTRACT_OVERAGE", "HIGH",
                f"£{amt:,.0f} exceeds the approved monthly retainer of £{retainer:,.0f} "
                f"for {contract['vendor_name']}.",
                "Hold payment and request a credit note or PO reference for the variance.",
                {"brain_key": f"signed_contracts[{contract['vendor_name']}].approved_monthly_retainer_gbp",
                 "expected": retainer, "found": amt},
                span={"text": m.group(0)},
            ))
            break
    return out


def check_large_commitment(text: str, brain: dict) -> list:
    rules = brain.get("financial_rules", {})
    threshold = rules.get("cfo_approval_required_over_gbp")
    if threshold is None or _find_vendor(text, brain):
        return []
    for _m, amt in _money_amounts(text):
        if amt >= threshold:
            return [_v(
                "APPROVAL_REQUIRED", "MEDIUM",
                f"£{amt:,.0f} commitment requires CFO approval (>{'£'}{threshold:,}).",
                f"Route to {brain.get('people', {}).get('cfo', 'the CFO')} before sending.",
                {"brain_key": "financial_rules.cfo_approval_required_over_gbp",
                 "expected": f"<= £{threshold:,} unapproved", "found": amt},
            )]
    return []


_CLAIM_WORDS = re.compile(
    r"(?i)\b(is live|now live|shipped|deployed|released|launched|rolled out|complete|"
    r"completed|certified|done|fixed|resolved|available now|ga\b|generally available)\b")
_NOT_DONE = re.compile(r"(?i)(in audit|in progress|in development|expected|review|"
                       r"open|planned|no committed|not started|pending)")


def check_feature_claims(text: str, brain: dict) -> list:
    out = []
    if not _CLAIM_WORDS.search(text):
        return out
    for item in brain.get("engineering_status", []):
        feature = item["feature"]
        words = [w for w in re.split(r"[\s/]+", feature) if len(w) > 2]
        hits = sum(1 for w in words if re.search(rf"(?i)\b{re.escape(w)}\b", text))
        if hits < max(1, len(words) // 2):
            continue
        if _NOT_DONE.search(item["status"]):
            out.append(_v(
                "PROMISE_BREACH", "HIGH",
                f"You claim '{feature}' is done, but the brain says: {item['status']}.",
                "Rewrite to reflect the real status or get engineering sign-off.",
                {"brain_key": f"engineering_status[{feature}].status",
                 "expected": item["status"], "found": "claimed complete/live"},
            ))
    return out


def check_refund_credits(text: str, brain: dict) -> list:
    rules = brain.get("financial_rules", {})
    cap = rules.get("refund_or_credit_cap_gbp")
    if cap is None:
        return []
    if re.search(r"(?i)\b(full refund|refund|credit note|compensation|service credit)\b", text):
        for _m, amt in _money_amounts(text):
            if amt > cap:
                return [_v(
                    "FINANCIAL_POLICY", "MEDIUM",
                    f"£{amt:,.0f} refund/credit exceeds the £{cap} unapproved cap.",
                    f"Get approval in {brain.get('people', {}).get('finance_approval_channel', '#finance-approvals')}.",
                    {"brain_key": "financial_rules.refund_or_credit_cap_gbp",
                     "expected": f"<= £{cap}", "found": amt},
                )]
    return []


ALL_CHECKS = [
    check_payment_terms,
    check_discount_cap,
    check_treasury_lock,
    check_bank_details,
    check_amounts_vs_contract,
    check_large_commitment,
    check_feature_claims,
    check_refund_credits,
]


def run_rules(text: str, brain: dict) -> list:
    violations = []
    for check in ALL_CHECKS:
        violations.extend(check(text, brain))
    return violations


def risk_level(violations: list) -> str:
    if not violations:
        return "LOW"
    top = max(SEVERITY_ORDER.get(v["severity"], 0) for v in violations)
    return "HIGH" if top >= SEVERITY_ORDER["HIGH"] else ("MEDIUM" if top == 1 else "LOW")


def apply_fixes(text: str, violations: list) -> str:
    out = text
    for v in sorted(violations, key=lambda x: x.get("span", {}).get("start", 0), reverse=True):
        span, fix = v.get("span"), v.get("fix")
        if span and fix and span.get("start") is not None:
            out = out[:span["start"]] + fix + out[span["end"]:]
    return out
