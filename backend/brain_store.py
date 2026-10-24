"""Single writer for company_brain.json (owner: Riyansh).

Every mutation of the brain goes through this module — nothing else may
write the file. learned_rules writes in rules.py delegate here via
rules._write_brain — do not duplicate the write logic elsewhere.

Patches UPDATE existing keys only (set_path raises KeyError on anything
missing), and every applied patch appends an entry to brain_changelog.jsonl
so demo changes can be rewound with revert_all().
"""

import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path(__file__).parent
BRAIN_PATH = BASE / "company_brain.json"
CHANGELOG_PATH = BASE / "brain_changelog.jsonl"

# List selectors resolve by index ([0]) or by the first dict element whose
# vendor_name / feature / id equals the bracket text.
_IDENTITY_KEYS = ("vendor_name", "feature", "id")
_INDEX_RE = re.compile(r"-?\d+")

_LOCK = threading.Lock()
_ON_CHANGE_HOOKS: list = []


def register_on_change(fn) -> None:
    """Register fn(brain_key, old, new, meta) run after each applied patch.

    Hooks are collected under the lock but called AFTER the file write +
    changelog append, each wrapped in try/except so a crashing hook can
    neither break apply_patch nor block the other hooks.
    """
    _ON_CHANGE_HOOKS.append(fn)


def _tokenize(key: str) -> list:
    """Split a dotted path into ('key', name) / ('sel', text) tokens.

    "signed_contracts[CloudScale Ltd].bank_iban" ->
    [key signed_contracts, sel CloudScale Ltd, key bank_iban]
    """
    tokens = []
    buf = ""
    i = 0
    while i < len(key):
        ch = key[i]
        if ch == ".":
            if buf:
                tokens.append(("key", buf))
                buf = ""
            i += 1
        elif ch == "[":
            if buf:
                tokens.append(("key", buf))
                buf = ""
            end = key.find("]", i)
            if end < 0:
                raise KeyError(f"malformed selector in {key!r}")
            tokens.append(("sel", key[i + 1:end]))
            i = end + 1
        else:
            buf += ch
            i += 1
    if buf:
        tokens.append(("key", buf))
    return tokens


def _select_index(items: list, sel: str) -> int:
    """List index for a bracket selector: numeric index or dict identity."""
    if _INDEX_RE.fullmatch(sel):
        idx = int(sel)
        if -len(items) <= idx < len(items):
            return idx
        raise KeyError(f"index [{sel}] out of range")
    for i, item in enumerate(items):
        if isinstance(item, dict) and any(
                item.get(k) == sel for k in _IDENTITY_KEYS):
            return i
    raise KeyError(f"no list item matching [{sel}]")


def _walk(brain: dict, tokens: list):
    """Resolve a token list against the brain; KeyError on any miss."""
    cur = brain
    for kind, val in tokens:
        if kind == "key":
            if not isinstance(cur, dict) or val not in cur:
                raise KeyError(val)
            cur = cur[val]
        else:
            if not isinstance(cur, list):
                raise KeyError(val)
            cur = cur[_select_index(cur, val)]
    return cur


def get_path(brain: dict, key: str) -> Any:
    """Value at a dotted path like "a.b[0]" or "a.b[Name].c"."""
    return _walk(brain, _tokenize(key))


def set_path(brain: dict, key: str, value) -> Any:
    """Update an existing leaf and return its old value.

    Raises KeyError if the key does not already exist — patches only
    UPDATE existing keys, they never create new structure.
    """
    tokens = _tokenize(key)
    if not tokens:
        raise KeyError(key)
    parent = _walk(brain, tokens[:-1])
    kind, val = tokens[-1]
    if kind == "key":
        if not isinstance(parent, dict) or val not in parent:
            raise KeyError(val)
        old = parent[val]
        parent[val] = value
        return old
    if not isinstance(parent, list):
        raise KeyError(val)
    idx = _select_index(parent, val)
    old = parent[idx]
    parent[idx] = value
    return old


