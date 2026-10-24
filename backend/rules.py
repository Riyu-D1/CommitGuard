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

    fd, tmp = tempfile.mkstemp(dir=brain_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(brain, indent=2) + "\n")
        os.replace(tmp, brain_path)
    except BaseException:
        os.unlink(tmp)
        raise
    return stored


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
