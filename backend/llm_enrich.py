"""LLM enrichment layer (owner: Riyansh).

Optional second stage after the deterministic rules engine. Fails open:
no API key, openai package missing, no network, timeout, bad JSON
-> returns None -> rules-only result is served. Never raises.
"""

import json
import os
from typing import Optional

_client = None

SYSTEM_PROMPT = (
    "You are CommitGuard's secondary review layer. Deterministic rules already "
    "found the listed violations — do NOT repeat them. Report ONLY additional, "
    "concrete risks backed by the company brain (implied commitments, promises "
    "not backed by the brain, missing approvals). If there are none, return an "
    "empty list. Also produce a polished full rewrite that resolves ALL "
    "findings (rule + yours) while keeping the sender's tone; return null for "
    "full_rewrite if there is nothing to fix."
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["violations", "full_rewrite"],
    "properties": {
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["category", "severity", "issue", "correction",
                             "suggested_rewrite", "evidence"],
                "properties": {
                    "category": {"type": "string"},
                    "severity": {"type": "string", "enum": ["LOW", "MEDIUM"]},
                    "issue": {"type": "string"},
                    "correction": {"type": "string"},
                    "suggested_rewrite": {"type": ["string", "null"]},
                    "evidence": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["brain_key", "expected", "found"],
                        "properties": {
                            "brain_key": {"type": "string"},
                            "expected": {"type": "string"},
                            "found": {"type": "string"},
                        },
                    },
                },
            },
        },
        "full_rewrite": {"type": ["string", "null"]},
    },
}


def _get_client():
    global _client
    if _client is None and os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            _client = OpenAI()
        except Exception:
            return None
    return _client


def llm_enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY")) and _get_client() is not None


def llm_enrich(text: str, context_type: str, violations: list, brain: dict) -> Optional[dict]:
    try:
        client = _get_client()
        if client is None:
            return None
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Company brain:\n{json.dumps(brain)}\n\n"
                f"Deterministic rule violations already found (do not repeat):\n"
                f"{json.dumps(violations)}\n\n"
                f"Context type: {context_type}\n\n"
                f"Draft text:\n{text}"
            )},
        ]
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            timeout=4,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "commit_guard_enrich",
                    "strict": True,
                    "schema": SCHEMA,
                },
            },
        )
        data = json.loads(resp.choices[0].message.content)

        rule_categories = {v.get("category") for v in violations}
        rule_brain_keys = {(v.get("evidence") or {}).get("brain_key") for v in violations}
        survivors = []
        for v in data.get("violations") or []:
            if v.get("category") in rule_categories:
                continue
            if (v.get("evidence") or {}).get("brain_key") in rule_brain_keys:
                continue
            v["source"] = "llm"
            survivors.append(v)
        return {"violations": survivors, "full_rewrite": data.get("full_rewrite")}
    except Exception:
        return None


POLISH_PROMPT = (
    "You are CommitGuard's onboarding helper. Rephrase the policy answer "
    "into one or two friendly sentences for a new hire. Keep every fact, "
    "number, and threshold exactly as stated — never invent rules."
)


def llm_polish_answer(question: str, answer: str) -> Optional[str]:
    """Optional friendly rephrase of a brain answer for /ask. Sources are
    never touched. Fails open like llm_enrich: any problem -> None."""
    try:
        client = _get_client()
        if client is None:
            return None
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            timeout=4,
            messages=[
                {"role": "system", "content": POLISH_PROMPT},
                {"role": "user", "content":
                    f"New hire's question: {question}\n\n"
                    f"Brain answer to rephrase: {answer}"},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        return None
