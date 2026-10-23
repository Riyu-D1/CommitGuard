"""LLM enrichment layer (owner: Riyansh).

Optional second stage after the deterministic rules engine. Fails open:
no API key or any error -> returns None -> rules-only result is served.
"""

import json
import os
from typing import Optional

_client = None
if os.environ.get("OPENAI_API_KEY"):
    from openai import OpenAI
    _client = OpenAI()


def llm_enabled() -> bool:
    return _client is not None


def llm_enrich(text: str, context_type: str, violations: list, brain: dict) -> Optional[dict]:
    if not _client:
        return None
    prompt = f"""You are CommitGuard, the pre-send compliance firewall for a company.
Review the draft below against the Company Brain and the deterministic findings.

Company Brain:
{json.dumps(brain, indent=2)}

Deterministic findings (already detected - keep them, improve wording if needed):
{json.dumps(violations, indent=2)}

Context type: {context_type}
Draft:
\"\"\"{text}\"\"\"

Return: status (CLEAN or VIOLATION_DETECTED), risk_level, violations (same fields:
category, severity, issue, correction, suggested_rewrite), and a single polished
full_rewrite of the draft that resolves every violation while keeping the sender's
tone. Set full_rewrite to null if CLEAN."""
    try:
        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=8,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "commit_guard_response",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "enum": ["CLEAN", "VIOLATION_DETECTED"]},
                            "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                            "violations": {"type": "array", "items": {"type": "object"}},
                            "full_rewrite": {"type": ["string", "null"]},
                        },
                        "required": ["status", "risk_level", "violations", "full_rewrite"],
                        "additionalProperties": False,
                    },
                },
            },
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return None
