"""Invoice chaser — receivables ageing + chase drafting (owner: Riyansh).

Reads finance.invoices receivables from the company brain, computes days
overdue and ageing buckets, remembers what's been said before (chase_log on
each invoice + feed history scan), and drafts a chase email on a tone
ladder (friendly reminder -> firm -> final notice, escalating to the CFO).

OpenAI structured output is used when OPENAI_API_KEY is set; a deterministic
template is the fallback — the module works fully offline and NEVER sends
email or any other message. It only produces drafts.

Paid/promise detection: feed/Slack text like "Acme paid INV-1043" flips an
invoice to paid; "Acme will pay Friday" lands a promise in chase_log so the
next draft references it. All brain writes go through rules._write_brain
(tmp + os.replace, atomic) so chase_log survives restarts and rides the
Lightfern brain export.
"""

import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import rules
from llm_enrich import _get_client  # same fail-open client as the LLM stage

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"

BUCKETS = ("current", "1-30", "31-60", "60+")
TONES = ("friendly_reminder", "firm", "final_notice")
MAX_CHASE_LOG = 50


# ---- receivables + ageing ---------------------------------------------------


def _parse_due(inv: dict) -> Optional[date]:
    try:
        return date.fromisoformat(str(inv.get("due_date", ""))[:10])
    except ValueError:
        return None


def _bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    return "60+"


def _chases(inv: dict) -> list:
    return [e for e in inv.get("chase_log") or []
            if isinstance(e, dict) and e.get("kind") == "chase"]


def _promises(inv: dict) -> list:
    return [e for e in inv.get("chase_log") or []
            if isinstance(e, dict) and e.get("kind") == "promise"]


def _enrich(inv: dict, today: date) -> dict:
    due = _parse_due(inv)
    days = max(0, (today - due).days) if due else 0
    promises = _promises(inv)
    return {
        "invoice_id": inv.get("id"),
        "counterparty": inv.get("counterparty"),
        "amount_gbp": inv.get("amount_gbp"),
        "due_date": inv.get("due_date"),
        "status": inv.get("status"),
        "owner": inv.get("owner"),
        "contact": inv.get("contact") or {},
        "days_overdue": days,
        "bucket": _bucket(days),
        "chases_sent": len(_chases(inv)),
        "last_promise": promises[-1].get("promise_text") or
                        promises[-1].get("note") if promises else None,
        "chase_log": list(inv.get("chase_log") or []),
    }


def receivables(brain: dict, today: Optional[date] = None) -> list:
    """Open receivables (kind=receivable, not paid), most overdue first."""
    today = today or date.today()
    out = [_enrich(i, today)
           for i in brain.get("finance", {}).get("invoices", [])
           if i.get("kind") == "receivable" and i.get("status") != "paid"]
    out.sort(key=lambda r: (-r["days_overdue"], -(r["amount_gbp"] or 0)))
    return out


def ageing(brain: dict, today: Optional[date] = None) -> dict:
    """GET /receivables payload — buckets + totals + the enriched list."""
    today = today or date.today()
    items = receivables(brain, today)
    buckets = {b: {"count": 0, "amount_gbp": 0} for b in BUCKETS}
    for it in items:
        buckets[it["bucket"]]["count"] += 1
        buckets[it["bucket"]]["amount_gbp"] += it["amount_gbp"] or 0
    total = sum(i["amount_gbp"] or 0 for i in items)
    overdue = sum(i["amount_gbp"] or 0 for i in items if i["days_overdue"] > 0)
    return {"as_of": today.isoformat(), "total_outstanding_gbp": total,
            "overdue_gbp": overdue, "open_count": len(items),
            "buckets": buckets, "items": items}


def find_invoice(brain: dict, ref: str) -> Optional[dict]:
    """Resolve a user ref — 'INV-1048', '1048', or a counterparty fragment
    ('acme', 'Globex') — to the open receivable it most likely means."""
    ref = (ref or "").strip()
    if not ref:
        return None
    low = ref.lower()
    cands = [i for i in brain.get("finance", {}).get("invoices", [])
             if i.get("kind") == "receivable" and i.get("status") != "paid"]
    for inv in cands:  # exact invoice id first (with or without prefix)
        iid = str(inv.get("id", ""))
        if iid.lower() == low or (low.isdigit() and iid.lower().endswith(low)):
            return inv
    today = date.today()
    matches = [i for i in cands
               if low in str(i.get("counterparty", "")).lower()
               or low == str(i.get("counterparty", "")).split()[0].lower()]
    if matches:  # a customer name means their MOST overdue invoice
        matches.sort(key=lambda i: -(
            (today - _parse_due(i)).days if _parse_due(i) else 0))
        return matches[0]
    return None


