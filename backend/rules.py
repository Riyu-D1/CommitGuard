"""CommitGuard deterministic rules engine.

Every outgoing payload is checked against company_brain.json with plain,
auditable logic. Each violation carries an `evidence` block pointing at the
exact brain key that fired it, so nothing is ever "the model said so".
"""

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).parent
BRAIN_PATH = BASE_DIR / "company_brain.json"

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
SEVERITY_RISK_SCORE = {"LOW": 20, "MEDIUM": 45, "HIGH": 70, "CRITICAL": 95}


def _v(category, severity, issue, correction, evidence, span=None, fix=None):
    v = {
        "category": category,
        "severity": severity,
        "risk_score": SEVERITY_RISK_SCORE.get(severity, 0),
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


_INVOICE_NO_RE = re.compile(r"\b[A-Z]{2,4}[-\s]?\d{3,}\b")
_DUP_LANG_RE = re.compile(
    r"(?i)\b(already paid|duplicate|second request|paid twice|settled last|"
    r"resending|previously paid)\b")


def check_duplicate_invoice(text: str, brain: dict) -> list:
    dup = _DUP_LANG_RE.search(text)
    if not dup:
        return []
    out = []
    seen = set()
    for m in _INVOICE_NO_RE.finditer(text):
        if m.group(0) in seen:
            continue
        seen.add(m.group(0))
        out.append(_v(
            "DUPLICATE_INVOICE", "CRITICAL",
            f"Invoice {m.group(0)} is flagged as a possible duplicate payment request.",
            "Verify against the payment ledger before approving — duplicate invoice fraud is common.",
            {"brain_key": "payment_ledger",
             "expected": "no prior payment for this invoice", "found": dup.group(0)},
            span={"text": m.group(0), "start": m.start(), "end": m.end()},
        ))
    return out


_SENDER_RE = re.compile(
    r"(?i)(?:from|reply-to):\s*(\S+@([A-Za-z0-9.-]+\.[A-Za-z]{2,}))")


def check_sender_domain(text: str, brain: dict) -> list:
    known_list = brain.get("known_sender_domains", [])
    known = {d.lower() for d in known_list}
    contract = _find_vendor(text, brain)
    out = []
    seen = set()
    for m in _SENDER_RE.finditer(text):
        email, domain = m.group(1), m.group(2).lower()
        if domain in known or domain in seen:
            continue
        seen.add(domain)
        if contract:
            out.append(_v(
                "SENDER_DOMAIN_MISMATCH", "CRITICAL",
                f"Sender domain '{domain}' claimed to be from {contract['vendor_name']} — "
                "this is a classic supplier-impersonation pattern.",
                "Verify the sender out-of-band before acting on this message.",
                {"brain_key": "known_sender_domains",
                 "expected": known_list, "found": domain},
                span={"text": email, "start": m.start(1), "end": m.end(1)},
            ))
        else:
            out.append(_v(
                "SENDER_DOMAIN_MISMATCH", "HIGH",
                f"Sender domain '{domain}' is not a known supplier domain — "
                "possible impersonation/phishing.",
                "Verify the sender out-of-band before acting on this message.",
                {"brain_key": "known_sender_domains",
                 "expected": known_list, "found": domain},
                span={"text": email, "start": m.start(1), "end": m.end(1)},
            ))
    return out


_URGENCY_RE = re.compile(
    r"(?i)\b(urgent(?:ly)?|immediately|asap|today|by eod|end of day|"
    r"time-sensitive|before close)\b")
_PAYDETAIL_RE = re.compile(
    r"(?i)\b(iban|sort code|bank details|account number|updated payment|"
    r"new account|payment details|change of bank)\b")


def check_urgent_payment_change(text: str, brain: dict) -> list:
    urgencies = list(_URGENCY_RE.finditer(text))
    if not urgencies:
        return []
    payments = list(_PAYDETAIL_RE.finditer(text))
    for u in urgencies:
        for p in payments:
            if abs(u.start() - p.start()) <= 120:
                lo, hi = min(u.start(), p.start()), max(u.end(), p.end())
                return [_v(
                    "URGENT_PAYMENT_CHANGE", "CRITICAL",
                    "Urgency combined with a payment-detail change is the #1 invoice-fraud pattern.",
                    "Never process bank-detail changes under time pressure — verify out-of-band first.",
                    {"brain_key": "financial_rules.fraud_controls",
                     "expected": "no urgency+bank-change combination",
                     "found": f"{u.group(0)} + {p.group(0)}"},
                    span={"text": text[lo:hi], "start": lo, "end": hi},
                )]
    return []


_CERT_CLAIM_TOKENS = (
    "soc 2", "iso 27001", "iso27001", "hipaa", "pci dss",
    "pci-dss", "gdpr certified", "cyber essentials",
)


def check_unverified_claims(text: str, brain: dict) -> list:
    corpus = " ".join(
        f"{i.get('feature', '')} {i.get('status', '')}"
        for i in brain.get("engineering_status", [])
    ).lower()
    out = []
    for token in _CERT_CLAIM_TOKENS:
        m = re.search(rf"(?i)\b{re.escape(token)}\b", text)
        if not m or token in corpus:
            continue  # not claimed, or covered by an engineering_status entry
        out.append(_v(
            "UNVERIFIED_CLAIM", "MEDIUM",
            f"'{m.group(0)}' is asserted but has no backing entry in the company brain.",
            "Remove the claim or add an authoritative source to the brain before sending.",
            {"brain_key": "engineering_status",
             "expected": f"a status entry covering {m.group(0)}", "found": "no entry"},
            span={"text": m.group(0), "start": m.start(), "end": m.end()},
        ))
    return out


_EXPENSE_WORDS = re.compile(
    r"(?i)\b(expens\w*|spend(?:s|ing|t)?|buy(?:ing)?|purchas\w*|"
    r"company card|corporate card|pay(?:ing)? for)\b")


def check_expense_approval(text: str, brain: dict) -> list:
    limit = brain.get("internal_policies", {}).get("expense_approval_limit_gbp")
    if limit is None or not _EXPENSE_WORDS.search(text):
        return []
    for m, amt in _money_amounts(text):
        if amt > limit:
            return [_v(
                "APPROVAL_REQUIRED", "HIGH",
                f"£{amt:,.0f} of spend needs CFO approval — over the "
                f"£{limit:,} expense limit.",
                f"Get {brain.get('people', {}).get('cfo', 'the CFO')} to "
                "approve the spend first.",
                {"brain_key": "internal_policies.expense_approval_limit_gbp",
                 "expected": f"<= £{limit:,} unapproved", "found": amt},
                span={"text": m.group(0), "start": m.start(), "end": m.end()},
            )]
    return []


_SEAT_PRICE_RE = re.compile(r"(?i)[£$€]?\s?(\d+(?:\.\d+)?)\s*(?:/|per)\s*seat")


def check_price_floor(text: str, brain: dict) -> list:
    plans = brain.get("internal_policies", {}) \
        .get("pricing_floor_gbp_per_seat", {})
    if not plans:
        return []
    out = []
    for m in _SEAT_PRICE_RE.finditer(text):
        price = float(m.group(1))
        plan = next((p for p in plans
                     if re.search(rf"(?i)\b{re.escape(p)}\b", text)), None)
        floor = plans.get(plan, min(plans.values()))
        if price < floor:
            out.append(_v(
                "PRICE_FLOOR", "HIGH",
                f"£{price:g}/seat is below the £{floor}/seat floor"
                + (f" for the {plan} plan." if plan else
                   f" (lowest plan floor is {min(plans, key=plans.get)})."),
                f"Don't quote below £{floor}/seat — reprice or get "
                "sales-lead sign-off.",
                {"brain_key": "internal_policies.pricing_floor_gbp_per_seat",
                 "expected": f">= £{floor}/seat", "found": f"£{price:g}/seat"},
                span={"text": m.group(0), "start": m.start(), "end": m.end()},
            ))
    return out


_CLIENT_LIST_RE = re.compile(r"(?i)\b(?:client|customer)s?\s+list\b")
_EXFIL_VERB_RE = re.compile(
    r"(?i)\b(send|share|export|upload|email|forward|attach|drop|paste)\b")


def check_confidential_leak(text: str, brain: dict) -> list:
    policies = brain.get("internal_policies", {})
    if "confidential_data" not in policies:
        return []
    out = []
    customers = brain.get("company", {}).get("customers", [])
    name_m = next((re.search(rf"(?i)\b{re.escape(c)}\b", text)
                   for c in customers
                   if re.search(rf"(?i)\b{re.escape(c)}\b", text)), None)
    if name_m:
        for m, _amt in _money_amounts(text):
            out.append(_v(
                "CONFIDENTIAL_LEAK", "HIGH",
                f"'{name_m.group(0)}' next to a revenue figure — customer "
                "financials don't belong in this message.",
                "Move customer figures to a private channel or strip "
                "the numbers.",
                {"brain_key": "internal_policies.confidential_data",
                 "expected": "no customer name + revenue figures in one "
                             "message",
                 "found": f"{name_m.group(0)} + {m.group(0)}"},
                span={"text": name_m.group(0),
                      "start": name_m.start(), "end": name_m.end()},
            ))
            break
    list_m = _CLIENT_LIST_RE.search(text)
    verb_m = _EXFIL_VERB_RE.search(text)
    if list_m and verb_m:
        out.append(_v(
            "CONFIDENTIAL_LEAK", "CRITICAL",
            "Sharing the client list outside the company is a data "
            "exfiltration risk.",
            "Never send the client list externally — escalate to the CFO "
            "instead.",
            {"brain_key": "internal_policies.confidential_data",
             "expected": "client list stays internal",
             "found": f"{verb_m.group(0)} + {list_m.group(0)}"},
            span={"text": list_m.group(0),
                  "start": list_m.start(), "end": list_m.end()},
        ))
    return out


# --- finance checks (Round track): spend tiers, invoice discipline, payment runs
#
# Amount parser handles £12k, £1.2m, £12,000, 12,000, 2,500 gbp, etc.
_AMOUNT_RES = [
    re.compile(r"[£$€]\s?(\d[\d,]*(?:\.\d+)?)\s*([kKmM])\b"),
    re.compile(r"[£$€]\s?(\d[\d,]*(?:\.\d+)?)\b"),
    re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s*([kKmM])\s*(?:gbp|pounds?|quid)?\b", re.I),
    re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s*(?:gbp|pounds?|quid)\b", re.I),
    re.compile(r"\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?)\b"),
]


def gbp_amounts(text: str):
    """Yield (match, float_value) for GBP-looking amounts in `text`."""
    used = []
    for pat in _AMOUNT_RES:
        for m in pat.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in used):
                continue  # overlapping a wider match already yielded
            used.append((m.start(), m.end()))
            groups = [g for g in m.groups() if g is not None]
            mult = 1
            if len(groups) > 1 and str(groups[-1]).lower() in ("k", "m"):
                mult = 1_000 if groups[-1].lower() == "k" else 1_000_000
            try:
                yield m, float(str(groups[0]).replace(",", "")) * mult
            except (ValueError, IndexError):
                continue


