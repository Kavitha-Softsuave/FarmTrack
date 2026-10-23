"""The SPOKEN version of an advice: short ear-friendly sentences with no digits and no symbols.

Two jobs:
- normalise_spoken(): turns '600 g in 200 L' into 'six hundred grams in two hundred litres' (Hindi: 'दो सौ लीटर ... छह सौ ग्राम'),
  writes chemical names in Devanagari for the Hindi voice and removes every symbol. It GUARANTEES the result has no digit.
- build_spoken(): the template wording for each rule status (the LLM writes its own spoken text; it goes through the same normaliser).
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from app.advice import phrases
from app.advice.dose import dose_text
from app.advice.names import display_brand
from app.advice.numbers import digits_to_words, number_to_words
from app.advice.refdata import RefData
from app.domain.types import Lang, LocalizedText, RuleOutput, SpokenText

# unit key (lowercase) -> (singular, plural) per language; Hindi does not inflect
_UNITS: dict[str, dict[str, tuple[str, str]]] = {
    "en": {"kg": ("kilogram", "kilograms"), "g": ("gram", "grams"), "ml": ("millilitre", "millilitres"),
           "l": ("litre", "litres"), "ha": ("hectare", "hectares"), "acre": ("acre", "acres"), "%": ("percent", "percent"),
           "mm": ("millimetre", "millimetres"), "day": ("day", "days"), "hour": ("hour", "hours"),
           "°c": ("degree Celsius", "degrees Celsius")},
    "hi": {"kg": ("किलोग्राम", "किलोग्राम"), "g": ("ग्राम", "ग्राम"), "ml": ("मिलीलीटर", "मिलीलीटर"), "l": ("लीटर", "लीटर"),
           "ha": ("हेक्टेयर", "हेक्टेयर"), "acre": ("एकड़", "एकड़"), "%": ("प्रतिशत", "प्रतिशत"),
           "mm": ("मिलीमीटर", "मिलीमीटर"), "day": ("दिन", "दिन"), "hour": ("घंटा", "घंटे"), "°c": ("डिग्री सेल्सियस", "डिग्री सेल्सियस")},
}
_UNIT_ALIASES = {
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg", "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "ml": "ml", "mls": "ml", "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "ltr": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l", "ha": "ha", "hectare": "ha", "hectares": "ha",
    "acre": "acre", "acres": "acre", "%": "%", "percent": "%", "mm": "mm", "day": "day", "days": "day",
    "hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour", "h": "hour",
}
_UNIT_PATTERN = r"kgs?|kilograms?|gms?|g|grams?|mls?|millilit(?:re|er)s?|litres?|liters?|ltr|l|ha|hectares?|acres?|%|percent|mm|days?|hours?|hrs?|h"
_NUM = r"\d+(?:\.\d+)?"
_UNIT_AFTER_NUMBER = re.compile(
    rf"(?<![\w.])(?P<neg>-)?(?P<num>{_NUM})\s*(?:(?P<celsius>°\s?c(?![A-Za-z]))|(?P<unit>{_UNIT_PATTERN})"
    rf"(?:\s*/\s*(?P<per>{_UNIT_PATTERN}))?(?![A-Za-z]))",
    re.IGNORECASE,
)
_RANGE = re.compile(rf"(?<![\w.])({_NUM})\s*[-–—]\s*({_NUM})(?![\d.])")
_BARE_NUMBER = re.compile(rf"(?<![\w.])(?P<neg>-)?(?P<num>{_NUM})")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_SENTENCE_END = re.compile(r"(?<=[.?!।])\s+")


def short_hindi(name: str) -> str:
    """'गंधक (सल्फर)' -> 'गंधक': the bracket explains, the ear does not need it."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def _ascii_digits(text: str) -> str:
    return "".join(str(unicodedata.digit(ch)) if ch.isdigit() and not ch.isascii() and unicodedata.digit(ch, None) is not None else ch
                   for ch in text)


def _unit_words(key: str, value: Decimal, lang: Lang) -> str:
    singular, plural = _UNITS[lang][key]
    return singular if value == 1 else plural


def _expand_unit(match: re.Match[str], lang: Lang) -> str:
    value = Decimal(match.group("num"))
    words = number_to_words(match.group("num"), lang)
    if match.group("neg"):
        words = f"{'माइनस' if lang == 'hi' else 'minus'} {words}"
    if match.group("celsius"):
        return f"{words} {_unit_words('°c', value, lang)}"
    unit = _unit_words(_UNIT_ALIASES[match.group("unit").lower()], value, lang)
    if match.group("per"):
        per_singular = _UNITS[lang][_UNIT_ALIASES[match.group("per").lower()]][0]
        return f"{words} {unit} {'प्रति' if lang == 'hi' else 'per'} {per_singular}"
    return f"{words} {unit}"


