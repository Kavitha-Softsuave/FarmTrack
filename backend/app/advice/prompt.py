"""The LLM prompt for an advice draft: built from the RuleOutput and the retrieved notes ONLY (no farmer name, phone or village).

The facts travel as a JSON block between two markers so a test double (app.llm.mock.MockLLM) can read them back.
"""
from __future__ import annotations

from typing import Any

from app.advice.dose import dose_text
from app.advice.names import display_brand
from app.advice.refdata import RefData, is_safe_note_text
from app.domain.types import LocalizedText, Note, RuleOutput, WarningItem
from app.llm.facts import wrap_facts

MAX_NOTES = 6
MAX_NOTE_CHARS = 500
ADVICE_SCHEMA_NAME = "advice_draft"

_LOCALIZED = {"type": "object", "additionalProperties": False, "required": ["en", "hi"],
              "properties": {"en": {"type": "string"}, "hi": {"type": "string"}}}
ADVICE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["headline", "summary", "steps", "safety", "spoken", "product_ids_mentioned", "doses_mentioned"],
    "properties": {
        "headline": _LOCALIZED,
        "summary": _LOCALIZED,
        "steps": {"type": "array", "items": _LOCALIZED},
        "safety": {"type": "array", "items": _LOCALIZED},
        "spoken": _LOCALIZED,
        "product_ids_mentioned": {"type": "array", "items": {"type": "string"}},
        "doses_mentioned": {"type": "array", "items": {"type": "string"}},
    },
}

INSTRUCTIONS = """You write short farm advice for a smallholder farmer in Himachal Pradesh, India. The farmer may not read well, so use \
plain, simple words and short sentences. Everything you need is in the FACTS block below. The facts come from a rules engine and \
are the only truth; you only explain them.

HARD RULES
1. Name only the products listed in facts.products. Never name any other medicine, brand, chemical or active ingredient, and never \
suggest a product when facts.products is empty.
2. Copy every dose and waiting period exactly as given (use each product's dose_text and waiting_period_days). Never change, round, \
convert or invent a number.
3. Follow facts.timing.action. If it is "wait" or "not_needed", or facts.status is not "advice", do not tell the farmer to spray; \
any sentence that mentions spraying must say "not", "wait", "when" or "ask". If it is "repeat_within_days", say when to spray again.
4. Do not name any disease other than facts.disease and do not add a diagnosis.
5. Never write a phone number or a helpline number.
6. Write every field in BOTH English (en) and Hindi (hi, Devanagari). Hindi must be simple spoken Hindi with short sentences; \
write chemical names in Hindi exactly as given in the "hi" fields.
7. `spoken` is a separate text for a voice: 3 to 6 short sentences per language, easy to listen to, no lists. In `spoken` write numbers \
as digits and units as g, ml, L, kg, ha or days; our system turns them into words. Use no other symbols or brackets.
8. `summary`: 2 or 3 short sentences. `steps`: one action per step, in order: timing first, then each product with its dose and waiting \
period, then the non-chemical measures. `safety`: only extra short tips; the system adds the standard safety lines and the rule warnings.
9. `product_ids_mentioned`: the product_id of every product you name. `doses_mentioned`: the dose_text (English) of each.
Return only the JSON object."""


def _loc(text: LocalizedText) -> dict[str, str]:
    return {"en": text.en, "hi": text.hi}


def _warning(w: WarningItem) -> dict[str, Any]:
    return {"code": w.code, "level": w.level.value, "text": _loc(w.text)}


def build_facts(out: RuleOutput, notes: list[Note], ref: RefData) -> dict[str, Any]:
    crop = ref.crop_name(out.crop_id)
    disease = ref.disease_name(out.disease_id)
    products = []
    for p in out.products:
        products.append({
            "product_id": p.product_id,
            "active_ingredient": {"en": p.active_ingredient, "hi": p.active_ingredient_hi or ref.hindi_ingredient(p.active_ingredient) or p.active_ingredient},
            "brand_example": display_brand(p.brand_examples[0]) if p.brand_examples else "",
            "category": p.category,
            "dose_text": _loc(dose_text(p)),
            "waiting_period_days": p.waiting_period_days,
            "warnings": [_warning(w) for w in p.warnings],
        })
    timing = None
    if out.timing:
        timing = {"action": out.timing.action, "repeat_within_days": out.timing.repeat_within_days,
                  "rain_next_12h_mm": out.timing.rain_next_12h_mm, "text": _loc(out.timing.text)}
    safe_notes = [n for n in notes if is_safe_note_text(f"{n.text_en} {n.text_hi}")][:MAX_NOTES]
    return {
        "task": "advice",
        "status": out.status,
        "severity": out.severity.value,
        "crop": {"id": out.crop_id, **_loc(crop)},
        "disease": {"id": out.disease_id, **_loc(disease)} if disease else None,
        "stage": out.stage,
        "timing": timing,
        "products": products,
        "non_chemical": [_loc(m) for m in out.non_chemical],
        "warnings": [_warning(w) for w in out.warnings],
        "risks": [{"id": r.id, "level": r.level.value, "title": _loc(r.title), "text": _loc(r.text)} for r in out.risks],
        "notes": [{"note_id": n.note_id, "text_en": n.text_en[:MAX_NOTE_CHARS], "text_hi": n.text_hi[:MAX_NOTE_CHARS]} for n in safe_notes],
    }


def build_prompt(facts: dict[str, Any]) -> str:
    return f"{INSTRUCTIONS}\n\n{wrap_facts(facts)}\n"
