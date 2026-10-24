"""TribalSync (owner: Riyansh) — turns feed chatter into reviewable brain patches.

Watches Slack/email feed messages for AUTHORITATIVE DECISIONS ("from now
on...", "new policy...", "we've decided...") and turns each into a BRAIN PATCH
proposal against company_brain.json. Proposals are NEVER auto-applied —
humans decide in the Slack thread or via POST /brain/proposals/{id}/apply and
.../reject. Every proposal cites the message that triggered it plus the feed
items whose rule verdicts the patch is predicted to flip, so a human can see
exactly what applying it changes before they say yes.

Detection is deterministic-first (cue phrases + value extractors, same regex
style as rules.py) with an optional OpenAI stage that only runs when the
deterministic pass finds nothing and an API key is configured. Everything
fails open: no cue, a hedge/question, an unresolvable brain key, a corrupt
proposals file, no API key — all return None / [] rather than raising.
"""

import copy
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import rules

try:
    import actions  # writes audit_log.jsonl rows on apply/reject
except Exception:  # fastapi-less contexts — audit calls are try/except anyway
    actions = None

try:
    from llm_enrich import llm_enabled
except Exception:  # pragma: no cover - llm_enrich is always present
    def llm_enabled() -> bool:
        return False

BASE = Path(__file__).parent
PROPOSALS_PATH = BASE / "brain_proposals.json"

_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# brain_store — partner module (Darsh): get_path / set_path / apply_patch /
# BRAIN_PATH / CHANGELOG_PATH. It may not have merged yet, so the import is
# guarded and a contract-identical local stand-in is used until it lands.
# --------------------------------------------------------------------------

_KEY_SEG_RE = re.compile(r"^([^\[\]]+?)(?:\[([^\[\]]+)\])?$")


def _resolve_list_item(seq, sub):
    """Find the element of a brain list addressed by `key[sub]` — matches the
    subscript against the identity fields used in evidence brain_keys
    (vendor_name, feature, id, counterparty, tier), then a numeric index."""
    if isinstance(sub, str):
        for item in seq:
            if isinstance(item, dict) and sub in (
                    item.get("vendor_name"), item.get("id"),
                    item.get("feature"), item.get("counterparty"),
                    item.get("tier")):
                return item
        for item in seq:  # case-insensitive retry
            if isinstance(item, dict) and any(
                    str(item.get(k, "")).lower() == sub.lower()
                    for k in ("vendor_name", "feature", "id",
                              "counterparty", "tier")):
                return item
    if isinstance(sub, str) and sub.isdigit():
        i = int(sub)
        if 0 <= i < len(seq):
            return seq[i]
    return None


def _get_path(brain, key):
    """brain_store.get_path contract: 'a.b.c', 'a.b[idx-or-name].c'."""
    node = brain
    for seg in str(key).split("."):
        m = _KEY_SEG_RE.match(seg)
        if not m:
            raise KeyError(key)
        name, sub = m.group(1), m.group(2)
        if not isinstance(node, dict) or name not in node:
            raise KeyError(key)
        node = node[name]
        if sub is not None:
            if not isinstance(node, list):
                raise KeyError(key)
            node = _resolve_list_item(node, sub)
            if node is None:
                raise KeyError(key)
    return node


def _set_path(brain, key, value):
    """brain_store.set_path contract — same grammar as _get_path."""
    segs = str(key).split(".")
    node = brain
    for seg in segs[:-1]:
        m = _KEY_SEG_RE.match(seg)
        if not m:
            raise KeyError(key)
        name, sub = m.group(1), m.group(2)
        if not isinstance(node, dict):
            raise KeyError(key)
        if name not in node:
            raise KeyError(key)  # update-only — match brain_store.set_path
        node = node[name]
        if sub is not None:
            if not isinstance(node, list):
                raise KeyError(key)
            item = _resolve_list_item(node, sub)
            if item is None:
                raise KeyError(key)
            node = item
    m = _KEY_SEG_RE.match(segs[-1])
    if not m or not isinstance(node, dict):
        raise KeyError(key)
    name, sub = m.group(1), m.group(2)
    if sub is None:
        node[name] = value
        return
    if name not in node or not isinstance(node[name], list):
        raise KeyError(key)
    seq = node[name]
    item = _resolve_list_item(seq, sub)
    if item is None:
        raise KeyError(key)
    seq[seq.index(item)] = value