def spend_tier(amount: float, brain: dict):
    """Return the approval tier for `amount` with approver names resolved.

    None if the brain has no spend_approvals. 'self' tier means anyone may
    approve — callers treat it as no escalation needed.
    """
    tiers = brain.get("finance", {}).get("spend_approvals", [])
    people = brain.get("people", {})
    for t in tiers:
        limit = t.get("max_gbp")
        if limit is None or amount <= limit:
            roles = t.get("approvers", [])
            return {"tier": t.get("tier"), "approver_roles": roles,
                    "approvers": [people.get(r, r) for r in roles],
                    "max_gbp": limit}
    return None


_SPEND_INTENT_RE = re.compile(
    r"(?i)\b(approv\w*|sign\w*[ -]?off|budget\w*|spend\w*|wir(?:e|ed|ing)|"
    r"transfer\w*|pay|paying|pays|invoic\w*|bill\w*|remit\w*|settle\w*|"
    r"purchase order|pay(?:ing|s)?\s+out)\b")
_RECURRING_SUFFIX_RE = re.compile(
    r"(?i)^\s*(?:(?:/|per)\s*(?:yr|year|mo|month|annum|seat|user|licen[cs]e)|"
    r"arr|mrr|apr)\b")
_TIER_SEVERITY = {"team_lead": "MEDIUM", "cfo": "HIGH", "exec": "CRITICAL"}