# ---- context: "what's been said before" -------------------------------------


def scan_context(inv: dict, feed_items: list, limit: int = 5) -> list:
    """Feed/Slack messages mentioning this customer or invoice no —
    newest first, capped. Pure scan, no state."""
    if not feed_items:
        return []
    name = str(inv.get("counterparty", ""))
    iid = str(inv.get("id", ""))
    first = name.split()[0] if name else ""
    hits = []
    for item in feed_items:
        text = str(item.get("text") or "")
        if not text:
            continue
        if (iid and iid.lower() in text.lower()) or \
           (first and re.search(rf"(?i)\b{re.escape(first)}\b", text)):
            hits.append({"ts": item.get("ts"), "source": item.get("source"),
                         "user": item.get("user"), "text": text[:240]})
            if len(hits) >= limit:
                break
    return hits


# ---- tone ladder -------------------------------------------------------------


def tone_for(days_overdue: int, chases_sent: int) -> str:
    """friendly_reminder -> firm -> final_notice, driven by how overdue the
    invoice is AND how many chases have already gone out."""
    if days_overdue > 60 or chases_sent >= 3:
        return "final_notice"
    if days_overdue > 30 or chases_sent >= 2:
        return "firm"
    if days_overdue > 0 or chases_sent >= 1:
        return "friendly_reminder"
    return "friendly_reminder"


def _escalates(tone: str) -> bool:
    return tone == "final_notice"


# ---- drafting ----------------------------------------------------------------


def _money(n) -> str:
    return f"£{(n or 0):,}"


def _fmt_due(inv: dict) -> str:
    return str(inv.get("due_date") or "an unknown date")


def template_draft(inv: dict, days_overdue: int, tone: str,
                   prior_chases: int, promise: Optional[str],
                   brain: dict) -> dict:
    """Deterministic chase draft — the offline path. Cites invoice no,
    amount, due date, days overdue and any prior promise."""
    name = inv.get("counterparty", "your team")
    contact = (inv.get("contact") or {}).get("name") or "there"
    iid = inv.get("id")
    amt = _money(inv.get("amount_gbp"))
    due = _fmt_due(inv)
    promise_line = (f"We noted your message — \u201c{promise}\u201d — "
                    "but the payment hasn't landed yet.\n\n"
                    if promise else "")
    if tone == "final_notice":
        subject = f"Final notice — {iid} ({amt}) {days_overdue} days overdue"
        body = (
            f"Hi {contact},\n\n"
            f"This is a final notice for invoice {iid} ({amt}), due {due} — "
            f"now {days_overdue} days overdue.\n\n"
            f"{promise_line}"
            f"Unless payment or a firm date reaches us within 3 working days, "
            f"this is being escalated to our CFO "
            f"{brain.get('people', {}).get('cfo', '')} and further work with "
            f"{name} will be paused.\n\n"
            f"Thanks,\n{inv.get('owner') or 'Finance'}")
    elif tone == "firm":
        subject = f"Overdue: {iid} ({amt}) — {days_overdue} days past due"
        body = (
            f"Hi {contact},\n\n"
            f"Invoice {iid} for {amt} was due {due} and is now "
            f"{days_overdue} days overdue.\n\n"
            f"{promise_line}"
            f"Please arrange payment this week or reply with a firm payment "
            f"date.\n\n"
            f"Thanks,\n{inv.get('owner') or 'Finance'}")
    else:
        subject = (f"Friendly reminder — {iid} ({amt})"
                   + (f" due {due}" if days_overdue == 0 else
                      f" — {days_overdue} days overdue"))
        body = (
            f"Hi {contact},\n\n"
            f"A friendly nudge on invoice {iid} for {amt}, due {due}"
            + (f" — {days_overdue} days ago" if days_overdue else "")
            + ".\n\n"
            f"{promise_line}"
            f"Could you confirm it's in the payment run?\n\n"
            f"Thanks,\n{inv.get('owner') or 'Finance'}")
    return {"subject": subject, "body": body, "tone": tone}