def _atomic_write_json(path: Path, data) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class _BrainStoreShim:
    """Local stand-in for brain_store.py until that file merges — exposes the
    exact surface tribal_sync relies on. apply_patch performs the atomic
    brain rewrite + changelog append that the real module owns."""

    BRAIN_PATH = BASE / "company_brain.json"
    CHANGELOG_PATH = BASE / "brain_changelog.jsonl"

    get_path = staticmethod(_get_path)
    set_path = staticmethod(_set_path)

    @staticmethod
    def apply_patch(brain_key, new_value, meta=None, brain_path=None,
                    changelog_path=None):
        brain_path = Path(brain_path or _BrainStoreShim.BRAIN_PATH)
        changelog_path = Path(changelog_path or _BrainStoreShim.CHANGELOG_PATH)
        brain = json.loads(brain_path.read_text())
        try:
            old = _get_path(brain, brain_key)
        except KeyError:
            old = None
        if meta and "expected_old" in meta and meta["expected_old"] != old:
            raise ValueError("conflict: brain moved since proposal")
        _set_path(brain, brain_key, new_value)
        _atomic_write_json(brain_path, brain)
        entry = {
            "id": "chg_" + uuid.uuid4().hex[:8],
            "ts": datetime.now(timezone.utc).isoformat(),
            "brain_key": brain_key,
            "old": old,
            "new": new_value,
            "meta": meta or {},
        }
        with changelog_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry


try:
    import brain_store  # the real thing once Darsh's file lands
except Exception:
    brain_store = _BrainStoreShim

_SET_PATH = getattr(brain_store, "set_path", None) or _set_path


# --------------------------------------------------------------------------
# Detection — cue phrases, hedge rejection, value extractors
# --------------------------------------------------------------------------

_CUE_RE = re.compile(
    r"(?i)\b("
    r"from now on|from today|from this (?:week|month|quarter)|"
    r"new policy|policy update|"
    r"effective\s+(?:immediately|today|now|from\b|as\s+of\b)|"
    r"we've decided|we have decided|going forward|as of today|"
    r"with immediate effect|"
    r"(?:from|as of) next (?:week|month|quarter|q[1-4])"
    r")")

_ROLE_RE = re.compile(
    r"(?i)\b(cfo|ceo|cto|head of\s+[\w -]{0,30}|finance lead|leadership|"
    r"exec team)\b")

_HEDGE_RE = re.compile(
    r"(?i)(\bshould we\b|\bcould we\b|\bcan we\b|\bshall we\b|\bwhat if\b|"
    r"\bdo you think\b|thoughts\?|\bwdyt\b|\bany objection|\bmaybe\b|"
    r"\bperhaps\b|\bi think we should\b|\bproposal\s*:)")

# Negation — "we've decided NOT to move to Net-45" / "Net-45 is banned" must
# never produce a patch for the value being rejected. A negated/ban phrase
# anywhere in the message vetoes detection (false-negative beats an inverted
# patch; humans can still teach it via /learn).
_NEG_RE = re.compile(
    r"(?i)\b(?:no|not|never|n't)\b[^.!?;]{0,40}?"
    r"(?:net[\s-]?\d+|move|switch|change|shift|allow|offer|increase|raise|"
    r"apply|adopt|approve)")
_BAN_RE = re.compile(r"(?i)\b(?:banned|forbidden|prohibited|disallowed)\b")