def check_spend_tiers(text: str, brain: dict) -> list:
    """Spend requests must name the right approver for their tier."""
    if not _SPEND_INTENT_RE.search(text):
        return []
    best = None  # (amount, match, tier) for the largest non-recurring amount
    for m, amt in gbp_amounts(text):
        if _RECURRING_SUFFIX_RE.match(text[m.end():]):
            continue  # £48k/yr, £31k ARR, £110/seat — run-rates, not spend
        tier = spend_tier(amt, brain)
        if tier and "self" not in tier["approver_roles"] and \
                (best is None or amt > best[0]):
            best = (amt, m, tier)
    if not best:
        return []
    amt, m, tier = best
    names = " + ".join(tier["approvers"])
    cap = (f"£{tier['max_gbp']:,}" if tier["max_gbp"] is not None
           else "any amount over the top tier")
    return [_v(
        "SPEND_OVER_LIMIT", _TIER_SEVERITY.get(tier["tier"], "HIGH"),
        f"£{amt:,.0f} spend sits in the '{tier['tier']}' tier — needs "
        f"sign-off from {names}.",
        f"Route to {names} before committing the spend.",
        {"brain_key": "finance.spend_approvals",
         "expected": f"{tier['tier']} tier (up to {cap}) approved by "
                     f"{names}",
         "found": f"£{amt:,.0f}",
         "required_approvers": tier["approvers"]},
        span={"text": m.group(0), "start": m.start(), "end": m.end()},
    )]


_PAY_INTENT_RE = re.compile(
    r"(?i)\b(pay|paying|paid|settle\w*|wir(?:e|ed|ing)|transfer\w*|remit\w*|"
    r"send(?:ing|t)?|dispatch\w*|clear(?:ing)?)\b")
_APPROVAL_WORD_RE = re.compile(
    r"(?i)\b(approved|approves|approval|authorised|authorized|"
    r"sign\w*[ -]?off|cleared by)\b")


def check_unapproved_payment(text: str, brain: dict) -> list:
    """Paying a payable invoice that's still unpaid/overdue needs sign-off."""
    rules = brain.get("finance", {}).get("payment_rules", {})
    if "no_unapproved_invoice_payments" not in rules or \
            not _PAY_INTENT_RE.search(text) or _APPROVAL_WORD_RE.search(text):
        return []
    by_id = {i["id"]: i for i in brain.get("finance", {}).get("invoices", [])
             if i.get("kind") == "payable" and
             i.get("status") in ("unpaid", "overdue")}
    out = []
    seen = set()
    for m in _INVOICE_NO_RE.finditer(text):
        ref = m.group(0).replace(" ", "-")
        inv = by_id.get(ref)
        if not inv or ref in seen:
            continue
        seen.add(ref)
        out.append(_v(
            "UNAPPROVED_PAYMENT", "HIGH",
            f"{ref} ({inv['counterparty']}, £{inv['amount_gbp']:,}) is "
            f"{inv['status']} — paying it without approval breaks the "
            "payment rules.",
            f"Get sign-off in "
            f"{brain.get('people', {}).get('finance_approval_channel', '#finance-approvals')} "
            "before paying, or wait for the next payment run.",
            {"brain_key": f"finance.invoices[{ref}].status",
             "expected": "approved before payment",
             "found": inv["status"],
             "invoice_id": ref},
            span={"text": m.group(0), "start": m.start(), "end": m.end()},
        ))
    return out


_BANK_CHANGE_RE = re.compile(
    r"(?i)\b(new|updated|changed|different)\s+(bank|payment|account)\s+"
    r"(details|account|info|number)\b|\b(new|updated)\s+iban\b|"
    r"\bchanged\s+(their|our|its|the)\s+bank\b|\bnew\s+bank\s+account\b|"
    r"\bbank\s+details?\s+(have|has|been|were)?\s*(changed|updated)\b")
