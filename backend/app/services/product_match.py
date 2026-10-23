"""Match the medicine a farmer typed in the spray diary to the product master, so the spray-safety rules can check it.

Only an EXACT identity is accepted, after tolerant clean-up: case, punctuation, spacing, strengths like "75%" and trailing
formulation or unit words (WP, EC, SC, g, ml, a number) are ignored; Hindi text is compared after Unicode normalisation (the nukta
dot and the chandrabindu are ignored). A text matches when it is
  - a product id ("P012"), or
  - the English or Hindi name of an active ingredient (or several joined with + & and), or
  - a brand name from the product master or the HP evaluated-brand table (Bavistin, Dithane M-45 ...).
A text that merely CONTAINS a known name ("mancozeb plus zinc") is not matched: guessing the missing part would hide it.

The match is by active ingredient and crop. Several product rows can share one identity (Mancozeb has rows for the green-tip
stage, the walnut stage and a drench); that is fine when every row says the same thing about safety (category, FRAC/IRAC code,
ban status, waiting period) and the lowest id is used. When the rows disagree, or a brand belongs to two different ingredients,
the text is AMBIGUOUS and no product is chosen: the caller keeps the free text and tells the farmer it could not be checked.
Rules decide, this module never guesses.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.rules.data import Product, ReferenceData, load_reference

Status = Literal["resolved", "ambiguous", "unknown"]
Via = Literal["id", "brand", "active"]

_FORMULATIONS = frozenset({"wp", "sc", "ec", "wg", "wdg", "fs", "sl", "sp", "dp", "gr", "od", "ew", "se", "zc", "df", "sg", "ls",
                           "cs", "ds", "w", "v"})
_UNITS = frozenset({"g", "gm", "gms", "gram", "grams", "kg", "ml", "l", "ltr", "litre", "liter"})
_SEPARATORS = frozenset({"+", "&", "and", "plus", "और"})
_NUMBER = re.compile(r"^\d+(?:[.,]\d+)?$")
_STRENGTH = re.compile(r"\d+(?:[.,]\d+)?\s*%")
_BRAND_SPLIT = re.compile(r"[/;,]")
_ASCII_SPLIT = re.compile(r"(?<=[0-9])(?=[a-z])|(?<=[a-z])(?=[0-9])")     # "50wp" -> "50 wp", "m45" -> "m 45" (the compact key is unchanged)
_NUKTA = "़"
_CHANDRABINDU = "ँ"
_ANUSVARA = "ं"


@dataclass(frozen=True)
class Match:
    status: Status
    product_id: str | None = None
    via: Via | None = None


UNKNOWN = Match("unknown")
AMBIGUOUS = Match("ambiguous")


def tokens(text: str) -> list[str]:
    """Lower-case words of `text`: punctuation and symbols are separators, '+' and '&' stay as tokens, strengths are dropped."""
    text = unicodedata.normalize("NFC", text).casefold().replace(_CHANDRABINDU, _ANUSVARA)
    text = _ASCII_SPLIT.sub(" ", _STRENGTH.sub(" ", text))
    kept: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cf" or char == _NUKTA:                 # zero-width joiners, the nukta dot
            continue
        if category[0] in "LMN":
            kept.append(char)
        elif char in "+&":
            kept.append(f" {char} ")
        else:
            kept.append(" ")
    return "".join(kept).split()


def _noise(word: str, numbers: bool) -> bool:
    return word in _FORMULATIONS or word in _UNITS or (numbers and bool(_NUMBER.match(word)))


def keys(words: list[str], numbers: bool = True) -> Iterator[str]:
    """Compact lookup keys, the whole text first, then with trailing formulation / unit (and, for typed text, number) words removed."""
    rest = list(words)
    while rest:
        yield "".join(rest)
        if not _noise(rest[-1], numbers):
            return
        rest.pop()


def _parts(words: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for word in words:
        if word in _SEPARATORS:
            out.append([])
        else:
            out[-1].append(word)
    return [part for part in out if part]


def _compact_parts(text: str | None) -> list[str]:
    return ["".join(part) for part in _parts(tokens(text or ""))]


@dataclass(frozen=True)
class _Index:
    products: tuple[Product, ...]
    by_id: dict[str, Product]                        # lower-case product id -> product
    products_by_id: dict[str, Product]               # product id -> product
    actives: dict[str, str]                          # compact English or Hindi active-ingredient part -> compact English part
    sets: dict[str, frozenset[str]]                  # product id -> its active-ingredient set
    brand_products: dict[str, frozenset[str]]        # compact brand -> ids of the product rows that list it
    brand_actives: dict[str, frozenset[frozenset[str]]]   # compact brand -> the ingredient sets it stands for (HP brand table)


def _build(ref: ReferenceData) -> _Index:
    actives: dict[str, str] = {}
    sets: dict[str, frozenset[str]] = {}
    brand_products: dict[str, set[str]] = {}
    brand_actives: dict[str, set[frozenset[str]]] = {}
    for product in ref.products:
        english = _compact_parts(product.active_ingredient)
        sets[product.product_id] = frozenset(english)
        hindi = _compact_parts(product.active_ingredient_hi)
        for index, part in enumerate(english):
            actives.setdefault(part, part)
            if len(hindi) == len(english):
                actives.setdefault(hindi[index], part)
        for name in [*_BRAND_SPLIT.split(product.brand_example or ""), *product.hp_brands]:
            for key in keys(tokens(name), numbers=False):
                brand_products.setdefault(key, set()).add(product.product_id)
    for brand, active in ref.brand_actives.items():
        identity = frozenset(_compact_parts(active))
        if identity:
            for key in keys(tokens(brand), numbers=False):
                brand_actives.setdefault(key, set()).add(identity)
    return _Index(products=ref.products, by_id={p.product_id.casefold(): p for p in ref.products},
                  products_by_id={p.product_id: p for p in ref.products}, actives=actives, sets=sets,
                  brand_products={k: frozenset(v) for k, v in brand_products.items()},
                  brand_actives={k: frozenset(v) for k, v in brand_actives.items()})


@lru_cache(maxsize=4)
def _index(data_dir: Path) -> _Index:
    return _build(load_reference(data_dir))


def _signature(product: Product) -> tuple:
    return (product.category, product.frac_irac_code, product.ban_status, product.waiting_period_days)


class ProductMatcher:
    """Resolve typed text to one product-master row (see the module docstring for what counts as a match)."""

    def __init__(self, data_dir: Path | str) -> None:
        self._index = _index(Path(data_dir).resolve())

    def resolve(self, text: str, crop_id: str | None = None) -> Match:
        words = tokens(text)
        if not words:
            return UNKNOWN
        for key in keys(words):
            product = self._index.by_id.get(key)
            if product is not None:
                return Match("resolved", product.product_id, "id")
        wanted = self._active_set(words)
        if wanted is not None:
            return self._decide(self._of_crop(self._with_actives(wanted), crop_id), "active")
        for key in keys(words):
            if key in self._index.brand_products or key in self._index.brand_actives:
                return self._decide(self._brand_candidates(key, crop_id), "brand")
        return UNKNOWN

    def _active_set(self, words: list[str]) -> frozenset[str] | None:
        found: set[str] = set()
        for part in _parts(words):
            canonical = next((self._index.actives[key] for key in keys(part) if key in self._index.actives), None)
            if canonical is None:
                return None
            found.add(canonical)
        return frozenset(found) or None

    def _with_actives(self, wanted: frozenset[str]) -> list[Product]:
        return [p for p in self._index.products if self._index.sets[p.product_id] == wanted]

    def _brand_candidates(self, key: str, crop_id: str | None) -> list[Product]:
        """Rows that list the brand; failing that (another crop, or a brand only in the HP table) the rows of its ingredient."""
        listed = self._of_crop([self._index.products_by_id[i] for i in sorted(self._index.brand_products.get(key, ()))], crop_id)
        if listed:
            return listed
        identities = self._index.brand_actives.get(key, frozenset())
        return self._of_crop([p for p in self._index.products if self._index.sets[p.product_id] in identities], crop_id)

    @staticmethod
    def _of_crop(products: list[Product], crop_id: str | None) -> list[Product]:
        return [p for p in products if crop_id is None or p.crop.casefold() == crop_id.casefold()]

    def _decide(self, candidates: list[Product], via: Via) -> Match:
        if not candidates:
            return UNKNOWN                                    # a known name, but no row for this crop
        if len({self._index.sets[p.product_id] for p in candidates}) > 1 or len({_signature(p) for p in candidates}) > 1:
            return AMBIGUOUS                                  # different ingredients, or rows that disagree about safety
        chosen = min(candidates, key=lambda p: (not p.usable, p.product_id))
        return Match("resolved", chosen.product_id, via)