_MONEY_RE = re.compile(r"£\s?([\d,]+(?:\.\d+)?)")
_IBAN_RE = re.compile(
    r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b")
_DAY_RE = re.compile(
    r"(?i)\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b")

_DEFAULT_PLANS = ("Starter", "Growth", "Enterprise")


def _norm_iban(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


def _num(s):
    f = float(str(s).replace(",", ""))
    return int(f) if f.is_integer() else f


def _int(s):
    return int(str(s).replace(",", ""))


def _find_vendor(text: str, brain: dict):
    """Same as rules._find_vendor: first-word or full-name match against
    signed_contracts."""
    fn = getattr(rules, "_find_vendor", None)
    if fn:
        return fn(text, brain)
    for c in brain.get("signed_contracts", []):
        name = c["vendor_name"]
        if re.search(rf"(?i)\b{re.escape(name.split()[0])}\b", text) or \
                re.search(rf"(?i)\b{re.escape(name)}\b", text):
            return c
    return None


def _extract_candidates(text: str, brain: dict):
    """Yield (brain_key, new_value) for each extractor that fires, in spec
    order — first resolvable, value-changing candidate wins."""
    # 1. net terms — "net 45" plus the word term(s)
    m = re.search(r"(?i)\bnet[\s-]?(\d+)\b", text)
    if m and re.search(r"(?i)\bterms?\b", text):
        yield "financial_rules.max_payment_terms", f"Net-{int(m.group(1))}"

    # 2. discount cap
    m = re.search(
        r"(?i)discounts?\s+(?:over|above|of|up\s+to|capped\s+at)\s*"
        r"(\d+(?:\.\d+)?)\s*%", text)
    if not m:
        for mm in re.finditer(r"(?i)(\d+(?:\.\d+)?)\s*%\s*discount", text):
            lo, hi = max(0, mm.start() - 100), min(len(text), mm.end() + 100)
            if re.search(r"(?i)(cap|max|limit|approval|sign-?off)",
                         text[lo:hi]):
                m = mm
                break
    if m:
        yield "financial_rules.max_unapproved_discount_percent", \
            _num(m.group(1))

    # 3. cfo approval threshold
    m = re.search(r"(?i)(?:over|above)\s*£?\s*([\d,]+)\s*needs?\s+cfo\b",
                  text) or re.search(
        r"(?i)cfo\s+approval\s+(?:required\s+)?(?:over|above|for|on)\s*"
        r"£?\s*([\d,]+)", text)
    if m:
        yield "financial_rules.cfo_approval_required_over_gbp", _num(m.group(1))

    # 4. refund / credit cap
    if re.search(r"(?i)\b(refund|credit)s?\b", text) and \
            re.search(r"(?i)\b(cap|limit|approval)\b", text):
        m = _MONEY_RE.search(text)
        if m:
            yield "financial_rules.refund_or_credit_cap_gbp", _num(m.group(1))

    # 5. expense / spend approval limit
    if re.search(r"(?i)\b(expense|spend)\b", text) and \
            re.search(r"(?i)\b(limit|cap|approval)\b", text):
        m = _MONEY_RE.search(text)
        if m:
            yield "internal_policies.expense_approval_limit_gbp", \
                _num(m.group(1))

    # 6. per-seat pricing floor — plan name + £N/seat
    plans = brain.get("internal_policies", {}) \
        .get("pricing_floor_gbp_per_seat", {})
    names = [p for p in plans if isinstance(p, str)] or list(_DEFAULT_PLANS)
    plan = next((p for p in names
                 if re.search(rf"(?i)\b{re.escape(p)}\b", text)), None)
    if plan:
        m = re.search(r"(?i)£?\s?([\d,]+(?:\.\d+)?)\s*(?:/|per)\s*seat", text)
        if m:
            yield f"internal_policies.pricing_floor_gbp_per_seat.{plan}", \
                _num(m.group(1))

    # 7-9. vendor contract fields
    contract = _find_vendor(text, brain)
    if contract:
        vname = contract["vendor_name"]
        m = re.search(r"(?i)£\s?([\d,]+)\s*(?:/|per)\s*(?:mo|month)\b", text)
        if not m and re.search(r"(?i)\bretainer\b", text):
            # "retainer" near a £ figure, either side
            m = re.search(r"(?i)retainer\b[^£]{0,80}£\s?([\d,]+)", text) or \
                re.search(r"(?i)£\s?([\d,]+)[^£]{0,80}\bretainer\b", text)
        if m:
            yield (f"signed_contracts[{vname}]"
                   ".approved_monthly_retainer_gbp"), _int(m.group(1))
        m = re.search(r"(?i)£\s?([\d,]+)\s*(?:/|per)\s*h(?:ou)?r\b", text)
        if m:
            yield f"signed_contracts[{vname}].hourly_rate_gbp", \
                _int(m.group(1))
        ib = _IBAN_RE.search(text)
        if ib:
            yield f"signed_contracts[{vname}].bank_iban", \
                _norm_iban(ib.group(0))

    # 10. payment-run days
    if re.search(r"(?i)\bpayment\s+runs?\b", text):
        seen, days = set(), []
        for d in _DAY_RE.findall(text):
            day = d.capitalize()
            if day not in seen:
                seen.add(day)
                days.append(day)
        if days:
            yield "finance.payment_rules.payment_run_days", days


def _detect_deterministic(text: str, brain: dict) -> Optional[dict]:
    cue = _CUE_RE.search(text)
    if cue is None:
        return None
    if text.strip().endswith("?") or _HEDGE_RE.search(text):
        return None  # a question or a proposal-for-discussion, not a decision
    if _NEG_RE.search(text) or _BAN_RE.search(text):
        return None  # a decision to REJECT a value — never invert the intent
    for key, new in _extract_candidates(text, brain):
        try:
            old = brain_store.get_path(brain, key)
        except KeyError:
            continue  # brain key not in this brain — try the next extractor
        if old == new:
            continue  # nothing changes for this candidate — keep looking
        role = _ROLE_RE.search(text)
        return {
            "brain_key": key,
            "old": old,
            "new": new,
            "confidence": 0.9 if role else 0.75,
            "detector": "regex",
            "cue": cue.group(0),
            "author": role.group(0) if role else None,
        }
    return None


# --------------------------------------------------------------------------
# Optional LLM stage — only when the deterministic pass found nothing.
# Fails open exactly like llm_enrich: any error -> None.
# --------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None and os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            _client = OpenAI()
        except Exception:
            return None
    return _client


_LLM_SYSTEM = (
    "You are TribalSync, part of CommitGuard. Decide whether the feed message "
    "announces an AUTHORITATIVE company decision that changes a policy, "
    "threshold, or contract value already stored in the company brain. "
    "Questions, hedges, brainstorming, and proposals-for-discussion are NOT "
    "decisions -> is_decision=false. When it is a decision, map it to the "
    "existing brain key using dot paths (e.g. "
    "'financial_rules.max_payment_terms', "
    "'signed_contracts[CloudScale Ltd].bank_iban'), quote the current value "
    "as old_value, and the decided value as new_value."
)

_LLM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["is_decision", "brain_key", "old_value", "new_value",
                 "effective", "author", "confidence"],
    "properties": {
        "is_decision": {"type": "boolean"},
        "brain_key": {"type": "string"},
        "old_value": {"type": ["string", "number", "null"]},
        "new_value": {"type": ["string", "number", "null"]},
        "effective": {"type": ["string", "null"]},
        "author": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
    },
}


def llm_detect(text: str, brain: dict) -> Optional[dict]:
    """Optional second opinion — same detection shape, detector='llm'."""
    try:
        client = _get_client()
        if client is None:
            return None
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            timeout=4,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content":
                    f"Company brain:\n{json.dumps(brain)}\n\n"
                    f"Feed message:\n{text}"},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "tribal_sync_decision",
                    "strict": True,
                    "schema": _LLM_SCHEMA,
                },
            },
        )
        data = json.loads(resp.choices[0].message.content)
        if not data.get("is_decision"):
            return None
        key = data.get("brain_key")
        if not key:
            return None
        old = brain_store.get_path(brain, key)  # KeyError -> unresolvable
        new = data.get("new_value")
        if isinstance(old, (int, float)) and not isinstance(old, bool):
            try:
                new = _num(new)
            except (TypeError, ValueError):
                return None
        elif isinstance(old, str) and new is not None and \
                not isinstance(new, str):
            new = str(new)  # keep string-typed brain keys string-typed
        if new is None or new == old:
            return None
        conf = data.get("confidence")
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.6
        return {
            "brain_key": key,
            "old": old,
            "new": new,
            "confidence": conf if 0 < conf <= 1 else 0.6,
            "detector": "llm",
            "cue": data.get("effective"),
            "author": data.get("author"),
        }
    except Exception:
        return None


