"""AuditTrace — CommitGuard's "brain and hands" invoice interceptor.

Owner: Riyansh.

Where rules.py checks drafted text against policy, AuditTrace parses an
incoming invoice / wire request into structured fields (vendor, invoice
number, amounts, rate, hours, IBAN, sort code, account number, terms,
hidden clauses) and reconciles every field against the brain's
signed_contracts and finance.invoices.

This is the tighter audit: it fires on ANY contract overage (rules.py's
older check only trips at +20%), bank-detail mismatches beyond IBAN (sort
code, account number), hidden uplift/auto-renew clauses, already-paid
invoices being re-billed, and payment-terms drift — and it runs on
invoice-ish slack_message payloads where the old invoice checks never run.

Fully deterministic regex + dictionary checks — no LLM, stdlib only.
Every violation cites evidence: {brain_key, expected, found}, built with
rules._v so the shape is identical to the main engine.

Baseline-safe by construction: a candidate is dropped when `existing`
already contains a violation with the same category OR the same
evidence.brain_key. On the classic CloudScale invoice (rate + retainer
overage + wrong IBAN — all already caught by rules.py) AuditTrace adds
zero violations, preserving the locked baseline.
"""

import copy
import json
import re
from pathlib import Path

import rules

BASE_DIR = Path(__file__).parent
BRAIN_PATH = BASE_DIR / "company_brain.json"
SCENARIOS_PATH = BASE_DIR / "scenarios.json"

# Categories AuditTrace can emit — counted in meta.checks_run when the
# audit is eligible (incoming_invoice or invoice-ish slack text).
CATEGORIES = frozenset({
    "INVOICE_OVER_CONTRACT", "BANK_DETAILS_MISMATCH", "HIDDEN_CLAUSE",
    "DUPLICATE_INVOICE", "TERMS_MISMATCH"})
CHECK_COUNT = 5  # over-contract, bank details, clause, duplicate, terms

# --- parsing regexes (tolerant) -------------------------------------------

# "INVOICE #CS-1187" / "invoice no. CS 1187" / "inv: 1201" -> capture the ref.
# The label keyword must be followed by a real separator — otherwise bare
# "INV-1043" would be misread as keyword `inv` + ref `-1043`.
_INVOICE_LABEL_RE = re.compile(
    r"(?i)\b(?:invoice|inv)(?=\s*(?:no\.?|number|#|:|\s))"
    r"\s*(?:no\.?|number|#|:)?\s*([A-Z]{0,4}[-\s]?\d{3,})")
_RATE_RE = re.compile(r"(?i)£?\s*(\d+(?:\.\d+)?)\s*(?:/|per)\s*h(?:ou)?r")
_HOURS_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(?:hrs?|hours)\b")
_SORT_CODE_RE = re.compile(
    r"(?i)sort\s*code[:\s]*(\d{2}[-\s]?\d{2}[-\s]?\d{2})")
_ACCOUNT_NO_RE = re.compile(
    r"(?i)account\s*(?:no\.?|number|#)?[:\s]*(\d{6,8})")
_TERMS_RE = re.compile(r"(?i)\bnet[\s-]?(\d+)")

# rules._IBAN_RE is uppercase-only — a lowercase IBAN would slip past both
# engines. AuditTrace matches case-insensitively; _norm_iban uppercases
# before comparison, so "gb22barc…" still reconciles against the contract.
_IBAN_CI_RE = re.compile(
    r"\b[A-Za-z]{2}\d{2}(?:\s?[A-Za-z0-9]{4}){2,7}"
    r"(?:\s?[A-Za-z0-9]{1,3})?\b")

# Hidden uplift / auto-renew clause signatures — first hit wins.
_CLAUSE_RES = [
    re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:cpi|annual|yearly)?\s*"
               r"(?:uplift|increase|escalation)", re.I),
    re.compile(r"auto[- ]?renew\w*", re.I),
    re.compile(r"price\s+(?:increase|rise|uplift)", re.I),
    re.compile(r"indexation|indexed\s+pricing", re.I),
]

