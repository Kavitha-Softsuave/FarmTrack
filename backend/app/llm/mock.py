"""MockLLM: deterministic, offline stand-in for an LLM (the default provider).

Protocol with the advice composer: the prompt carries the rule facts as JSON between FACTS_JSON markers. For an 'advice' task
MockLLM writes a draft FROM those facts only (so the whole pipeline, validator included, runs without a network). For the Ask
service (schema_name 'ask_answer') it quotes the first sentence of the first approved note in the prompt, so offline Q&A works.
For any other prompt it returns the smallest object that satisfies the JSON schema.
"""
from __future__ import annotations

import re
from typing import Any

from app.interfaces import LLMError
from app.llm.facts import extract_facts

_TIMING = {
    "spray_now": ("You can spray now.", "आप अभी छिड़काव कर सकते हैं।"),
    "wait": ("Do not spray yet. Wait for a dry, calm day.", "अभी छिड़काव न करें। सूखे और शांत दिन का इंतज़ार करें।"),
    "not_needed": ("Spraying is not needed now.", "अभी छिड़काव की ज़रूरत नहीं है।"),
    "unknown": ("Ask your expert when to spray.", "कब छिड़काव करना है, यह विशेषज्ञ से पूछें।"),
}


def fill_schema(schema: dict[str, Any]) -> Any:
    """Smallest value that satisfies `schema` (objects: required properties; arrays: empty; strings: first enum value or '')."""
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if schema.get(key):
            return fill_schema(schema[key][0])
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "object":
        props = schema.get("properties", {})
        return {name: fill_schema(props[name]) for name in schema.get("required", list(props)) if name in props}
    if kind == "array":
        return []
    if kind == "string":
        return ""
    if kind in ("number", "integer"):
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    return None


def _timing_lines(timing: dict[str, Any] | None) -> tuple[str, str]:
    action = (timing or {}).get("action", "unknown")
    if action == "repeat_within_days":
        days = timing.get("repeat_within_days") if timing else None
        if days is None:
            return "You will need to spray again. Ask your expert when.", "दोबारा छिड़काव करना होगा। कब, यह विशेषज्ञ से पूछें।"
        return f"Spray again within {days} days.", f"{days} दिन के अंदर दोबारा छिड़काव करें।"
    return _TIMING.get(action, _TIMING["unknown"])


def _waiting(days: int | None) -> tuple[str, str]:
    if days is None:
        return "No waiting period is listed. If harvest is near, ask your expert.", "इंतज़ार के दिन नहीं लिखे हैं। तुड़ाई पास हो तो विशेषज्ञ से पूछें।"
    return f"Wait at least {days} days before harvest.", f"तुड़ाई से पहले कम से कम {days} दिन रुकें।"


