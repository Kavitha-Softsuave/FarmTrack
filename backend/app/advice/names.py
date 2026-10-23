"""Name matching for chemicals, brands and diseases in Latin and Devanagari text (used by the validator and the spoken-text writer)."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable

DEVA_RANGE = "\u0900-\u097f"
_FORMULATION_TAIL = re.compile(r"\s+\d[\d.]*\s*%?\s*[A-Z]{1,3}$")

# Brands that are also ordinary English words: scanning for them would flag normal sentences ('Stop spraying').
COMMON_WORD_BRANDS = frozenset(
    "alert boon force glow index key laurel scale score stop titan trust companion majestic navigator governor magister "
    "cursor grapple".split()
)

# Spelling variants and generic names a model may use instead of the master's name.
ALIASES: dict[str, tuple[str, ...]] = {
    "horticultural mineral oil": ("mineral oil", "horticultural oil"),
    "sulphur": ("sulfur",),
    "copper sulphate": ("copper sulfate",),
}


def norm_latin(text: str) -> str:
    return re.sub(r"[\s\-_]+", " ", text.lower()).strip()


def norm_deva(text: str) -> str:
    """Drop the nukta (so ज़ीरम == जीरम) and collapse spaces."""
    decomposed = unicodedata.normalize("NFD", text).replace("़", "")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", decomposed)).strip()


def has_devanagari(text: str) -> bool:
    return re.search(f"[{DEVA_RANGE}]", text) is not None


def components(name: str) -> list[str]:
    """'A + B (C)' -> ['A', 'B', 'C']: every single name inside a combination or a bracketed synonym."""
    parts: list[str] = []
    for chunk in re.split(r"\s*\+\s*", name):
        base = re.sub(r"\s*\(.*?\)", "", chunk).strip()
        if base:
            parts.append(base)
        parts.extend(inner.strip() for inner in re.findall(r"\((.*?)\)", chunk) if inner.strip())
    return parts


def clean_brand(raw: str) -> list[str]:
    """'Cursor 40% EC (Dhanuka Agritech)' -> ['Cursor']; 'SAAF / Companion' -> ['SAAF', 'Companion']; [] when unusable."""
    brands: list[str] = []
    for piece in raw.split("/"):
        name = re.sub(r"\s*\(.*$", "", piece).strip()
        name = _FORMULATION_TAIL.sub("", name).strip()
        if len(name) >= 4:
            brands.append(name)
    return brands


def display_brand(raw: str) -> str:
    """The brand as a farmer reads it: no company in brackets and no formulation tail."""
    cleaned = clean_brand(raw)
    return cleaned[0] if cleaned else raw.strip()


class NameMatcher:
    """Finds whole-word occurrences of any of `names` (Latin: case, hyphen and spacing insensitive; Devanagari: nukta insensitive)."""

    def __init__(self, names: Iterable[str], *, devanagari: bool = False) -> None:
        self._devanagari = devanagari
        normaliser = norm_deva if devanagari else norm_latin
        self.names = frozenset(n for n in (normaliser(x) for x in names) if n)
        if not self.names:
            self._regex = None
            return
        ordered = sorted(self.names, key=len, reverse=True)
        space = r"\s+" if devanagari else r"[\s\-]+"
        body = "|".join(re.escape(n).replace(r"\ ", space) for n in ordered)
        if devanagari:
            self._regex = re.compile(rf"(?<![{DEVA_RANGE}])(?:{body})(?![{DEVA_RANGE}])")
        else:
            self._regex = re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.IGNORECASE)

    def find(self, text: str) -> set[str]:
        if self._regex is None:
            return set()
        if self._devanagari:
            return {norm_deva(m.group()) for m in self._regex.finditer(norm_deva(text))}
        return {norm_latin(m.group()) for m in self._regex.finditer(text)}

    def replace(self, text: str, repl: Callable[[str], str]) -> str:
        """Latin matchers only: replace every match with repl(normalised name)."""
        if self._regex is None or self._devanagari:
            return text
        return self._regex.sub(lambda m: repl(norm_latin(m.group())), text)
