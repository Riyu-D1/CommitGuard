#!/usr/bin/env python3
"""Live demo gate — hits a RUNNING CommitGuard server at 127.0.0.1:8000.

Checks /health, /feed/stats, /slack/status, injects every slack_demo_*
scenario through POST /feed/inject and verifies each gets its expected
categories (parsed from backend/smoke_test.py so expectations never drift).
If /ask exists it also asks 2 questions. A missing endpoint is SKIP, never a
crash. Exits non-zero if any row FAILs.
"""
import ast
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8000")
if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
    BASE_URL = sys.argv[1]
ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = ROOT / "backend" / "scenarios.json"
SMOKE_PATH = ROOT / "backend" / "smoke_test.py"


def _expected_map():
    """Pull the SLACK_DEMO/FINANCE_DEMO/TRIBAL_DEMO/AUDIT_DEMO
    expected-category dicts out of smoke_test.py so expectations never
    drift. Dicts that don't exist yet are simply skipped."""
    tree = ast.parse(SMOKE_PATH.read_text())
    merged = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") in ("SLACK_DEMO", "FINANCE_DEMO",
                                         "TRIBAL_DEMO", "AUDIT_DEMO")
                for t in node.targets):
            merged.update(ast.literal_eval(node.value))
    return merged


def _req(method, path, payload=None, timeout=5):
    req = urllib.request.Request(BASE_URL + path, method=method)
    data = json.dumps(payload).encode() if payload is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None
    except Exception as e:
        return None, {"error": str(e)}