_VENDOR_CONTEXT_RE = re.compile(
    r"(?i)\b(vendor|supplier|invoice|account|iban|pay\w*|wir\w*|transfer\w*|"
    r"send\w*|remit\w*)\b")


def check_new_vendor_bank(text: str, brain: dict) -> list:
    """'Changed bank details' from a party with no signed contract = fraud."""
    rules = brain.get("finance", {}).get("payment_rules", {})
    if "no_payment_to_new_vendor_without_verified_bank" not in rules or \
            _find_vendor(text, brain):
        return []
    m = _BANK_CHANGE_RE.search(text)
    if not m or not _VENDOR_CONTEXT_RE.search(text):
        return []
    return [_v(
        "NEW_VENDOR_BANK_CHANGE", "CRITICAL",
        "Bank-detail change from a party with no signed contract — the "
        "classic new-vendor fraud pattern.",
        "Do not pay. Verify bank details out-of-band on a known number, "
        "then escalate to "
        f"{brain.get('people', {}).get('cfo', 'the CFO')}.",
        {"brain_key": "finance.payment_rules."
                      "no_payment_to_new_vendor_without_verified_bank",
         "expected": "verified bank details before first payment",
         "found": m.group(0)},
        span={"text": m.group(0), "start": m.start(), "end": m.end()},
    )]


_DAY_RE = re.compile(
    r"(?i)\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b")
_SCHED_WORD_RE = re.compile(
    r"(?i)\b(on|move[ds]?|moving|push(?:ing|ed)?|batch(?:ing|ed)?|schedul\w+|"
    r"delay(?:ed|ing)?|until|postpone\w*|deadline|lands?|set\s+for|shift\w*|"
    r"go(?:es)?\s+out|falls?\s+on|book\w*)\b")
_PAYMENT_WORD_RE = re.compile(
    r"(?i)\b(pay\w*|payment\w*|invoice\w*|wir\w*|transfer\w*|batch|"
    r"supplier\w*|vendor\w*|remit\w*)\b")
_DAY_NORMALISE = {"mon": "monday", "tue": "tuesday", "tues": "tuesday",
                  "wed": "wednesday", "thu": "thursday", "thur": "thursday",
                  "thurs": "thursday", "fri": "friday", "sat": "saturday",
                  "sun": "sunday"}


def check_payment_off_cycle(text: str, brain: dict) -> list:
    """Supplier payments only run on the days in payment_run_days."""
    run_days = brain.get("finance", {}).get("payment_rules", {}) \
        .get("payment_run_days", [])
    if not run_days or not _PAYMENT_WORD_RE.search(text):
        return []
    allowed = {_DAY_NORMALISE.get(d.lower()[:5], d.lower()) for d in run_days}
    for m in _DAY_RE.finditer(text):
        day = m.group(1).lower()
        if day in allowed:
            continue
        lo, hi = max(0, m.start() - 60), min(len(text), m.end() + 60)
        if not _SCHED_WORD_RE.search(text, lo, hi):
            continue
        return [_v(
            "PAYMENT_OFF_CYCLE", "MEDIUM",
            f"Payments scheduled on {m.group(1)} — payment runs only happen "
            f"on {'/'.join(run_days)}.",
            f"Hold it for the next payment run ({'/'.join(run_days)}) or get "
            "CFO sign-off for an off-cycle payment.",
            {"brain_key": "finance.payment_rules.payment_run_days",
             "expected": "/".join(run_days), "found": m.group(1)},
            span={"text": m.group(0), "start": m.start(), "end": m.end()},
        )]
    return []


def check_learned_rules(text: str, brain: dict) -> list:
    out = []
    for rule in brain.get("learned_rules", []):
        try:
            phrase = rule["phrase"]
            m = re.search(rf"(?i)\b{re.escape(phrase)}\b", text)
            if not m:
                continue
            out.append(_v(
                rule["category"] or "LEARNED_RULE",
                rule["severity"],
                rule["issue"],
                rule["correction"],
                {"brain_key": f"learned_rules[{rule['id']}]",
                 "expected": f"no '{phrase}' without approval",
                 "found": m.group(0)},
                span={"text": m.group(0), "start": m.start(), "end": m.end()},
            ))
        except Exception:
            continue  # fail open on any malformed learned rule
    return out


LEARNED_SEVERITIES = {"MEDIUM", "HIGH", "CRITICAL"}


def _write_brain(brain: dict, brain_path: Path) -> None:
    """Atomically rewrite company_brain.json (temp file + os.replace)."""
    fd, tmp = tempfile.mkstemp(dir=brain_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(brain, indent=2) + "\n")
        os.replace(tmp, brain_path)
    except BaseException:
        os.unlink(tmp)
        raise


