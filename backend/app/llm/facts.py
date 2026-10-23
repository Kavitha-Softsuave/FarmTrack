"""How a caller hands structured facts to MockLLM: a JSON object between two markers inside the prompt.

A real model sees the same block as ordinary prompt text, so one prompt works for both.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.interfaces import LLMError

FACTS_START = "<<<FACTS_JSON"
FACTS_END = "FACTS_JSON>>>"
_FACTS_RE = re.compile(re.escape(FACTS_START) + r"\s*(.*?)\s*" + re.escape(FACTS_END), re.DOTALL)


def wrap_facts(facts: dict[str, Any]) -> str:
    return f"{FACTS_START}\n{json.dumps(facts, ensure_ascii=False, indent=1)}\n{FACTS_END}"


def extract_facts(prompt: str) -> dict[str, Any] | None:
    """The facts object of a prompt, or None when it has no facts block."""
    match = _FACTS_RE.search(prompt)
    if not match:
        return None
    try:
        facts = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise LLMError("facts block is not valid JSON") from exc
    return facts if isinstance(facts, dict) else None