# Contract keys that, when present, mean the clause is legitimately papered.
_CLAUSE_KEY_HINTS = ("indexation", "uplift", "auto_renew", "auto-renew")

# Invoice-ish keywords for the slack_message gate.
_INVOICEISH_RE = re.compile(r"(?i)\b(invoic\w*|payment\s+due|wir\w*|remit\w*)")

# parse_invoice's public fields, in spec order. _extract() also returns a
# private "_m" bag of re.Match objects so checks can attach spans.
_PUBLIC_KEYS = ("vendor", "invoice_no", "amounts", "rate", "hours", "iban",
                "sort_code", "account_no", "terms", "clause")


# --- helpers ----------------------------------------------------------------

_DEFAULT_BRAIN = None


def _default_brain() -> dict:
    """Lazy read-only load of company_brain.json for standalone parse use."""
    global _DEFAULT_BRAIN
    if _DEFAULT_BRAIN is None:
        try:
            _DEFAULT_BRAIN = json.loads(BRAIN_PATH.read_text())
        except Exception:
            _DEFAULT_BRAIN = {}
    return _DEFAULT_BRAIN


def _fmt_gbp(x) -> str:
    x = float(x)
    return f"£{x:,.0f}" if x == int(x) else f"£{x:,.2f}"


def _span(m) -> dict:
    """Span dict for a regex match (matches rules._v's expected shape)."""
    return {"text": m.group(0), "start": m.start(), "end": m.end()} if m else None


def _span_g1(m) -> dict:
    """Span of capture group 1 — used when group(0) includes a label like
    'INVOICE ' that shouldn't be underlined."""
    return ({"text": m.group(1), "start": m.start(1), "end": m.end(1)}
            if m and m.lastindex else _span(m))


def _norm_inv_no(s: str) -> str:
    """'CS 1187' -> 'CS-1187'; whitespace -> '-', uppercased, edges stripped."""
    return re.sub(r"\s+", "-", s.strip()).upper().strip("-")


def _norm_id(s: str) -> str:
    """Alnum-only uppercase — for comparing invoice ids across formats."""
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def _norm_sort(s: str) -> str:
    """'40 11 22' / '401122' -> '40-11-22' (non-6-digit input passes through)."""
    d = re.sub(r"\D", "", str(s))
    return f"{d[:2]}-{d[2:4]}-{d[4:]}" if len(d) == 6 else str(s).strip()


def _norm_acct(s: str) -> str:
    return re.sub(r"\s+", "", str(s))


def _norm_terms(s: str) -> str:
    return re.sub(r"[\s-]+", "", str(s)).lower()


def _extract(text: str, brain: dict) -> dict:
    """Full parse: public fields plus a private '_m' dict of match objects."""
    out = {k: None for k in _PUBLIC_KEYS}
    out["amounts"] = []
    out["_m"] = {}

    out["vendor"] = rules._find_vendor(text, brain)

    m = _INVOICE_LABEL_RE.search(text)
    if m:
        out["invoice_no"] = _norm_inv_no(m.group(1))
        out["_m"]["invoice_no"] = m
    else:
        m = rules._INVOICE_NO_RE.search(text)
        if m:
            out["invoice_no"] = _norm_inv_no(m.group(0))
            out["_m"]["invoice_no"] = m

    amount_ms = []
    for m, v in rules.gbp_amounts(text):
        out["amounts"].append((m.group(0), v))
        amount_ms.append(m)
    out["_m"]["amounts"] = amount_ms

    m = _RATE_RE.search(text)
    if m:
        out["rate"] = float(m.group(1))
        out["_m"]["rate"] = m

    m = _HOURS_RE.search(text)
    if m:
        out["hours"] = float(m.group(1))
        out["_m"]["hours"] = m

    m = rules._IBAN_RE.search(text) or _IBAN_CI_RE.search(text)
    if m:
        out["iban"] = m.group(0)
        out["_m"]["iban"] = m

    m = _SORT_CODE_RE.search(text)
    if m:
        out["sort_code"] = _norm_sort(m.group(1))
        out["_m"]["sort_code"] = m

    m = _ACCOUNT_NO_RE.search(text)
    if m:
        out["account_no"] = m.group(1)
        out["_m"]["account_no"] = m

    m = _TERMS_RE.search(text)
    if m:
        out["terms"] = f"Net-{m.group(1)}"
        out["_m"]["terms"] = m

    for pat in _CLAUSE_RES:
        m = pat.search(text)
        if m:
            out["clause"] = m.group(0)
            out["_m"]["clause"] = m
            break

    return out