def add_learned_rule(rule: dict, brain_path=BRAIN_PATH) -> dict:
    """Store a runtime-added rule in company_brain.json (atomic rewrite).

    Raises ValueError on bad input; dedupes on phrase (case-insensitive).
    """
    if not isinstance(rule, dict):
        raise ValueError("learned rule must be an object")
    phrase = rule.get("phrase")
    if not isinstance(phrase, str) or not (3 <= len(phrase.strip()) <= 120):
        raise ValueError("learned rule 'phrase' must be 3-120 characters")
    phrase = phrase.strip()
    severity = rule.get("severity", "HIGH")
    if severity not in LEARNED_SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(LEARNED_SEVERITIES)}")

    brain_path = Path(brain_path)
    brain = json.loads(brain_path.read_text())
    learned = brain.setdefault("learned_rules", [])
    for existing in learned:
        if isinstance(existing, dict) and \
                str(existing.get("phrase", "")).lower() == phrase.lower():
            return existing

    stored = {
        "id": "lr_" + uuid.uuid4().hex[:8],
        "phrase": phrase,
        "category": rule.get("category") or "LEARNED_RULE",
        "severity": severity,
        "issue": rule.get("issue") or f"Message contains learned-rule phrase '{phrase}'.",
        "correction": rule.get("correction")
            or "Remove the phrase or get explicit approval before sending.",
        "created_ts": datetime.now(timezone.utc).isoformat(),
    }
    if rule.get("source_feed_id"):
        stored["source_feed_id"] = rule["source_feed_id"]
    learned.append(stored)
    _write_brain(brain, brain_path)
    return stored


def add_learned_exception(rule: dict, brain_path=BRAIN_PATH) -> dict:
    """Store a runtime exception: suppresses a category when its phrase
    appears in the checked text. Atomic write; dedupes on (phrase, category).

    Raises ValueError on bad input.
    """
    if not isinstance(rule, dict):
        raise ValueError("learned exception must be an object")
    phrase = rule.get("phrase")
    if not isinstance(phrase, str) or not (3 <= len(phrase.strip()) <= 120):
        raise ValueError("learned exception 'phrase' must be 3-120 characters")
    phrase = phrase.strip()
    category = rule.get("category")
    if not isinstance(category, str) or not category.strip():
        raise ValueError("learned exception 'category' is required")
    category = category.strip()

    brain_path = Path(brain_path)
    brain = json.loads(brain_path.read_text())
    exceptions = brain.setdefault("learned_exceptions", [])
    for existing in exceptions:
        if isinstance(existing, dict) and \
                str(existing.get("phrase", "")).lower() == phrase.lower() and \
                existing.get("category") == category:
            return existing

    stored = {
        "id": "le_" + uuid.uuid4().hex[:8],
        "phrase": phrase,
        "category": category,
        "created_ts": datetime.now(timezone.utc).isoformat(),
    }
    if rule.get("note"):
        stored["note"] = rule["note"]
    if rule.get("source_feed_id"):
        stored["source_feed_id"] = rule["source_feed_id"]
    exceptions.append(stored)
    _write_brain(brain, brain_path)
    return stored


def _apply_exceptions(text: str, violations: list, brain: dict) -> list:
    """Drop violations suppressed by a learned exception — fail open."""
    low = text.lower()
    for exc in brain.get("learned_exceptions", []):
        try:
            if exc["phrase"].lower() in low:
                violations = [v for v in violations
                              if v["category"] != exc["category"]]
        except Exception:
            continue
    return violations


ALL_CHECKS = [
    check_payment_terms,
    check_discount_cap,
    check_treasury_lock,
    check_bank_details,
    check_amounts_vs_contract,
    check_large_commitment,
    check_feature_claims,
    check_refund_credits,
    check_duplicate_invoice,
    check_sender_domain,
    check_urgent_payment_change,
    check_unverified_claims,
    check_expense_approval,
    check_price_floor,
    check_confidential_leak,
    check_spend_tiers,
    check_unapproved_payment,
    check_new_vendor_bank,
    check_payment_off_cycle,
    check_learned_rules,
]

# Which context_types each check runs in. "ALL" = fraud signatures that must
# fire everywhere; a check absent from this map also defaults to "ALL".
VALID_CONTEXT_TYPES = {"outgoing_email", "slack_message", "incoming_invoice", "general"}
CONTEXTS = {
    check_bank_details: "ALL",
    check_duplicate_invoice: "ALL",
    check_urgent_payment_change: "ALL",
    check_learned_rules: "ALL",
    check_amounts_vs_contract: {"incoming_invoice"},
    check_sender_domain: {"incoming_invoice"},
    check_payment_terms: {"outgoing_email", "slack_message", "general"},
    check_discount_cap: {"outgoing_email", "slack_message", "general"},
    check_treasury_lock: {"outgoing_email", "slack_message", "general"},
    check_feature_claims: {"outgoing_email", "slack_message", "general"},
    check_refund_credits: {"outgoing_email", "slack_message", "general"},
    check_large_commitment: {"outgoing_email", "slack_message", "general"},
    check_unverified_claims: {"outgoing_email", "slack_message", "general"},
    check_expense_approval: {"outgoing_email", "slack_message", "general"},
    check_price_floor: {"outgoing_email", "slack_message", "general"},
    check_confidential_leak: {"outgoing_email", "slack_message", "general"},
    check_spend_tiers: {"outgoing_email", "slack_message", "general"},
    check_payment_off_cycle: {"outgoing_email", "slack_message", "general"},
    check_unapproved_payment: "ALL",
    check_new_vendor_bank: "ALL",
}


def run_rules(text: str, brain: dict, context_type: Optional[str] = None) -> list:
    violations = []
    filter_ctx = context_type if context_type in VALID_CONTEXT_TYPES else None
    for check in ALL_CHECKS:
        allowed = CONTEXTS.get(check, "ALL")
        if filter_ctx is not None and isinstance(allowed, set) \
                and filter_ctx not in allowed:
            continue
        violations.extend(check(text, brain))
    return _apply_exceptions(text, violations, brain)


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