def _bare(match: re.Match[str], lang: Lang) -> str:
    words = number_to_words(match.group("num"), lang)
    return f"{'माइनस' if lang == 'hi' else 'minus'} {words}" if match.group("neg") else words


def _clean_symbols(text: str, lang: Lang) -> str:
    text = text.replace("+", " और " if lang == "hi" else " and ").replace("&", " और " if lang == "hi" else " and ")
    text = text.replace("’", "'")
    text = re.sub(r"\(\s*", ", ", text)
    text = re.sub(r"\s*\)", ", ", text)
    text = re.sub(r"[:;]", ",", text)
    kept = []
    for i, ch in enumerate(text):
        category = unicodedata.category(ch)
        if category[0] in "LMZ" or ch in ".,?!।":
            kept.append(ch)
        elif ch == "'" and 0 < i < len(text) - 1 and text[i - 1].isalpha() and text[i + 1].isalpha():
            kept.append(ch)
        else:
            kept.append(" ")
    out = re.sub(r"\s+", " ", "".join(kept))
    out = re.sub(r"\s+([,.?!।])", r"\1", out)
    out = re.sub(r"[,.?!।]{2,}", _strongest_punctuation, out)
    return re.sub(r"^[\s,.]+", "", out).strip()


def _strongest_punctuation(match: re.Match[str]) -> str:
    run = match.group()
    return next((ch for ch in run if ch in ".?!।"), ",")


def normalise_spoken(text: str, lang: Lang, ref: RefData | None = None) -> str:
    """Make `text` safe and clear for a machine voice. The result never contains a digit."""
    text = _ascii_digits(text)
    text = _THOUSANDS.sub("", text)
    if lang == "hi" and ref is not None:
        text = _hindi_names(text, ref)
    text = _RANGE.sub(lambda m: f"{m.group(1)} {'से' if lang == 'hi' else 'to'} {m.group(2)}", text)
    text = _UNIT_AFTER_NUMBER.sub(lambda m: _expand_unit(m, lang), text)
    text = _BARE_NUMBER.sub(lambda m: _bare(m, lang), text)
    text = _clean_symbols(text, lang)
    if any(ch.isdigit() for ch in text):                     # unreachable by construction; the guarantee is cheap
        text = "".join(digits_to_words(ch, lang) + " " if ch.isdigit() else ch for ch in text)
    return text


def _hindi_names(text: str, ref: RefData) -> str:
    return ref.hindi_name_matcher.replace(text, lambda name: short_hindi(ref.hi_names.get(name, name)))


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text.strip()) if s.strip(" .?!।")]


# ---------------------------------------------------------------- template wording (raw: numbers still digits)
def _join(*parts: LocalizedText) -> SpokenText:
    return SpokenText(en=" ".join(p.en for p in parts if p.en), hi=" ".join(p.hi for p in parts if p.hi))


def build_spoken(out: RuleOutput, ref: RefData) -> SpokenText:
    crop = ref.crop_name(out.crop_id)
    if out.status == "advice" and out.products:
        disease = ref.disease_name(out.disease_id)
        product = out.products[0]
        ingredient = LocalizedText(en=product.active_ingredient, hi=short_hindi(
            product.active_ingredient_hi or ref.hindi_ingredient(product.active_ingredient) or product.active_ingredient))
        brand = display_brand(product.brand_examples[0]) if product.brand_examples else ""
        action = out.timing.action if out.timing else "unknown"
        repeat = out.timing.repeat_within_days if out.timing else None
        parts = [
            phrases.diagnosis_spoken(short_hindi(disease.hi) if disease else "", disease.en if disease else None, crop, out.severity.value),
            phrases.timing_sentence(action, repeat),
            phrases.product_spoken(ingredient, brand, dose_text(product)),
        ]
        if action != "wait":
            parts.append(phrases.waiting_sentence(product.waiting_period_days))
        parts += [phrases.PPE_SPOKEN, phrases.EXPERT_CONFIRM]
        return _join(*parts)
    if out.status == "no_approved_data":
        return _join(phrases.no_data_spoken(crop))
    if out.status == "not_a_disease":
        return _join(phrases.not_disease_spoken(crop))
    if out.status == "needs_more_info":
        return _join(phrases.MORE_INFO_SPOKEN)
    # expert_review, and 'advice' with no approved product left: plain "not sure", never a medicine
    return _join(phrases.expert_spoken(crop))