def parse_invoice(text: str) -> dict:
    """Parse invoice/wire text into fields.

    -> {"vendor": contract-dict|None, "invoice_no": str|None,
        "amounts": [(match_text, float)], "rate": float|None,
        "hours": float|None, "iban": str|None, "sort_code": str|None,
        "account_no": str|None, "terms": str|None (e.g. "Net-30"),
        "clause": match-str|None}

    Vendor resolves against company_brain.json (read-only, cached).
    """
    p = _extract(text, _default_brain())
    return {k: p[k] for k in _PUBLIC_KEYS}


def _invoiceish(text: str, p: dict) -> bool:
    """slack_message gate: does this text look like an invoice/wire?

    A vendor mention + an amount is NOT enough — that also matches pricing
    decisions ("retainer moves to £5,500/mo"). Require an invoice cue: an
    invoice ref, a bank detail, or an invoice/wire/remit keyword.
    """
    if p["invoice_no"] or p["iban"] or p["sort_code"] or p["account_no"]:
        return True
    if _INVOICEISH_RE.search(text) and (p["vendor"] or p["amounts"]):
        return True
    return False


def _already_flagged(candidate: dict, existing: list) -> bool:
    """Baseline-safety dedupe: skip when `existing` has the same category or
    the same evidence.brain_key as the candidate."""
    key = (candidate.get("evidence") or {}).get("brain_key")
    for v in existing or []:
        if v.get("category") == candidate.get("category"):
            return True
        if key and (v.get("evidence") or {}).get("brain_key") == key:
            return True
    return False


def _verify_correction(vendor: dict) -> str:
    phone = vendor.get("contact_phone")
    if phone:
        return (f"Do not pay — call {phone} (the number on file, never the "
                "email) to verify the bank details.")
    return ("Do not pay — verify the bank details out-of-band on a known "
            "number, never by replying to the invoice.")


def _contract_covers_clause(vendor: dict) -> bool:
    """True if the contract carries an indexation/uplift/auto_renew key."""
    return any(h in str(k).lower()
               for k in vendor for h in _CLAUSE_KEY_HINTS)


# --- the audit --------------------------------------------------------------