def explain_policy(question: str, brain: dict) -> dict:
    """Answer a 'what are the rules?' question from the brain — no LLM.

    Returns {"answer": str, "sources": [{"brain_key", "value"}], "matched": bool}.
    """
    q = question.lower()
    fin = brain.get("financial_rules", {})
    pol = brain.get("internal_policies", {})
    people = brain.get("people", {})
    channel = people.get("finance_approval_channel", "#finance-approvals")

    def _ans(answer, *sources):
        return {"answer": answer,
                "sources": [{"brain_key": k, "value": v} for k, v in sources],
                "matched": True}

    learned = brain.get("learned_rules", [])
    if any(k in q for k in ("learned", "taught it", "teach it")) or any(
            isinstance(r, dict) and r.get("phrase")
            and r["phrase"].lower() in q for r in learned):
        if learned:
            listing = "; ".join(f"'{r.get('phrase')}' ({r.get('severity', '?')})"
                                for r in learned[:5])
            return _ans(f"Rules learned at runtime: {listing}.",
                        ("learned_rules", learned))
        return _ans("No learned rules yet — humans can add them and they're "
                    "enforced immediately.", ("learned_rules", learned))

    fin_section = brain.get("finance", {})
    invoices = fin_section.get("invoices", [])
    people_map = brain.get("people", {})

    if "runway" in q or ("burn" in q and "rate" not in q):
        bank = fin_section.get("bank", {})
        bal, burn = bank.get("balance_gbp"), bank.get("monthly_burn_gbp")
        if bal is not None and burn:
            months = bal / burn
            return _ans(f"£{bal:,.0f} in the bank ÷ £{burn:,.0f}/month burn "
                        f"≈ {months:.1f} months of runway.",
                        ("finance.bank.balance_gbp", bal),
                        ("finance.bank.monthly_burn_gbp", burn))
        return _ans("Bank balance and monthly burn aren't in the brain yet.",
                    ("finance.bank", bank))

    if "overdue" in q:
        late = [i for i in invoices if i.get("status") == "overdue"]
        if not late:
            return _ans("No overdue invoices in the brain right now.",
                        ("finance.invoices", invoices))
        listing = "; ".join(
            f"{i['id']} {i['counterparty']} £{i['amount_gbp']:,} "
            f"{i['kind']} (was due {i['due_date']})" for i in late)
        return _ans(f"Overdue: {listing}.", ("finance.invoices", late))

    if any(k in q for k in ("due out", "due this month", "due next month",
                            "what's due", "whats due", "going out",
                            "payment run", "pay run", "when do we pay")):
        run_days = fin_section.get("payment_rules", {}) \
            .get("payment_run_days", [])
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        due = [i for i in invoices
               if i.get("kind") == "payable" and i.get("status") != "paid"
               and str(i.get("due_date", "")).startswith(month)]
        parts = [f"{i['id']} {i['counterparty']} £{i['amount_gbp']:,} "
                 f"({i['status']}, due {i['due_date']})" for i in due]
        answer = (f"Payables due {month}: " + "; ".join(parts) + "."
                  if parts else f"No unpaid payables due in {month}.")
        if run_days:
            answer += f" Payment runs go out on {'/'.join(run_days)}."
        return _ans(answer, ("finance.invoices", invoices),
                    ("finance.payment_rules.payment_run_days", run_days))

    if any(k in q for k in ("who approves", "who can approve", "approver",
                            "approval tier", "spend over", "approve spend",
                            "how much can i spend", "spending limit")):
        tiers = fin_section.get("spend_approvals", [])
        if not tiers:
            return _ans("No spend-approval tiers in the brain yet.",
                        ("finance.spend_approvals", tiers))
        parts = []
        prev = 0
        for t in tiers:
            names = " + ".join(people_map.get(r, r)
                               for r in t.get("approvers", []))
            cap = t.get("max_gbp")
            band = (f"over £{prev:,}" if cap is None
                    else f"£{prev:,}–£{cap:,}" if prev
                    else f"up to £{cap:,}")
            parts.append(f"{band}: {names}")
            prev = cap or prev
        return _ans("Spend approvals — " + "; ".join(parts) + ".",
                    ("finance.spend_approvals", tiers),
                    ("people", people_map))

    if any(k in q for k in ("bank", "iban", "sort code", "account number",
                            "payment details", "change of bank")):
        return _ans(fin.get("fraud_controls", "Verify bank changes out-of-band.")
                    + " Always check the IBAN against the signed contract.",
                    ("financial_rules.fraud_controls", fin.get("fraud_controls")),
                    ("signed_contracts",
                     [c["vendor_name"] for c in brain.get("signed_contracts", [])]))

    if any(k in q for k in ("client list", "customer list", "confidential",
                            "customer name", "revenue figure", "leak")):
        return _ans(pol.get("confidential_data", "Keep customer data private."),
                    ("internal_policies.confidential_data",
                     pol.get("confidential_data")),
                    ("company.customers",
                     brain.get("company", {}).get("customers", [])))

    if any(k in q for k in ("seat", "price floor", "pricing", "per-seat",
                            "plan price", "cheaper")):
        plans = pol.get("pricing_floor_gbp_per_seat", {})
        listing = ", ".join(f"{p} £{v}/seat" for p, v in plans.items())
        return _ans(f"Never quote below the per-seat floor: {listing}.",
                    ("internal_policies.pricing_floor_gbp_per_seat", plans))

    if any(k in q for k in ("discount", "margin", "% off", "percent off")):
        cap = fin.get("max_unapproved_discount_percent")
        return _ans(f"Discounts are capped at {cap}% — anything bigger needs "
                    f"approval in {channel}.",
                    ("financial_rules.max_unapproved_discount_percent", cap))

    if any(k in q for k in ("quarterly", "billing", "treasury")):
        return _ans(fin.get("treasury_lock", "Quarterly billing is disabled."),
                    ("financial_rules.treasury_lock", fin.get("treasury_lock")))

    if any(k in q for k in ("payment term", "net-", "net ", "terms")):
        return _ans(f"Payment terms are capped at "
                    f"{fin.get('max_payment_terms')} — extended terms need "
                    "50% upfront.",
                    ("financial_rules.max_payment_terms",
                     fin.get("max_payment_terms")))

    if any(k in q for k in ("refund", "credit note", "compensation",
                            "service credit")):
        cap = fin.get("refund_or_credit_cap_gbp")
        return _ans(f"Refunds or credits over £{cap} need approval first.",
                    ("financial_rules.refund_or_credit_cap_gbp", cap))

    if any(k in q for k in ("expense", "spend", "purchase", "buy",
                            "company card", "corporate card")):
        lim = pol.get("expense_approval_limit_gbp")
        return _ans(f"Any spend over £{lim:,} needs CFO approval first.",
                    ("internal_policies.expense_approval_limit_gbp", lim),
                    ("internal_policies.expense_approval_note",
                     pol.get("expense_approval_note")))

    if any(k in q for k in ("approval", "approve", "commitment", "sign-off",
                            "signoff")):
        thr = fin.get("cfo_approval_required_over_gbp")
        return _ans(f"Commitments over £{thr:,} need CFO approval "
                    f"({people.get('cfo', 'the CFO')}) before sending.",
                    ("financial_rules.cfo_approval_required_over_gbp", thr))

    if any(k in q for k in ("contract", "vendor", "supplier", "retainer",
                            "hourly rate")):
        cs = brain.get("signed_contracts", [])
        listing = "; ".join(
            f"{c['vendor_name']}: £{c['approved_monthly_retainer_gbp']:,}/mo, "
            f"£{c['hourly_rate_gbp']}/hr, IBAN {c['bank_iban']}" for c in cs)
        return _ans(f"Signed contracts — {listing}.", ("signed_contracts", cs))

    if any(k in q for k in ("engineering", "feature", "status", "soc 2",
                            "sso", "saml", "roadmap", "shipped", "is live",
                            "launched")):
        es = brain.get("engineering_status", [])
        listing = "; ".join(f"{i['feature']} — {i['status']}" for i in es)
        return _ans(f"Engineering status — {listing}.",
                    ("engineering_status", es))

    if any(k in q for k in ("domain", "sender", "email", "phish",
                            "impersonat")):
        doms = brain.get("known_sender_domains", [])
        return _ans("Supplier email only counts from: " + ", ".join(doms)
                    + " — anything else is a possible impersonation.",
                    ("known_sender_domains", doms))

    if any(k in q for k in ("fraud", "scam", "duplicate", "already paid",
                            "paid twice", "urgent")):
        return _ans(fin.get("fraud_controls", "Verify suspicious payment "
                            "requests out-of-band."),
                    ("financial_rules.fraud_controls",
                     fin.get("fraud_controls")))

    if any(k in q for k in ("rule", "rules", "policy", "policies", "allowed",
                            "not allowed")):
        return _ans("Headline rules: Net-30 terms max, discounts "
                    f"≤{fin.get('max_unapproved_discount_percent')}%, monthly "
                    "billing only, spend over "
                    f"£{pol.get('expense_approval_limit_gbp', 0):,} needs CFO "
                    "approval, per-seat pricing floors, and customer names "
                    "never sit next to revenue figures.",
                    ("financial_rules", fin),
                    ("internal_policies", pol),
                    ("company", brain.get("company", {})))

    return {"answer": "Not in the company brain yet. Ask #finance-approvals",
            "sources": [], "matched": False}