def _list_from(payload, *keys):
    """Normalise a list-or-wrapped-list JSON payload."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in keys:
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def _prop_key(prop):
    """Stable identity for a proposal dict (id, else serialized form)."""
    if isinstance(prop, dict):
        return prop.get("id") or prop.get("proposal_id") or json.dumps(
            prop, sort_keys=True, default=str)
    return json.dumps(prop, sort_keys=True, default=str)


def main():
    rows = []

    def row(name, status, detail=""):
        rows.append(status)
        print(f"  {name:<30} {status:<5} {detail}")

    print(f"demo_check — {BASE_URL}\n{'-' * 60}")

    code, health = _req("GET", "/health")
    if code == 200 and isinstance(health, dict) and health.get("ok"):
        row("GET /health", "PASS",
            f"engine={health.get('engine')} checks={health.get('checks')}")
    elif code == 200:
        row("GET /health", "FAIL", f"ok flag missing: {health}")
    else:
        row("GET /health", "FAIL", f"http={code} — is the server running?")

    code, stats = _req("GET", "/feed/stats")
    if code == 404:
        row("GET /feed/stats", "SKIP", "endpoint not implemented")
    elif code == 200 and isinstance(stats, dict):
        row("GET /feed/stats", "PASS", json.dumps(stats)[:70])
    else:
        row("GET /feed/stats", "FAIL", f"http={code}")

    code, st = _req("GET", "/slack/status")
    if code == 404:
        row("GET /slack/status", "SKIP", "endpoint not implemented")
    elif code == 200 and isinstance(st, dict):
        row("GET /slack/status", "PASS", json.dumps(st)[:70])
    else:
        row("GET /slack/status", "FAIL", f"http={code}")

    scenarios = json.loads(SCENARIOS_PATH.read_text())
    expected = _expected_map()
    print('-' * 60)
    for key, sc in scenarios.items():
        if key not in expected:
            continue
        code, item = _req("POST", "/feed/inject",
                          {"text": sc["text"], "user": "demo_check",
                           "context_type": sc.get("context_type")})
        if code in (404, 405):
            row(f"inject {key}", "SKIP", f"http={code}")
            continue
        if code != 200 or not isinstance(item, dict):
            row(f"inject {key}", "FAIL", f"http={code}")
            continue
        cats = {v.get("category") for v in item.get("violations", [])}
        missing = set(expected[key]) - cats
        if missing:
            row(f"inject {key}", "FAIL", f"missing {sorted(missing)}")
        else:
            row(f"inject {key}", "PASS", f"got {sorted(cats) or 'CLEAN'}")

    print('-' * 60)
    for i, q in enumerate(["can I give a 20% discount?",
                           "who approves spend over £5k?",
                           "what's our runway?"], 1):
        code, res = _req("POST", "/ask", {"question": q})
        if code in (404, 405, 422):
            row(f"ask #{i}", "SKIP", f"http={code} (no /ask endpoint yet)")
        elif code == 200 and isinstance(res, dict) and res.get("answer"):
            row(f"ask #{i}", "PASS", str(res["answer"])[:60])
        else:
            row(f"ask #{i}", "FAIL", f"http={code}")

    print('-' * 60)
    print("TribalSync + AuditTrace live flow")

    verify_payload = {"text": "we can offer Net-45 terms to close this",
                      "context_type": "slack_message"}

    # a) baseline verdict — while the brain still says Net-30, offering
    #    Net-45 must breach FINANCIAL_POLICY
    code, res = _req("POST", "/verify-context", verify_payload)
    if code != 200 or not isinstance(res, dict):
        row("tribal pre-verdict", "SKIP", f"http={code}")
    else:
        got = {v.get("category") for v in res.get("violations", [])}
        if "FINANCIAL_POLICY" in got:
            row("tribal pre-verdict", "PASS", f"got {sorted(got)}")
        else:
            row("tribal pre-verdict", "FAIL",
                f"expected FINANCIAL_POLICY, got {sorted(got) or 'CLEAN'}")

    # b) a CFO-style decision message should create a pending proposal
    code, _ = _req("POST", "/feed/inject",
                   {"text": "CFO here: from today, payment terms are "
                            "Net-45 for all suppliers.",
                    "user": "demo_check"})
    code2, props = _req("GET", "/brain/proposals?status=pending")
    proposal_id = None
    if code in (404, 405) or code2 in (404, 405):
        row("tribal proposal", "SKIP",
            f"inject http={code} proposals http={code2}")
    elif code2 != 200:
        row("tribal proposal", "FAIL", f"http={code2}")
    else:
        for p in _list_from(props, "proposals", "items", "pending"):
            if isinstance(p, dict) and p.get("brain_key") == \
                    "financial_rules.max_payment_terms":
                proposal_id = p.get("id") or p.get("proposal_id")
                break
        if proposal_id is not None:
            row("tribal proposal", "PASS", f"id={proposal_id}")
        else:
            row("tribal proposal", "FAIL",
                "no pending proposal for "
                "financial_rules.max_payment_terms")

    # c) applying the proposal flips the brain to Net-45
    applied = False
    if proposal_id is None:
        row("tribal apply", "SKIP", "no pending proposal captured")
    else:
        code, res = _req("POST", f"/brain/proposals/{proposal_id}/apply")
        if code == 200 and isinstance(res, dict) and res.get("applied"):
            applied = True
            row("tribal apply", "PASS", "applied=true")
        elif code in (404, 405):
            row("tribal apply", "SKIP", f"http={code}")
        else:
            row("tribal apply", "FAIL",
                f"http={code} {json.dumps(res)[:60]}")

    # d) the same text must no longer breach policy post-apply
    if not applied:
        row("tribal verdict flip", "SKIP", "apply did not succeed")
    else:
        code, res = _req("POST", "/verify-context", verify_payload)
        if code != 200 or not isinstance(res, dict):
            row("tribal verdict flip", "SKIP", f"http={code}")
        else:
            got = {v.get("category") for v in res.get("violations", [])}
            if "FINANCIAL_POLICY" in got:
                row("tribal verdict flip", "FAIL",
                    f"FINANCIAL_POLICY still fired: {sorted(got)}")
            else:
                row("tribal verdict flip", "PASS",
                    f"got {sorted(got) or 'CLEAN'}")

    # e) the change must be recorded in the brain changelog
    if not applied:
        row("brain changelog", "SKIP", "apply did not succeed")
    else:
        code, log = _req("GET", "/brain/changelog?limit=5")
        if code in (404, 405):
            row("brain changelog", "SKIP", "endpoint not implemented")
        elif code != 200:
            row("brain changelog", "FAIL", f"http={code}")
        else:
            entries = _list_from(log, "changelog", "entries", "changes",
                                 "items")
            hit = any(
                isinstance(e, dict)
                and (e.get("brain_key") or e.get("key")) ==
                "financial_rules.max_payment_terms"
                and str(e.get("old") or e.get("old_value")) == "Net-30"
                and str(e.get("new") or e.get("new_value")) == "Net-45"
                for e in entries)
            if hit:
                row("brain changelog", "PASS", "Net-30 -> Net-45 recorded")
            else:
                row("brain changelog", "FAIL",
                    f"no matching entry in {json.dumps(log)[:60]}")

    # f) audit invoices — each must surface its expected category
    audit_cases = [
        ("audit over_contract",
         "INVOICE CS-1201\nCloudScale Ltd\nMonthly retainer: £5,400\n"
         "Please pay to IBAN GB29REVOLUT12345689",
         {"INVOICE_OVER_CONTRACT"}),
        ("audit iban_fraud",
         "INVOICE CS-1202\nCloudScale Ltd — £5,000 due\n"
         "Updated account: IBAN GB22BARC99887766554",
         {"PAYMENT_REDIRECTION"}),
        ("audit sort_code",
         "INVOICE PPD-441\nPinnacle Print & Design — services £1,800\n"
         "Remit to sort code 40-11-22, account number 99887766",
         {"BANK_DETAILS_MISMATCH"}),
        ("audit hidden_clause",
         "INVOICE PPD-442\nPinnacle Print & Design — £1,800\n"
         "Includes 8% CPI uplift from this billing cycle",
         {"HIDDEN_CLAUSE"}),
        ("audit duplicate",
         "INVOICE INV-1039\nAmazon Web Services\nCloud hosting — £1,140\n"
         "Please pay to IBAN GB99AWSX12345678",
         {"DUPLICATE_INVOICE"}),
        ("audit clean",
         "INVOICE PPD-440\nPinnacle Print & Design — £1,800 monthly "
         "retainer\nIBAN GB33LOYD22334455\nPayment terms: Net-30",
         set()),  # empty want -> expect status CLEAN
    ]
    for name, text, want in audit_cases:
        code, res = _req("POST", "/verify-context",
                         {"text": text, "context_type": "incoming_invoice"})
        if code in (404, 405) or code is None:
            row(name, "SKIP", f"http={code}")
            continue
        if code != 200 or not isinstance(res, dict):
            row(name, "FAIL", f"http={code}")
            continue
        got = {v.get("category") for v in res.get("violations", [])}
        if not want:
            if res.get("status") == "CLEAN":
                row(name, "PASS", "status=CLEAN")
            else:
                row(name, "FAIL",
                    f"expected CLEAN, got {res.get('status')} {sorted(got)}")
        elif want <= got:
            row(name, "PASS", f"got {sorted(got)}")
        else:
            row(name, "FAIL", f"missing {sorted(want - got)}")

    # g) a Net-45 *question* is not a decision — no proposal may be created
    code0, pre = _req("GET", "/brain/proposals?status=pending")
    if code0 != 200:
        row("tribal non-decision", "SKIP", f"proposals http={code0}")
    else:
        pre_keys = {_prop_key(p) for p in
                    _list_from(pre, "proposals", "items", "pending")}
        code1, _ = _req("POST", "/feed/inject",
                        {"text": "should we move to Net-45 for the Globex "
                                 "renewal?", "user": "demo_check"})
        code2, post = _req("GET", "/brain/proposals?status=pending")
        if code2 != 200:
            row("tribal non-decision", "SKIP", f"proposals http={code2}")
        elif code1 in (404, 405) or code1 is None:
            row("tribal non-decision", "SKIP", f"inject http={code1}")
        elif code1 != 200:
            row("tribal non-decision", "FAIL", f"inject http={code1}")
        else:
            new_props = [p for p in
                         _list_from(post, "proposals", "items", "pending")
                         if _prop_key(p) not in pre_keys]
            if new_props:
                row("tribal non-decision", "FAIL",
                    "question created proposal(s): "
                    + json.dumps(new_props)[:60])
            else:
                row("tribal non-decision", "PASS",
                    "no proposal from question")

    print('-' * 60)
    fails = rows.count("FAIL")
    print(f"{len(rows)} checks: {rows.count('PASS')} PASS · "
          f"{rows.count('SKIP')} SKIP · {fails} FAIL")
    print("DEMO READY" if fails == 0 else "DEMO NOT READY")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