def audit_violations(text: str, brain: dict,
                     context_type: str = "incoming_invoice",
                     existing: list = None) -> list:
    """Reconcile an invoice/wire payload against the brain.

    Returns ADDITIONAL violations beyond `existing` (deduped on category and
    evidence.brain_key). Runs for context_type "incoming_invoice", and for
    "slack_message" only when the payload is invoice-ish.
    """
    existing = existing or []
    p = _extract(text, brain)

    if context_type == "incoming_invoice":
        pass
    elif context_type == "slack_message" and _invoiceish(text, p):
        pass
    else:
        return []

    out = []

    def add(v):
        if not _already_flagged(v, existing):
            out.append(v)

    vendor = p["vendor"]
    vname = vendor["vendor_name"] if vendor else None
    invoices = brain.get("finance", {}).get("invoices", [])

    # 1. INVOICE_OVER_CONTRACT (HIGH) — any rate/amount over contract, not
    #    just rules.py's +20% band.
    if vendor:
        rate_cap = vendor.get("hourly_rate_gbp")
        if rate_cap is not None and p["rate"] is not None \
                and p["rate"] > rate_cap:
            delta = p["rate"] - rate_cap
            add(rules._v(
                "INVOICE_OVER_CONTRACT", "HIGH",
                f"{vname} billed at {_fmt_gbp(p['rate'])}/hr — "
                f"{_fmt_gbp(delta)}/hr over the contracted "
                f"{_fmt_gbp(rate_cap)}/hr.",
                f"Reject the uplift; the signed rate is "
                f"{_fmt_gbp(rate_cap)}/hr — pay at contract rate.",
                {"brain_key": f"signed_contracts[{vname}].hourly_rate_gbp",
                 "expected": rate_cap, "found": p["rate"],
                 "delta_gbp_per_hr": delta},
                span=_span(p["_m"].get("rate"))))

        retainer = vendor.get("approved_monthly_retainer_gbp")
        if retainer is not None:
            best = None  # (amount, match) for the largest over-retainer sum
            for m, (_mt, amt) in zip(p["_m"]["amounts"], p["amounts"]):
                if amt > retainer and amt != p["rate"]:
                    if best is None or amt > best[0]:
                        best = (amt, m)
            if best:
                amt, m = best
                delta = amt - retainer
                add(rules._v(
                    "INVOICE_OVER_CONTRACT", "HIGH",
                    f"{vname} billed {_fmt_gbp(amt)} — {_fmt_gbp(delta)} "
                    f"over the {_fmt_gbp(retainer)}/mo approved retainer.",
                    "Hold payment and request a credit note or PO reference "
                    "for the variance.",
                    {"brain_key": f"signed_contracts[{vname}]"
                                  ".approved_monthly_retainer_gbp",
                     "expected": retainer, "found": amt,
                     "delta_gbp": delta},
                    span=_span(m)))

    # 2. BANK_DETAILS_MISMATCH (CRITICAL) — IBAN / sort code / account no.
    #    Every differing field collapses into ONE violation (it is one BEC
    #    fraud signal); each field is deduped against `existing` on its own
    #    brain_key, so an IBAN already flagged as PAYMENT_REDIRECTION drops
    #    out while a fresh sort-code mismatch still lands.
    if vendor:
        diffs = []  # (label, brain_key, expected, found, match)
        if p["iban"] and vendor.get("bank_iban") and \
                rules._norm_iban(p["iban"]) != \
                rules._norm_iban(vendor["bank_iban"]):
            diffs.append(("IBAN", f"signed_contracts[{vname}].bank_iban",
                          vendor["bank_iban"], p["iban"],
                          p["_m"].get("iban")))
        if p["sort_code"] and vendor.get("bank_sort_code") and \
                p["sort_code"] != _norm_sort(vendor["bank_sort_code"]):
            diffs.append(("sort code",
                          f"signed_contracts[{vname}].bank_sort_code",
                          vendor["bank_sort_code"], p["sort_code"],
                          p["_m"].get("sort_code")))
        if p["account_no"] and vendor.get("bank_account_no") and \
                _norm_acct(p["account_no"]) != \
                _norm_acct(vendor["bank_account_no"]):
            diffs.append(("account number",
                          f"signed_contracts[{vname}].bank_account_no",
                          vendor["bank_account_no"], p["account_no"],
                          p["_m"].get("account_no")))
        covered = {(v.get("evidence") or {}).get("brain_key")
                   for v in existing}
        diffs = [d for d in diffs if d[1] not in covered]
        if diffs:
            detail = "; ".join(f"{lbl} {fnd} vs contracted {exp}"
                               for lbl, _k, exp, fnd, _m in diffs)
            add(rules._v(
                "BANK_DETAILS_MISMATCH", "CRITICAL",
                f"Bank details for {vname} differ from the signed "
                f"contract — {detail} — the BEC/mandate-fraud signature. "
                "Do not pay; verify out-of-band.",
                _verify_correction(vendor),
                {"brain_key": diffs[0][1],
                 "expected": diffs[0][2], "found": diffs[0][3],
                 "vendor": vname,
                 "fields": [{"field": lbl, "brain_key": k,
                             "expected": e, "found": f}
                            for lbl, k, e, f, _m in diffs]},
                span=_span(diffs[0][4])))

    # 3. HIDDEN_CLAUSE (HIGH) — uplift/auto-renew text the contract doesn't
    #    paper over.
    if vendor and p["clause"] and not _contract_covers_clause(vendor):
        add(rules._v(
            "HIDDEN_CLAUSE", "HIGH",
            f"'{p['clause']}' on the {vname} invoice — an uplift/auto-renew "
            "clause not present in the signed contract.",
            "Strike the clause or re-paper the contract before paying; an "
            "uncontracted uplift is not owed.",
            {"brain_key": f"signed_contracts[{vname}]",
             "expected": "no uplift/auto-renew clause in contract",
             "found": p["clause"]},
            span=_span(p["_m"].get("clause"))))

    # 4. DUPLICATE_INVOICE (CRITICAL) — re-billing something already paid.
    fired_dup = False
    if p["invoice_no"]:
        key = _norm_id(p["invoice_no"])
        for inv in invoices:
            iid = _norm_id(inv.get("id", ""))
            # digits-only refs ("INVOICE 1043") match the id's digit tail
            if inv.get("status") == "paid" and \
                    (iid == key or (key.isdigit() and iid.endswith(key))):
                add(rules._v(
                    "DUPLICATE_INVOICE", "CRITICAL",
                    f"{p['invoice_no']} ({inv.get('counterparty')}, "
                    f"{_fmt_gbp(inv.get('amount_gbp', 0))}) is already "
                    "marked paid — this is a duplicate payment request.",
                    "Do not pay. Confirm against the ledger — re-billing a "
                    "paid invoice is a classic duplicate-invoice fraud.",
                    {"brain_key":
                     f"finance.invoices[{inv.get('id')}].status",
                     "expected": "unpaid or absent", "found": "paid",
                     "invoice_id": inv.get("id")},
                    span=_span_g1(p["_m"].get("invoice_no"))))
                fired_dup = True
                break
    if vendor and not fired_dup:
        for inv in invoices:
            if inv.get("kind") != "payable" or inv.get("status") != "paid":
                continue
            if str(inv.get("counterparty", "")).strip().lower() != \
                    str(vname).strip().lower():
                continue
            hit = next(
                (m for m, (_mt, amt) in zip(p["_m"]["amounts"], p["amounts"])
                 if abs(amt - float(inv.get("amount_gbp", 0))) < 0.01),
                None)
            if hit:
                add(rules._v(
                    "DUPLICATE_INVOICE", "CRITICAL",
                    f"{vname} billed {_fmt_gbp(inv.get('amount_gbp', 0))} — "
                    f"the same amount as {inv.get('id')}, which is already "
                    "marked paid. Possible duplicate payment request.",
                    "Do not pay. Confirm against the ledger — re-billing a "
                    "paid invoice is a classic duplicate-invoice fraud.",
                    {"brain_key":
                     f"finance.invoices[{inv.get('id')}].status",
                     "expected": "unpaid or absent", "found": "paid",
                     "invoice_id": inv.get("id")},
                    span=_span(hit)))
                break

    # 5. TERMS_MISMATCH (MEDIUM) — invoice terms drift from the contract.
    if vendor and p["terms"] and vendor.get("payment_terms") and \
            _norm_terms(p["terms"]) != _norm_terms(vendor["payment_terms"]):
        add(rules._v(
            "TERMS_MISMATCH", "MEDIUM",
            f"{vname} invoice terms {p['terms']} differ from the "
            f"contracted {vendor['payment_terms']}.",
            f"Pay on the contracted {vendor['payment_terms']} terms; "
            "different terms need PO sign-off first.",
            {"brain_key": f"signed_contracts[{vname}].payment_terms",
             "expected": vendor["payment_terms"], "found": p["terms"]},
            span=_span(p["_m"].get("terms"))))

    return out