LLM_CHASE_PROMPT = (
    "You are CommitGuard's receivables chaser. Draft a payment-chase email "
    "for the invoice described. Match the requested tone exactly "
    "(friendly_reminder | firm | final_notice). The draft MUST cite the "
    "invoice number, the GBP amount, the due date and how many days overdue "
    "it is; if a prior customer promise is given, reference it plainly. "
    "Return cites[] naming the evidence you used (e.g. "
    "'finance.invoices[INV-1048].due_date', 'chase_log promise'). Never "
    "invent payment details, discounts or threats. This is a DRAFT for a "
    "human — it is never sent automatically."
)

LLM_CHASE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "body", "tone", "cites"],
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "tone": {"type": "string",
                 "enum": ["friendly_reminder", "firm", "final_notice"]},
        "cites": {"type": "array", "items": {"type": "string"}},
    },
}


def _llm_draft(inv: dict, days_overdue: int, tone: str, prior_chases: int,
               promise: Optional[str], context: list, brain: dict) -> Optional[dict]:
    """OpenAI structured-output draft. Fail-open: any problem -> None."""
    try:
        client = _get_client()
        if client is None:
            return None
        facts = {
            "invoice_id": inv.get("id"), "customer": inv.get("counterparty"),
            "amount_gbp": inv.get("amount_gbp"), "due_date": inv.get("due_date"),
            "days_overdue": days_overdue, "requested_tone": tone,
            "prior_chases": prior_chases,
            "prior_promise": promise,
            "escalate_to": (brain.get("people", {}).get("cfo")
                            if tone == "final_notice" else None),
            "contact_name": (inv.get("contact") or {}).get("name"),
            "owner": inv.get("owner"),
            "recent_channel_mentions": [c.get("text") for c in context[:3]],
        }
        resp = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.2, timeout=4,
            messages=[{"role": "system", "content": LLM_CHASE_PROMPT},
                      {"role": "user", "content": json.dumps(facts)}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "commit_guard_chase",
                                             "strict": True,
                                             "schema": LLM_CHASE_SCHEMA}})
        data = json.loads(resp.choices[0].message.content)
        if not (data.get("subject") and data.get("body")):
            return None
        data["tone"] = data.get("tone") if data.get("tone") in TONES else tone
        return data
    except Exception:
        return None


def draft_chase(brain: dict, ref: str, feed_items: Optional[list] = None,
                today: Optional[date] = None) -> dict:
    """The chase draft for an invoice id or customer name. DRAFT ONLY —
    returns {draft_only: True, ...} and this module has no send function."""
    inv = find_invoice(brain, ref)
    if inv is None:
        return {"error": f"no open receivable matching '{ref}'"}
    today = today or date.today()
    enr = _enrich(inv, today)
    days, n_chases = enr["days_overdue"], enr["chases_sent"]
    tone = tone_for(days, n_chases)
    promise = enr["last_promise"]
    context = scan_context(inv, feed_items or [])

    engine = "template"
    drafted = _llm_draft(inv, days, tone, n_chases, promise, context, brain)
    if drafted and all(k in json.dumps(drafted) for k in (inv["id"],)):
        engine = "rules+llm"
    else:
        drafted = template_draft(inv, days, tone, n_chases, promise, brain)

    cites = [
        f"finance.invoices[{inv['id']}].amount_gbp={_money(inv.get('amount_gbp'))}",
        f"finance.invoices[{inv['id']}].due_date={_fmt_due(inv)} "
        f"({days} days overdue)",
        f"finance.invoices[{inv['id']}].status={inv.get('status')}",
    ]
    if promise:
        cites.append(f"finance.invoices[{inv['id']}].chase_log "
                     f"promise: \"{promise}\"")
    if n_chases:
        cites.append(f"finance.invoices[{inv['id']}].chase_log "
                     f"({n_chases} prior chase{'s' if n_chases != 1 else ''})")
    for c in (drafted.get("cites") or []):
        if isinstance(c, str) and c not in cites:
            cites.append(c)

    cfo = brain.get("people", {}).get("cfo")
    return {
        "draft_only": True,           # never sent — a human owns the send
        "engine": engine,
        "invoice_id": inv.get("id"),
        "customer": inv.get("counterparty"),
        "contact": inv.get("contact") or {},
        "owner": inv.get("owner"),
        "amount_gbp": inv.get("amount_gbp"),
        "due_date": inv.get("due_date"),
        "days_overdue": days,
        "bucket": _bucket(days),
        "prior_chases": n_chases,
        "prior_promise": promise,
        "tone": drafted.get("tone") or tone,
        "escalate_to": cfo if _escalates(drafted.get("tone") or tone) else None,
        "subject": drafted["subject"],
        "body": drafted["body"],
        "cites": cites,
        "context": context,
        "reply_hint": "Reply `log` to mark it sent, `paid` if it's paid",
    }