def policy_cards(brain: dict) -> list:
    """One card per policy family, generated from the brain (not hardcoded)."""
    fin = brain.get("financial_rules", {})
    pol = brain.get("internal_policies", {})
    people = brain.get("people", {})
    channel = people.get("finance_approval_channel", "#finance-approvals")
    cards = []

    if "max_payment_terms" in fin:
        cards.append({"title": "Payment terms",
                      "rule": f"Terms capped at {fin['max_payment_terms']}; "
                              "extended terms need 50% upfront.",
                      "brain_key": "financial_rules.max_payment_terms",
                      "example_violation": "Offering Net-60 to close a deal."})
    if "max_unapproved_discount_percent" in fin:
        cap = fin["max_unapproved_discount_percent"]
        cards.append({"title": "Discount cap",
                      "rule": f"Discounts above {cap}% need approval in "
                              f"{channel}.",
                      "brain_key": "financial_rules.max_unapproved_discount_percent",
                      "example_violation": "Promising a 15% discount without "
                                           "sign-off."})
    if "treasury_lock" in fin:
        cards.append({"title": "Treasury lock",
                      "rule": fin["treasury_lock"],
                      "brain_key": "financial_rules.treasury_lock",
                      "example_violation": "Offering quarterly billing."})
    if "cfo_approval_required_over_gbp" in fin:
        thr = fin["cfo_approval_required_over_gbp"]
        cards.append({"title": "Commitment approval",
                      "rule": f"Commitments over £{thr:,} need CFO approval.",
                      "brain_key": "financial_rules.cfo_approval_required_over_gbp",
                      "example_violation": "Confirming a £30k deal directly."})
    if "refund_or_credit_cap_gbp" in fin:
        cap = fin["refund_or_credit_cap_gbp"]
        cards.append({"title": "Refund cap",
                      "rule": f"Refunds or credits over £{cap} need approval.",
                      "brain_key": "financial_rules.refund_or_credit_cap_gbp",
                      "example_violation": "Offering a £900 refund."})
    if "fraud_controls" in fin:
        cards.append({"title": "Fraud controls",
                      "rule": fin["fraud_controls"],
                      "brain_key": "financial_rules.fraud_controls",
                      "example_violation": "Processing an urgent bank-detail "
                                           "change."})
    if "expense_approval_limit_gbp" in pol:
        cards.append({"title": "Expense limit",
                      "rule": pol.get("expense_approval_note")
                      or f"Spend over £{pol['expense_approval_limit_gbp']:,} "
                         "needs CFO approval.",
                      "brain_key": "internal_policies.expense_approval_limit_gbp",
                      "example_violation": "Putting a £6,800 tool on the "
                                           "company card."})
    if "pricing_floor_gbp_per_seat" in pol:
        plans = pol["pricing_floor_gbp_per_seat"]
        listing = ", ".join(f"{p} £{v}/seat" for p, v in plans.items())
        cards.append({"title": "Pricing floor",
                      "rule": f"Never quote below the per-seat floor: "
                              f"{listing}.",
                      "brain_key": "internal_policies.pricing_floor_gbp_per_seat",
                      "example_violation": "Quoting Enterprise at £85/seat."})
    if "confidential_data" in pol:
        cards.append({"title": "Confidential data",
                      "rule": pol["confidential_data"],
                      "brain_key": "internal_policies.confidential_data",
                      "example_violation": "Posting 'Acme Corp pays £48k/yr' "
                                           "in a public channel."})
    if brain.get("known_sender_domains"):
        cards.append({"title": "Trusted senders",
                      "rule": "Supplier email only counts from: "
                              + ", ".join(brain["known_sender_domains"]) + ".",
                      "brain_key": "known_sender_domains",
                      "example_violation": "An invoice from "
                                           "@cloudscale-pay.com."})
    for c in brain.get("signed_contracts", []):
        cards.append({"title": f"Contract — {c['vendor_name']}",
                      "rule": f"Retainer £{c['approved_monthly_retainer_gbp']:,}"
                              f"/mo, £{c['hourly_rate_gbp']}/hr, IBAN "
                              f"{c['bank_iban']}.",
                      "brain_key": f"signed_contracts[{c['vendor_name']}]",
                      "example_violation": f"Paying {c['vendor_name']} to a "
                                           "different IBAN."})
    for i in brain.get("engineering_status", []):
        cards.append({"title": f"Status — {i['feature']}",
                      "rule": i["status"],
                      "brain_key": f"engineering_status[{i['feature']}]",
                      "example_violation": f"Claiming '{i['feature']}' is "
                                           "done and live."})
    for r in brain.get("learned_rules", []):
        cards.append({"title": f"Learned — '{r.get('phrase')}'",
                      "rule": r.get("issue") or f"Learned rule on "
                              f"'{r.get('phrase')}'.",
                      "brain_key": f"learned_rules[{r.get('id')}]",
                      "example_violation": f"Saying '{r.get('phrase')}' in a "
                                           "draft."})
    fin_sec = brain.get("finance", {})
    tiers = fin_sec.get("spend_approvals", [])
    if tiers:
        parts, prev = [], 0
        for t in tiers:
            names = " + ".join(people.get(r, r)
                               for r in t.get("approvers", []))
            cap = t.get("max_gbp")
            parts.append((f"over £{prev:,}" if cap is None
                          else f"£{prev:,}–£{cap:,}" if prev
                          else f"up to £{cap:,}") + f": {names}")
            prev = cap or prev
        cards.append({"title": "Spend approvals",
                      "rule": "Spend tiers — " + "; ".join(parts) + ".",
                      "brain_key": "finance.spend_approvals",
                      "example_violation": "Approving a £12k spend without "
                                           "CFO sign-off."})
    prules = fin_sec.get("payment_rules", {})
    if prules.get("payment_run_days"):
        days = "/".join(prules["payment_run_days"])
        cards.append({"title": "Payment runs",
                      "rule": f"Supplier payments go out on {days} only. "
                              + prules.get("no_unapproved_invoice_payments", ""),
                      "brain_key": "finance.payment_rules.payment_run_days",
                      "example_violation": "Wiring an unpaid invoice on a "
                                           "Friday."})
    bank = fin_sec.get("bank", {})
    if bank.get("balance_gbp") and bank.get("monthly_burn_gbp"):
        months = bank["balance_gbp"] / bank["monthly_burn_gbp"]
        cards.append({"title": "Runway",
                      "rule": f"£{bank['balance_gbp']:,.0f} ÷ "
                              f"£{bank['monthly_burn_gbp']:,.0f}/mo ≈ "
                              f"{months:.1f} months runway (computed, "
                              "never stored).",
                      "brain_key": "finance.bank",
                      "example_violation": "Committing spend that ignores "
                                           "the runway."})
    return cards