# --- self-test ---------------------------------------------------------------

if __name__ == "__main__":
    # Real brain + real scenarios, read-only.
    brain = json.loads(BRAIN_PATH.read_text())
    scenarios = json.loads(SCENARIOS_PATH.read_text())

    # (a) Locked baseline: the classic CloudScale invoice (rate + retainer
    #     overage + wrong IBAN, all already caught by rules.py) must add ZERO.
    base = scenarios["vendor_invoice"]["text"]
    existing = rules.run_rules(base, brain, "incoming_invoice")
    assert sorted(v["category"] for v in existing) == \
        ["CONTRACT_OVERAGE", "CONTRACT_OVERAGE", "PAYMENT_REDIRECTION"], \
        existing
    extra = audit_violations(base, brain, "incoming_invoice", existing)
    assert extra == [], f"baseline must add zero violations, got {extra}"

    # (b) Small overage (< +20%) the old engine misses -> INVOICE_OVER_CONTRACT
    #     with a £400 delta on the £5,000/mo retainer.
    t = ("INVOICE CS-1201\nCloudScale Ltd\nMonthly retainer: £5,400\n"
         "Please pay to IBAN GB29REVOLUT12345689")
    v = audit_violations(t, brain)
    assert len(v) == 1 and v[0]["category"] == "INVOICE_OVER_CONTRACT" \
        and v[0]["evidence"]["delta_gbp"] == 400, v

    # (c) Sort-code/account-number mismatch -> ONE BANK_DETAILS_MISMATCH
    #     enumerating every differing field in evidence.fields. The
    #     bank_sort_code/bank_account_no contract fields are additive and
    #     may be absent — pin known values on a deep copy of the real brain
    #     (real file stays untouched).
    b2 = copy.deepcopy(brain)
    for c in b2["signed_contracts"]:
        if c["vendor_name"] == "CloudScale Ltd":
            c["bank_sort_code"] = "20-00-00"
            c["bank_account_no"] = "87654321"
    t = ("INVOICE CS-1207\nCloudScale Ltd — £5,000\n"
         "Remit to sort code 40-11-22, account number 12345678")
    v = audit_violations(t, b2)
    assert [x["category"] for x in v] == ["BANK_DETAILS_MISMATCH"], v
    keys = {f["brain_key"].rsplit(".", 1)[-1]
            for f in v[0]["evidence"].get("fields", [])}
    assert keys == {"bank_sort_code", "bank_account_no"}, v

    # (d) "8% CPI uplift" buried in the invoice -> HIDDEN_CLAUSE.
    t = ("INVOICE CS-1208\nCloudScale Ltd — £5,000\n"
         "Includes 8% CPI uplift from this billing cycle")
    v = audit_violations(t, brain)
    assert [x["category"] for x in v] == ["HIDDEN_CLAUSE"], v
    assert "uplift" in v[0]["evidence"]["found"].lower(), v

    # (e) Paid invoice INV-1039 re-presented -> DUPLICATE_INVOICE.
    t = scenarios["audit_inv_duplicate"]["text"]
    v = audit_violations(t, brain)
    assert [x["category"] for x in v] == ["DUPLICATE_INVOICE"], v
    assert v[0]["evidence"]["found"] == "paid", v

    # (f) Clean invoice matching the contract exactly -> no additions.
    t = ("INVOICE CS-1210\nCloudScale Ltd\nMonthly retainer: £5,000\n"
         "IBAN GB29REVOLUT12345689\nPayment terms: Net-30")
    assert audit_violations(t, brain) == []

    print("SELFTEST PASS")