# ---- learning: paid / promise detection + chase_log writes -------------------

# Invoice id or counterparty must appear for the text to apply to an invoice.
_PAID_RE = re.compile(
    r"(?i)\b(has\s+(?:been\s+)?paid|(?:just\s+)?paid|settled|"
    r"payment\s+(?:landed|arrived|received|cleared|came\s+through)|"
    r"wire\s+(?:landed|arrived|received)|remittance\s+received)\b")
_PROMISE_RE = re.compile(
    r"(?i)\b(will\s+pay|will\s+send|going\s+to\s+pay|promise[ds]?\w*|"
    r"pay(?:ing)?\s+(?:on|by|this|next|tomorrow|monday|tuesday|wednesday|"
    r"thursday|friday|after)|send\s+the\s+(?:wire|payment)|"
    r"wire\s+(?:goes\s+out|on|by|this|next)|payment\s+(?:on|by|this|next|"
    r"tomorrow|after))\b")


# Negated payment claims ("still hasn't paid", "payment never landed") must
# not count as paid — strip them before the paid regex runs.
_NEGATED_PAID_RE = re.compile(
    r"(?i)\b(?:hasn'?t|has\s+not|haven'?t|have\s+not|not\s+yet|never|"
    r"still\s+hasn'?t|didn'?t|did\s+not)\s+(?:been\s+)?(?:paid|settled)\b|"
    r"\b(?:payment|wire|remittance)\s+(?:never|hasn'?t|has\s+not|didn'?t|"
    r"did\s+not)\s+(?:landed|arrived|received|cleared)\b|"
    r"\bno\s+payment\s+(?:has\s+)?(?:landed|arrived|received)\b")


def _paid_hit(text: str) -> bool:
    cleaned = _NEGATED_PAID_RE.sub(" ", text)
    return bool(_PAID_RE.search(cleaned))


def _mentions(text: str, inv: dict) -> bool:
    iid = str(inv.get("id") or "")
    name = str(inv.get("counterparty") or "")
    first = name.split()[0] if name else ""
    return bool(
        (iid and iid.lower() in text.lower()) or
        (first and re.search(rf"(?i)\b{re.escape(first)}\b", text)))


def _clean_note(text: str) -> str:
    return re.sub(r"[\[\]]", "", text.strip())[:240]


def record_signal(brain: dict, text: str, source: str = "feed",
                  brain_path: Optional[Path] = None) -> list:
    """Scan feed/Slack text for paid / promise signals on open receivables.

    "Globex paid INV-1048" -> invoice status 'paid' (+chase_log 'paid' row,
    'chase_paid_from' so resets can restore). "Acme will pay Friday" ->
    chase_log 'promise' row the next draft references. Mutates `brain`
    in memory; when brain_path is given the change is persisted atomically
    (surgical single-line write when possible). Returns updates applied.
    """
    if not text or not isinstance(brain, dict):
        return []
    updates = []
    now = datetime.now(timezone.utc).isoformat()
    note = _clean_note(text)
    for inv in brain.get("finance", {}).get("invoices", []):
        if inv.get("kind") != "receivable" or inv.get("status") == "paid":
            continue
        if not _mentions(text, inv):
            continue
        if _paid_hit(text):
            def mut(o, _note=note, _now=now, _src=source):
                prev = o.get("status")
                o["status"] = "paid"
                o["chase_paid_from"] = prev
                log = o.setdefault("chase_log", [])
                log.append({"kind": "paid", "ts": _now, "note": _note,
                            "source": _src})
                del log[:-MAX_CHASE_LOG]
                return {"invoice_id": o["id"], "kind": "paid",
                        "from_status": prev}
        elif _PROMISE_RE.search(text):
            log = inv.setdefault("chase_log", [])
            if any(e.get("kind") == "promise" and e.get("note") == note
                   for e in log):
                continue  # dedupe — the sim feed replays scenarios
            m = _PROMISE_RE.search(text)
            # promise_text = the rest of the promise sentence ("will pay
            # INV-1051 on Friday") — the next draft quotes it directly.
            seg = re.split(r"[.\n!;]", text[m.start():])[0]
            promise_text = _clean_note(seg)

            def mut(o, _note=note, _now=now, _src=source, _pt=promise_text):
                log = o.setdefault("chase_log", [])
                log.append({"kind": "promise", "ts": _now, "note": _note,
                            "source": _src, "promise_text": _pt})
                del log[:-MAX_CHASE_LOG]
                return {"invoice_id": o["id"], "kind": "promise",
                        "promise_text": _pt}
        else:
            continue
        if brain_path:
            obj, res = _mutate_invoice(inv["id"], Path(brain_path), mut)
            if obj is not None:  # sync the in-memory brain too
                inv["status"] = obj.get("status")
                if "chase_paid_from" in obj:
                    inv["chase_paid_from"] = obj["chase_paid_from"]
                inv["chase_log"] = obj.get("chase_log", [])
                updates.append(res)
        else:
            updates.append(mut(inv))
    return updates