def advice_from_facts(facts: dict[str, Any]) -> dict[str, Any]:
    crop, disease = facts["crop"], facts.get("disease")
    products = facts.get("products", [])[:3]
    d_en = disease["en"] if disease else "a plant problem"
    d_hi = disease["hi"].split(" (")[0] if disease else "पौधे की एक समस्या"
    t_en, t_hi = _timing_lines(facts.get("timing"))
    if not products or facts.get("status") != "advice":
        return {
            "headline": {"en": "Not sure yet: do not spray any medicine now", "hi": "अभी पक्का नहीं है: अभी कोई दवा न छिड़कें"},
            "summary": {"en": f"I am not sure what is wrong with your {crop['en']}. Please do not spray any medicine yet and ask a local agriculture expert.",
                        "hi": f"मुझे पक्का नहीं पता कि आपकी {crop['hi']} में क्या दिक्कत है। अभी कोई दवा न छिड़कें और खेती के जानकार से पूछें।"},
            "steps": [{"en": "Do not spray any medicine until you know what is wrong.", "hi": "जब तक पक्का न पता चले कि क्या दिक्कत है, कोई दवा न छिड़कें।"}],
            "safety": [],
            "spoken": {"en": "I am not sure what is wrong. Please do not spray any medicine now. Take another clear photo or show the plant to a local agriculture expert.",
                       "hi": "मुझे पक्का नहीं पता क्या दिक्कत है। अभी कोई दवा न छिड़कें। दूसरी साफ़ फ़ोटो लें या पौधा स्थानीय खेती के जानकार को दिखाएँ।"},
            "product_ids_mentioned": [],
            "doses_mentioned": [],
        }
    steps = [{"en": t_en, "hi": t_hi}]
    for p in products:
        brand = f" ({p['brand_example']})" if p.get("brand_example") else ""
        w_en, w_hi = _waiting(p.get("waiting_period_days"))
        steps.append({"en": f"{p['active_ingredient']['en']}{brand}: {p['dose_text']['en']}. {w_en}",
                      "hi": f"{p['active_ingredient']['hi']}: {p['dose_text']['hi']}। {w_hi}"})
    steps += [{"en": m["en"], "hi": m["hi"]} for m in facts.get("non_chemical", [])]
    first = products[0]
    w_en, w_hi = _waiting(first.get("waiting_period_days"))
    return {
        "headline": {"en": f"{d_en}: your next step", "hi": f"{d_hi}: आपका अगला कदम"},
        "summary": {"en": f"Your {crop['en']} crop shows signs of {d_en}. Follow the steps below.",
                    "hi": f"आपकी {crop['hi']} की फसल में {d_hi} के लक्षण दिख रहे हैं। नीचे दिए कदम अपनाएँ।"},
        "steps": steps,
        "safety": [],
        "spoken": {
            "en": f"This looks like {d_en}. {t_en} Use {first['active_ingredient']['en']}, {first['dose_text']['en']}. {w_en}",
            "hi": f"{d_hi} लग रहा है। {t_hi} {first['active_ingredient']['hi']} का इस्तेमाल करें, {first['dose_text']['hi']}। {w_hi}",
        },
        "product_ids_mentioned": [p["product_id"] for p in products],
        "doses_mentioned": [p["dose_text"]["en"] for p in products],
    }


# Ask (app.rag.ask): the prompt lists "NOTE <id> (crop: ..., topic: ...)" blocks with an "EN: ..." line and an optional "HI: ..." line.
ASK_SCHEMA_NAME = "ask_answer"
_NOTE_HEADER = re.compile(r"^NOTE (\S+) \(crop:", re.MULTILINE)
_FIRST_SENTENCE = re.compile(r"^(.+?[.?!।])(?=\s|$)", re.DOTALL)
MAX_MOCK_ANSWER_CHARS = 400


def ask_answer_from_prompt(prompt: str) -> dict[str, Any]:
    """First sentence of the first approved note in the requested language; no note in the prompt means an empty answer (a refusal)."""
    header = _NOTE_HEADER.search(prompt)
    if not header:
        return {"answer": "", "used_note_ids": []}
    texts: dict[str, str] = {}
    for line in prompt[header.end():].splitlines()[1:]:          # the lines under the header: "EN: ..." then an optional "HI: ..."
        if line[:4] not in ("EN: ", "HI: "):
            break
        texts[line[:2]] = line[4:].strip()
    text = (texts.get("HI") if "Write the answer in Hindi" in prompt else None) or texts.get("EN", "")
    sentence = _FIRST_SENTENCE.match(text)
    answer = (sentence.group(1) if sentence else text).strip()
    if len(answer) > MAX_MOCK_ANSWER_CHARS:
        answer = answer[:MAX_MOCK_ANSWER_CHARS].rsplit(" ", 1)[0]
    return {"answer": answer, "used_note_ids": [header.group(1)] if answer else []}


class MockLLM:
    name = "mock"

    def generate_json(self, prompt: str, schema: dict[str, Any], schema_name: str = "response",
                      images: list[bytes] | None = None) -> dict[str, Any]:
        if schema_name == ASK_SCHEMA_NAME:                # decided by the caller's schema name, never by text inside the prompt
            return ask_answer_from_prompt(prompt)
        facts = extract_facts(prompt)
        if facts and facts.get("task") == "advice":
            try:
                return advice_from_facts(facts)
            except (KeyError, TypeError, IndexError) as exc:
                raise LLMError("mock: advice facts are incomplete") from exc
        filled = fill_schema(schema)
        if not isinstance(filled, dict):
            raise LLMError("mock: schema root must be an object")
        return filled
