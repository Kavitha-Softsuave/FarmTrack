"""Find quantities ('600 g', '200 litres', '7 दिन', 'six hundred grams') in farmer-facing text, for the validator.

Everything is converted to base units (grams, millilitres) so '0.6 kg' equals '600 g'. Numbers written as words are read
back with the same tables used to write them (numbers.py), so a dose spelled out in words cannot slip past the checks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from functools import cache

from app.advice.numbers import EN_POINT, HI_HALVES, HI_POINT, number_to_words
from app.domain.types import Lang

MASS = "mass_g"
VOLUME = "volume_ml"
PERCENT = "percent"
DAYS = "days"
HOURS = "hours"
MM = "mm"
CELSIUS = "celsius"

# (family, factor to the base unit, regex alternatives; longest first)
_UNIT_DEFS: tuple[tuple[str, int, str], ...] = (
    (MASS, 1000, r"kgs?|kilograms?|kilos?|किलोग्राम|किलो|कि\.?\s?ग्रा\.?"),
    (MASS, 1, r"gms?|g|grams?|ग्राम|ग्रा"),
    (VOLUME, 1, r"mls?|millilit(?:re|er)s?|मिलीलीटर|मि\.?\s?ली\.?|एमएल"),
    (VOLUME, 1000, r"litres?|liters?|ltr|lit|l|लीटर|ली"),
    (PERCENT, 1, r"%|per\s?cent|प्रतिशत"),
    (DAYS, 1, r"days?|दिनों|दिन"),
    (HOURS, 1, r"hours?|hrs?|h|घंटे|घंटा|घण्टे|घंटों"),
    (MM, 1, r"mm|millimet(?:re|er)s?|मिलीमीटर"),
    (CELSIUS, 1, r"°\s?c|degrees?\s+celsius|degrees?|डिग्री(?:\s?सेल्सियस)?"),
)
_NUM = r"\d+(?:\.\d+)?"
_RANGE_SEP = r"(?:-|–|—|\bto\b|से)"
_LETTER = "A-Za-z\u0900-\u0963\u0965-\u097f"


@dataclass(frozen=True)
class Quantity:
    family: str
    value: Decimal          # in base units (g, ml) for MASS/VOLUME, otherwise as written
    text: str


def _unit_regex(alternatives: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![\d.])(?:(?P<lo>{_NUM})\s*{_RANGE_SEP}\s*)?(?P<num>{_NUM})\s*(?P<unit>{alternatives})(?![{_LETTER}])",
        re.IGNORECASE,
    )


_UNIT_RES = tuple((family, factor, _unit_regex(alts)) for family, factor, alts in _UNIT_DEFS)

# ------------------------------------------------------------------------------ number words -> digits
_UNIT_WORDS = frozenset(
    "gram grams kilogram kilograms kilo kilos millilitre millilitres milliliter milliliters litre litres liter liters percent "
    "day days hour hours millimetre millimetres millimeter millimeters degree degrees "
    "ग्राम किलोग्राम किलो मिलीलीटर लीटर प्रतिशत दिन दिनों घंटे घंटा मिलीमीटर डिग्री".split()
)
_WORD_RE = re.compile(rf"[{_LETTER}]+")
_HI_VARIANTS = {"छः": "छह", "पांच": "पाँच", "हजार": "हज़ार"}


@cache
def _reverse_tables() -> dict[str, dict[tuple[str, ...], int]]:
    tables: dict[str, dict[tuple[str, ...], int]] = {"en": {}, "hi": {}}
    langs: tuple[Lang, ...] = ("en", "hi")
    for n in range(10_000):
        for lang in langs:
            words = tuple(number_to_words(n, lang).split())
            tables[lang][words] = n
            if lang == "en" and "and" in words:
                tables[lang][tuple(w for w in words if w != "and")] = n
    return tables


def _decimal_from_words(tokens: list[str], start: int, lang: Lang) -> tuple[Decimal, int] | None:
    """Longest number-word run starting at `start`; returns (value, tokens used)."""
    table = _reverse_tables()[lang]
    best: tuple[Decimal, int] | None = None
    for end in range(min(len(tokens), start + 7), start, -1):
        key = tuple(tokens[start:end])
        if key in table:
            best = (Decimal(table[key]), end - start)
            break
    if lang == "hi":
        for number, spoken in HI_HALVES.items():
            if tokens[start] == spoken:
                return Decimal(number), 1
    if best is None:
        return None
    value, used = best
    point = EN_POINT if lang == "en" else HI_POINT
    pos = start + used
    digits = ""
    if pos < len(tokens) and tokens[pos] == point:
        pos += 1
        digit_words = {number_to_words(i, lang): str(i) for i in range(10)}
        while pos < len(tokens) and tokens[pos] in digit_words:
            digits += digit_words[tokens[pos]]
            pos += 1
        if digits:
            return Decimal(f"{value}.{digits}"), pos - start
    return value, used


def words_to_digits(text: str) -> str:
    """Replace number words that are directly followed by a unit word with digits ('six hundred grams' -> '600 grams')."""
    matches = list(_WORD_RE.finditer(text))
    tokens = [_HI_VARIANTS.get(m.group(), m.group()).lower() for m in matches]
    out: list[str] = []
    cursor = 0
    i = 0
    while i < len(matches):
        found = _decimal_from_words(tokens, i, "en") or _decimal_from_words(tokens, i, "hi")
        if found:
            value, used = found
            last = i + used - 1
            nxt = last + 1
            joined_by_space = all(re.fullmatch(r"[\s\-]+", text[matches[k].end():matches[k + 1].start()]) for k in range(i, last))
            gap_ok = nxt < len(matches) and re.fullmatch(r"\s*", text[matches[last].end():matches[nxt].start()])
            if joined_by_space and gap_ok and tokens[nxt] in _UNIT_WORDS:
                out.append(text[cursor:matches[i].start()])
                out.append(str(value))
                cursor = matches[last].end()
                i = nxt
                continue
        i += 1
    out.append(text[cursor:])
    return "".join(out)


def extract_quantities(text: str) -> list[Quantity]:
    """All number+unit pairs in `text`, ranges included, with MASS and VOLUME converted to grams and millilitres."""
    text = words_to_digits(text)
    found: list[Quantity] = []
    for family, factor, regex in _UNIT_RES:
        for m in regex.finditer(text):
            for key in ("lo", "num"):
                if m.group(key):
                    found.append(Quantity(family, Decimal(m.group(key)) * factor, m.group(0).strip()))
    return found