def _atomic_write_text(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _mutate_invoice(ref: str, brain_path: Path, mutate):
    """Run mutate(invoice) on the receivable matching `ref` and persist.

    Surgical write: when the invoice is a single-line JSON object (the
    committed brain style) only that line is rewritten — the rest of the
    file stays byte-identical. Falls back to rules._write_brain (full
    reserialize) once the file has been normalised. Returns
    (invoice_dict, mutate_result) or (None, None)."""
    brain_path = Path(brain_path)
    src = brain_path.read_text()
    low = (ref or "").strip().lower()
    lines = src.splitlines(keepends=True)
    cands = []
    for n, line in enumerate(lines):
        if '"kind": "receivable"' not in line:
            continue
        try:
            obj = json.loads(line.strip().rstrip(","))
        except Exception:
            cands = None      # normalised multi-line file — bail out
            break
        if not isinstance(obj, dict) or "id" not in obj:
            continue
        iid = str(obj["id"]).lower()
        name = str(obj.get("counterparty", "")).lower()
        if (iid == low or (low.isdigit() and iid.endswith(low))
                or (low and low in name)
                or (low and low == name.split()[0])):
            cands.append((n, obj))
    if cands:
        exact = [c for c in cands if str(c[1]["id"]).lower() == low]
        today = date.today()
        n, obj = (exact[0] if exact else max(
            cands, key=lambda c: (today - _parse_due(c[1])).days
            if _parse_due(c[1]) else 0))
        result = mutate(obj)
        if result is None:
            return None, None
        trailing = "," if lines[n].rstrip().endswith(",") else ""
        nl = "\n" if lines[n].endswith("\n") else ""
        indent = lines[n][:len(lines[n]) - len(lines[n].lstrip())]
        lines[n] = indent + json.dumps(obj, ensure_ascii=False) + trailing + nl
        new_src = "".join(lines)
        json.loads(new_src)          # validate before touching the file
        _atomic_write_text(brain_path, new_src)
        return obj, result
    brain = json.loads(src)
    inv = find_invoice(brain, ref)
    if inv is None:
        return None, None
    result = mutate(inv)
    rules._write_brain(brain, brain_path)
    return inv, result


def log_chase(ref: str, draft: Optional[dict] = None, note: Optional[str] = None,
              channel: str = "manual", brain_path=BRAIN_PATH) -> Optional[dict]:
    """'Mark it sent' — append a chase entry to the invoice's chase_log."""
    def mut(inv):
        entry = {"id": "ch_" + uuid.uuid4().hex[:8], "kind": "chase",
                 "ts": datetime.now(timezone.utc).isoformat(),
                 "channel": channel,
                 "tone": (draft or {}).get("tone"),
                 "subject": (draft or {}).get("subject"),
                 "note": _clean_note(note or "chase logged as sent")}
        log = inv.setdefault("chase_log", [])
        log.append(entry)
        del log[:-MAX_CHASE_LOG]
        return entry
    _inv, entry = _mutate_invoice(ref, brain_path, mut)
    return entry


def mark_paid(ref: str, note: Optional[str] = None, brain_path=BRAIN_PATH) -> Optional[dict]:
    """Mark a receivable paid — it drops out of the overdue list; the
    previous status is kept in 'chase_paid_from' for resets."""
    def mut(inv):
        prev = inv.get("status")
        inv["status"] = "paid"
        inv["chase_paid_from"] = prev
        entry = {"id": "ch_" + uuid.uuid4().hex[:8], "kind": "paid",
                 "ts": datetime.now(timezone.utc).isoformat(),
                 "note": _clean_note(note or "marked paid")}
        log = inv.setdefault("chase_log", [])
        log.append(entry)
        del log[:-MAX_CHASE_LOG]
        return {"invoice_id": inv["id"], "from_status": prev, "entry": entry}
    _inv, res = _mutate_invoice(ref, brain_path, mut)
    return res


def history(brain: dict, ref: str) -> Optional[dict]:
    """GET /chase/{id}/history — the invoice plus its chase_log, oldest first."""
    inv = find_invoice(brain, ref) or next(
        (i for i in brain.get("finance", {}).get("invoices", [])
         if str(i.get("id", "")).lower() == (ref or "").strip().lower()), None)
    if inv is None:
        return None
    return {"invoice_id": inv.get("id"), "counterparty": inv.get("counterparty"),
            "status": inv.get("status"), "amount_gbp": inv.get("amount_gbp"),
            "due_date": inv.get("due_date"),
            "chase_log": list(inv.get("chase_log") or [])}


# ---- Slack -------------------------------------------------------------------


_CHASE_CMD_RE = re.compile(r"(?i)^\s*chase[:\s]+(.+?)\s*$")


def parse_chase_command(text: str) -> Optional[str]:
    """'chase INV-1048' / 'chase Acme' -> the ref to draft; else None."""
    m = _CHASE_CMD_RE.match(text or "")
    return m.group(1) if m else None


def build_chase_blocks(item: dict) -> list:
    """Block Kit reply for a `chase X` command — draft + how to close it out."""
    d = item.get("chase") or {}
    if d.get("error"):
        return [{"type": "section", "text": {"type": "mrkdwn",
                 "text": f"⚠️ {d['error']}"}}]
    blocks = [{
        "type": "header",
        "text": {"type": "plain_text", "emoji": True,
                 "text": f"📨 Chase draft — {d.get('invoice_id')} · "
                         f"{d.get('customer')}"},
    }, {
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": f"*Subject:* {d.get('subject')}"},
    }, {
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": (d.get("body") or "")[:2900]},
    }, {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text":
            f"Tone: *{d.get('tone')}* · {d.get('days_overdue')}d overdue · "
            f"{_money(d.get('amount_gbp'))} · {d.get('prior_chases')} prior "
            f"chase{'s' if d.get('prior_chases') != 1 else ''}"
            + (f" · escalates to {d['escalate_to']}" if d.get("escalate_to")
               else "")}],
    }]
    for c in (d.get("cites") or [])[:4]:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"Evidence: `{c}`"}]})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": "Draft only — nothing is sent. " +
                (d.get("reply_hint") or "")}]})
    return blocks


def ask_summary(brain: dict, today: Optional[date] = None) -> dict:
    """Ageing summary in the /ask response shape — 'who owes us money?' /
    'what's overdue?' get the receivables picture, not the payables one."""
    rep = ageing(brain, today)
    if not rep["items"]:
        answer = "No open receivables — nobody owes us money right now."
    else:
        top = "; ".join(
            f"{i['invoice_id']} {i['counterparty']} {_money(i['amount_gbp'])}"
            + (f" ({i['days_overdue']}d overdue)" if i["days_overdue"]
               else f" (due {i['due_date']})")
            for i in rep["items"][:5])
        answer = (f"{_money(rep['total_outstanding_gbp'])} outstanding across "
                  f"{rep['open_count']} open receivable"
                  f"{'s' if rep['open_count'] != 1 else ''} — "
                  f"{_money(rep['overdue_gbp'])} overdue. {top}.")
        if any(i["last_promise"] for i in rep["items"]):
            pr = next(i for i in rep["items"] if i["last_promise"])
            answer += (f" Latest promise: {pr['counterparty']} said they'd "
                       f"{pr['last_promise']}.")
    return {"answer": answer,
            "sources": [{"brain_key": "finance.invoices",
                         "value": rep["items"]}],
            "matched": True}