def detect_decision(text: str, brain: dict) -> Optional[dict]:
    """Deterministic first; LLM only when that found nothing. Never raises."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        det = _detect_deterministic(text, brain)
        if det is not None:
            return det
    except Exception:
        pass  # fail open into the LLM stage
    try:
        if llm_enabled():
            return llm_detect(text, brain)
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# Proposals — build / list / get / apply / reject
# --------------------------------------------------------------------------

def _load_proposals(proposals_path) -> list:
    try:
        data = json.loads(Path(proposals_path).read_text())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # don't silently overwrite corrupt history — park it aside
        try:
            Path(proposals_path).rename(
                Path(str(proposals_path) + ".corrupt.bak"))
        except OSError:
            pass
        return []
    except OSError:
        return []


def _save_proposals(proposals_path, proposals: list) -> None:
    _atomic_write_json(Path(proposals_path), proposals)


def _multiset(violations: list):
    return sorted((v.get("category"), v.get("severity")) for v in violations)


def _probe_parts(probe):
    """Tolerate (feed_id, text, context_type) tuples and dicts."""
    if isinstance(probe, dict):
        return (probe.get("feed_id", probe.get("id")),
                probe.get("text", ""),
                probe.get("context_type"))
    try:
        fid, ptext, ctx = probe
    except (TypeError, ValueError):
        return None, None, None
    return fid, ptext, ctx


def _affected(text, brain, key, new, probes, self_ctx="slack_message"):
    """Diff rule output between the current brain and a patched copy — which
    checks and which feed items would the patch flip?"""
    patched = copy.deepcopy(brain)
    _SET_PATH(patched, key, new)
    all_probes = list(probes or [])
    all_probes.append((None, text, self_ctx))  # implicit self-probe
    feed_ids, checks, seen_fids, seen_checks = [], [], set(), set()
    for probe in all_probes:
        fid, ptext, ctx = _probe_parts(probe)
        if not ptext:
            continue
        try:
            before = rules.run_rules(ptext, brain, ctx)
            after = rules.run_rules(ptext, patched, ctx)
            if fid is not None and _multiset(before) != _multiset(after) \
                    and fid not in seen_fids:
                seen_fids.add(fid)
                feed_ids.append(fid)
        except Exception:
            pass
        for fn in rules.ALL_CHECKS:
            if fn.__name__ in seen_checks:
                continue
            try:
                if _multiset(fn(ptext, brain)) != _multiset(fn(ptext, patched)):
                    seen_checks.add(fn.__name__)
                    checks.append(fn.__name__)
            except Exception:
                continue
    return feed_ids, checks


def build_proposal(text: str, brain: dict, meta: dict = None,
                   probes: list = None,
                   proposals_path=PROPOSALS_PATH) -> Optional[dict]:
    """Detect a decision and store a pending brain-patch proposal for it.
    Idempotent: a pending proposal for the same key + value is returned
    unchanged. Returns None when no decision is detected."""
    meta = meta or {}
    det = detect_decision(text, brain)
    if det is None:
        return None
    # probe outside the lock — it can run hundreds of rule evaluations
    try:
        feed_ids, checks = _affected(text, brain, det["brain_key"],
                                     det["new"], probes,
                                     meta.get("context_type") or
                                     "slack_message")
    except Exception:
        feed_ids, checks = [], []  # never let probing block a proposal
    with _LOCK:
        proposals = _load_proposals(proposals_path)
        for p in proposals:
            if p.get("status") == "pending" and \
                    p.get("brain_key") == det["brain_key"] and \
                    p.get("new") == det["new"]:
                return p  # dedupe — same decision already on the table
        proposal = {
            "id": "bp_" + uuid.uuid4().hex[:8],
            "status": "pending",
            "brain_key": det["brain_key"],
            "old": det["old"],
            "new": det["new"],
            "evidence": {
                "message": text,
                "author": meta.get("author"),
                "ts": meta.get("ts"),
                "source": meta.get("source"),
                "feed_id": meta.get("feed_id"),
            },
            "affected_checks": checks,
            "affected_feed_ids": feed_ids,
            "confidence": det["confidence"],
            "detector": det["detector"],
            "cue": det.get("cue"),
            "created_ts": datetime.now(timezone.utc).isoformat(),
            "decided_ts": None,
            "decided_by": None,
        }
        proposals.append(proposal)
        _save_proposals(proposals_path, proposals)
        return proposal


def list_proposals(status: str = None,
                   proposals_path=PROPOSALS_PATH) -> list:
    """Newest-first; optional status filter pending|applied|rejected."""
    proposals = _load_proposals(proposals_path)
    if status is not None:
        proposals = [p for p in proposals if p.get("status") == status]
    return list(reversed(proposals))


def get_proposal(pid: str, proposals_path=PROPOSALS_PATH) -> Optional[dict]:
    for p in _load_proposals(proposals_path):
        if p.get("id") == pid:
            return p
    return None


def _find_pending(pid, proposals_path):
    proposals = _load_proposals(proposals_path)
    prop = next((p for p in proposals if p.get("id") == pid), None)
    if prop is None:
        raise ValueError("not found")
    if prop.get("status") != "pending":
        raise ValueError(f"already {prop.get('status')}")
    return proposals, prop


def _audit_patch(prop, decided_by, result):
    if actions is None:
        return
    actions.audit({
        "action_type": "BRAIN_PATCH",
        "payload": {
            "proposal_id": prop.get("id"),
            "brain_key": prop.get("brain_key"),
            "old": prop.get("old"),
            "new": prop.get("new"),
            "decided_by": decided_by,
        },
        "result": result,
    })


def apply_proposal(pid: str, decided_by: str = "human",
                   proposals_path=PROPOSALS_PATH,
                   brain_path=brain_store.BRAIN_PATH,
                   changelog_path=brain_store.CHANGELOG_PATH) -> dict:
    """Human-approved brain patch: writes through brain_store (atomic brain
    rewrite + changelog entry), flips the proposal to 'applied', audits it."""
    with _LOCK:
        proposals, prop = _find_pending(pid, proposals_path)
        entry = brain_store.apply_patch(
            prop["brain_key"], prop["new"],
            meta={
                "expected_old": prop["old"],
                "proposal_id": pid,
                "decided_by": decided_by,
                "affected_feed_ids": prop.get("affected_feed_ids"),
                "author": (prop.get("evidence") or {}).get("author"),
            },
            brain_path=brain_path,
            changelog_path=changelog_path)
        prop["status"] = "applied"
        prop["decided_ts"] = datetime.now(timezone.utc).isoformat()
        prop["decided_by"] = decided_by
        _save_proposals(proposals_path, proposals)
    try:
        _audit_patch(prop, decided_by, "applied")
    except Exception:
        pass
    return {"applied": True, "proposal": prop, "changelog": entry}


def reject_proposal(pid: str, decided_by: str = "human",
                    proposals_path=PROPOSALS_PATH) -> dict:
    """Human rejection — status flips to 'rejected' and the decision is
    audited; the brain is never touched."""
    with _LOCK:
        proposals, prop = _find_pending(pid, proposals_path)
        prop["status"] = "rejected"
        prop["decided_ts"] = datetime.now(timezone.utc).isoformat()
        prop["decided_by"] = decided_by
        _save_proposals(proposals_path, proposals)
    try:
        _audit_patch(prop, decided_by, "rejected")
    except Exception:
        pass
    return {"rejected": True, "proposal": prop}


# --------------------------------------------------------------------------
# Self-test — runs entirely on tempfiles, never the real brain / proposals /
# changelog / audit log.
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import shutil

    # Keep the self-test deterministic: no real OpenAI calls, no real audit
    # rows. Env is restored implicitly when the process exits.
    os.environ.pop("OPENAI_API_KEY", None)

    tmp = Path(tempfile.mkdtemp(prefix="tribal_sync_selftest_"))
    try:
        brain_path = tmp / "brain.json"
        brain_path.write_text(
            (BASE / "company_brain.json").read_text())
        props_path = tmp / "proposals.json"
        changelog_path = tmp / "changelog.jsonl"
        if actions is not None:
            actions.AUDIT_PATH = tmp / "audit.jsonl"  # don't touch the real log

        brain = json.loads(brain_path.read_text())

        # --- detection: 3 positives + 1 hedge rejection ---------------------
        d1 = detect_decision(
            "CFO here: from today, payment terms are Net-45 for all "
            "suppliers.", brain)
        assert d1, "net-terms decision not detected"
        assert d1["brain_key"] == "financial_rules.max_payment_terms", d1
        assert d1["new"] == "Net-45" and d1["old"] == "Net-30", d1
        assert d1["detector"] == "regex" and d1["confidence"] == 0.9, d1
        assert d1["author"] and d1["author"].lower() == "cfo", d1

        d2 = detect_decision(
            "New policy going forward: discounts over 15% need sign-off "
            "from Amara.", brain)
        assert d2, "discount-cap decision not detected"
        assert d2["brain_key"] == \
            "financial_rules.max_unapproved_discount_percent", d2
        assert d2["new"] == 15 and d2["old"] == 10, d2

        d3 = detect_decision(
            "We've decided — effective this month CloudScale Ltd's "
            "retainer moves to £5,500/mo.", brain)
        assert d3, "retainer decision not detected"
        assert d3["brain_key"] == \
            "signed_contracts[CloudScale Ltd].approved_monthly_retainer_gbp", d3
        assert d3["new"] == 5500 and d3["old"] == 5000, d3

        assert detect_decision(
            "should we move to Net-45 for the Globex renewal?",
            brain) is None, "hedge/question was not rejected"
        assert detect_decision("", brain) is None

        # --- build_proposal + dedupe -----------------------------------------
        probe_text = "we can offer Net-45 terms to Acme Corp"
        p1 = build_proposal(
            "CFO here: from today, payment terms are Net-45 for all "
            "suppliers.", brain,
            meta={"author": "amara", "feed_id": 7, "source": "slack"},
            probes=[(11, probe_text, "slack_message")],
            proposals_path=props_path)
        assert p1 and p1["status"] == "pending", p1
        assert p1["brain_key"] == "financial_rules.max_payment_terms", p1
        assert "check_payment_terms" in p1["affected_checks"], p1
        assert 11 in p1["affected_feed_ids"], p1

        p1b = build_proposal(
            "CFO here: from today, payment terms are Net-45 for all "
            "suppliers.", brain,
            meta={"author": "amara"},
            proposals_path=props_path)
        assert p1b["id"] == p1["id"], "dedupe failed — second proposal created"

        assert get_proposal(p1["id"], props_path)["id"] == p1["id"]
        assert list_proposals(proposals_path=props_path)[0]["id"] == p1["id"]

        # --- apply flips the verdict on the temp brain -----------------------
        before = rules.run_rules(probe_text, brain, "slack_message")
        assert any(v["category"] == "FINANCIAL_POLICY" for v in before)

        res = apply_proposal(p1["id"], decided_by="selftest",
                             proposals_path=props_path,
                             brain_path=brain_path,
                             changelog_path=changelog_path)
        assert res["applied"] is True
        assert res["changelog"]["brain_key"] == \
            "financial_rules.max_payment_terms"
        patched = json.loads(brain_path.read_text())
        assert patched["financial_rules"]["max_payment_terms"] == "Net-45"
        after = rules.run_rules(probe_text, patched, "slack_message")
        assert not any(v["category"] == "FINANCIAL_POLICY" for v in after), \
            "verdict did not flip after patch"
        assert get_proposal(p1["id"], props_path)["status"] == "applied"
        assert changelog_path.exists()

        # --- reject path ------------------------------------------------------
        p2 = build_proposal(
            "New policy going forward: discounts over 15% need sign-off "
            "from Amara.", brain,
            meta={"author": "amara"},
            proposals_path=props_path)
        rej = reject_proposal(p2["id"], decided_by="selftest",
                              proposals_path=props_path)
        assert rej["rejected"] is True
        assert get_proposal(p2["id"], props_path)["status"] == "rejected"

        # --- validation: already-decided + missing ids ------------------------
        for fn, pid in ((apply_proposal, p1["id"]),
                        (reject_proposal, p2["id"])):
            try:
                fn(pid, proposals_path=props_path,
                   **({"brain_path": brain_path,
                       "changelog_path": changelog_path}
                      if fn is apply_proposal else {}))
                raise AssertionError("expected ValueError")
            except ValueError as e:
                assert "already" in str(e), e
        try:
            apply_proposal("bp_missing", proposals_path=props_path,
                           brain_path=brain_path,
                           changelog_path=changelog_path)
            raise AssertionError("expected ValueError")
        except ValueError as e:
            assert str(e) == "not found", e

        # status filter: 1 applied, 1 rejected, 0 pending
        assert len(list_proposals("pending", props_path)) == 0
        assert len(list_proposals("applied", props_path)) == 1
        assert len(list_proposals("rejected", props_path)) == 1
        assert len(list_proposals(proposals_path=props_path)) == 2

        # real proposals file must NOT have been created by the self-test
        assert not PROPOSALS_PATH.exists() or \
            get_proposal(p1["id"]) is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("SELFTEST PASS")