def write_brain(brain: dict, path=BRAIN_PATH) -> None:
    """Atomically rewrite company_brain.json (temp file + os.replace)."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(brain, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def mutate_brain(fn, brain_path=BRAIN_PATH):
    """Run fn(brain) -> (result, changed, hook_args) under the module lock.

    The whole read→modify→write happens in one critical section, so a
    concurrent apply_patch/revert_all can't be clobbered by a stale
    snapshot (rules.add_learned_* go through here). The brain is written
    atomically only when `changed`; hook_args is either None or a
    (brain_key, old, new, meta) tuple fanned out to on-change hooks
    after the lock is released. Returns fn's result.
    """
    with _LOCK:
        brain_path = Path(brain_path)
        brain = json.loads(brain_path.read_text())
        result, changed, hook_args = fn(brain)
        if changed:
            write_brain(brain, brain_path)
        hooks = list(_ON_CHANGE_HOOKS) if hook_args else []
    for fn_ in hooks:
        try:
            fn_(*hook_args)
        except Exception:
            continue  # a hook crash must not break the mutation
    return result


def apply_patch(brain_key: str, new_value, meta: dict = None,
                brain_path=BRAIN_PATH, changelog_path=CHANGELOG_PATH) -> dict:
    """Apply one brain update under the module lock; returns the changelog entry.

    KeyError propagates for unknown keys. meta["expected_old"] is an
    optimistic-concurrency guard: a mismatch raises ValueError("conflict:
    brain moved since proposal"). Patching to the current value is a
    no-op that writes nothing and returns {"changed": False, ...}.
    """
    meta = meta or {}
    with _LOCK:
        brain_path = Path(brain_path)
        brain = json.loads(brain_path.read_text())
        old = get_path(brain, brain_key)
        if "expected_old" in meta and meta["expected_old"] != old:
            raise ValueError("conflict: brain moved since proposal")
        if new_value == old:
            return {"changed": False, "brain_key": brain_key,
                    "old": old, "new": new_value}
        set_path(brain, brain_key, new_value)
        write_brain(brain, brain_path)
        entry = {
            "id": "chg_" + uuid.uuid4().hex[:8],
            "ts": datetime.now(timezone.utc).isoformat(),
            "brain_key": brain_key,
            "old": old,
            "new": new_value,
            "changed": True,
            "meta": meta,
        }
        with Path(changelog_path).open("a") as f:
            f.write(json.dumps(entry) + "\n")
        hooks = list(_ON_CHANGE_HOOKS)
    for fn in hooks:
        try:
            fn(brain_key, old, new_value, meta)
        except Exception:
            continue  # a hook crash must not break apply
    return entry


def _read_changelog(path) -> list:
    """All changelog entries oldest-first; [] on missing/corrupt file."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        lines = path.read_text().strip().splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(e, dict):
            entries.append(e)
    return entries


def changelog(limit: int = 100, path=CHANGELOG_PATH) -> list:
    """Newest-first changelog entries; fail-open on missing/corrupt file."""
    entries = _read_changelog(path)
    return entries[-limit:][::-1] if limit > 0 else []


def revert_all(brain_path=BRAIN_PATH, changelog_path=CHANGELOG_PATH) -> dict:
    """Undo every logged patch: restore each key's OLDEST "old" value.

    One write_brain call for all keys, then the changelog is truncated.
    Missing changelog -> {"reverted": [], "restored": {}}.
    """
    brain_path = Path(brain_path)
    changelog_path = Path(changelog_path)
    if not changelog_path.exists():
        return {"reverted": [], "restored": {}}
    with _LOCK:
        restored = {}
        order = []
        for e in _read_changelog(changelog_path):
            k = e.get("brain_key")
            if k is not None and k not in restored:
                restored[k] = e.get("old")
                order.append(k)
        reverted = []
        pre_revert = {}
        if restored:
            brain = json.loads(brain_path.read_text())
            for k in order:
                try:
                    pre_revert[k] = get_path(brain, k)
                    set_path(brain, k, restored[k])
                except KeyError:
                    continue  # structure moved underneath us; skip that key
                reverted.append(k)
            write_brain(brain, brain_path)
        changelog_path.write_text("")
        hooks = list(_ON_CHANGE_HOOKS)
    meta = {"source": "revert_all"}
    for k in reverted:
        for fn_ in hooks:
            try:
                fn_(k, pre_revert[k], restored[k], meta)
            except Exception:
                continue
    return {"reverted": reverted,
            "restored": {k: restored[k] for k in reverted}}


if __name__ == "__main__":
    import shutil

    tmpdir = Path(tempfile.mkdtemp(prefix="brain_store_selftest_"))
    try:
        brain_path = tmpdir / "company_brain.json"
        log_path = tmpdir / "brain_changelog.jsonl"
        brain = {
            "financial_rules": {"max_payment_terms": "Net-30"},
            "signed_contracts": [
                {"vendor_name": "CloudScale Ltd",
                 "bank_iban": "GB29REVOLUT12345689"},
                {"vendor_name": "Northwind Analytics",
                 "bank_iban": "GB14MONODE87654321"},
            ],
            "engineering_status": [
                {"feature": "Bulkhead v2", "status": "Planning — not started"},
            ],
            "finance": {"invoices": [
                {"id": "INV-1043", "status": "unpaid"},
            ]},
        }
        write_brain(brain, brain_path)

        # get_path: dotted keys, numeric index, identity selectors
        assert get_path(brain, "financial_rules.max_payment_terms") == "Net-30"
        assert get_path(brain, "signed_contracts[0].bank_iban") == "GB29REVOLUT12345689"
        assert get_path(brain, "signed_contracts[CloudScale Ltd].bank_iban") == "GB29REVOLUT12345689"
        assert get_path(brain, "engineering_status[Bulkhead v2].status") == "Planning — not started"
        assert get_path(brain, "finance.invoices[INV-1043].status") == "unpaid"
        for bad in ("nope", "signed_contracts[Globex]",
                    "signed_contracts[9]", "signed_contracts[0].nope"):
            try:
                get_path(brain, bad)
                raise AssertionError(f"{bad} should raise KeyError")
            except KeyError:
                pass

        # set_path round-trip returns old; never creates new keys
        assert set_path(brain, "financial_rules.max_payment_terms", "Net-45") == "Net-30"
        assert get_path(brain, "financial_rules.max_payment_terms") == "Net-45"
        set_path(brain, "financial_rules.max_payment_terms", "Net-30")
        try:
            set_path(brain, "financial_rules.brand_new", 1)
            raise AssertionError("set_path must not create keys")
        except KeyError:
            pass

        # hooks: crashy hook must not break apply or block later hooks
        fired = []
        register_on_change(lambda *a: 1 / 0)
        register_on_change(lambda k, o, n, m: fired.append((k, o, n, m)))

        e1 = apply_patch("signed_contracts[CloudScale Ltd].bank_iban",
                         "GB00TESTIBAN", meta={"actor": "selftest"},
                         brain_path=brain_path, changelog_path=log_path)
        assert e1["changed"] is True and e1["id"].startswith("chg_")
        assert e1["old"] == "GB29REVOLUT12345689"
        assert e1["meta"] == {"actor": "selftest"}
        disk = json.loads(brain_path.read_text())
        assert get_path(disk, "signed_contracts[CloudScale Ltd].bank_iban") == "GB00TESTIBAN"
        assert fired == [("signed_contracts[CloudScale Ltd].bank_iban",
                          "GB29REVOLUT12345689", "GB00TESTIBAN",
                          {"actor": "selftest"})]

        # optimistic concurrency: stale expected_old conflicts
        try:
            apply_patch("signed_contracts[CloudScale Ltd].bank_iban", "X",
                        meta={"expected_old": "STALE"},
                        brain_path=brain_path, changelog_path=log_path)
            raise AssertionError("expected_old mismatch must raise ValueError")
        except ValueError as ex:
            assert "conflict" in str(ex)

        # matching expected_old goes through
        apply_patch("signed_contracts[CloudScale Ltd].bank_iban", "GB00V2",
                    meta={"expected_old": "GB00TESTIBAN"},
                    brain_path=brain_path, changelog_path=log_path)

        # idempotent no-change: returns changed=False, writes nothing
        lines_before = log_path.read_text().count("\n")
        hooks_before = len(fired)
        noop = apply_patch("signed_contracts[CloudScale Ltd].bank_iban",
                           "GB00V2",
                           brain_path=brain_path, changelog_path=log_path)
        assert noop == {"changed": False,
                        "brain_key": "signed_contracts[CloudScale Ltd].bank_iban",
                        "old": "GB00V2", "new": "GB00V2"}
        assert log_path.read_text().count("\n") == lines_before
        assert len(fired) == hooks_before  # no hooks for a no-op

        # changelog: newest-first
        log = changelog(path=log_path)
        assert len(log) == 2
        assert log[0]["new"] == "GB00V2" and log[1]["new"] == "GB00TESTIBAN"
        assert changelog(path=tmpdir / "missing.jsonl") == []

        # revert_all restores the ORIGINAL value and truncates the log
        res = revert_all(brain_path=brain_path, changelog_path=log_path)
        key = "signed_contracts[CloudScale Ltd].bank_iban"
        assert res == {"reverted": [key],
                       "restored": {key: "GB29REVOLUT12345689"}}
        disk = json.loads(brain_path.read_text())
        assert get_path(disk, key) == "GB29REVOLUT12345689"
        assert log_path.read_text() == ""
        assert changelog(path=log_path) == []
        assert revert_all(brain_path=brain_path,
                          changelog_path=tmpdir / "nope.jsonl") == \
            {"reverted": [], "restored": {}}

        print("SELFTEST PASS")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
