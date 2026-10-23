"""Reference data the advice module needs: product names (for the validator), disease and crop names, Hindi chemical names
(for pronunciation), and the standard safety lines. Loaded once per data directory from data/reference/.
"""
from __future__ import annotations

import csv
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from app.advice.crop_names import crop_hi
from app.advice.names import (
    ALIASES,
    COMMON_WORD_BRANDS,
    NameMatcher,
    clean_brand,
    components,
    has_devanagari,
    norm_deva,
    norm_latin,
)
from app.domain.types import LocalizedText, ProductChoice

logger = logging.getLogger(__name__)

_US_POISON_NUMBER = re.compile(r"\b1[\s\-]800[\s\-]?\d{3}|\b\d{3}[\s\-]\d{3}[\s\-]\d{4}\b|\b\d{10,}\b")   # printed in the HP PDF; never shown to farmers
_BUILTIN_SAFETY = LocalizedText(
    en="Keep children, animals and unfamiliar people away while you mix and spray. Wear long sleeves, long trousers, closed "
       "shoes, gloves and goggles. Mix outdoors, mix only what you need, and wash your hands before you eat.",
    hi="मिलाते और छिड़कते समय बच्चों, पशुओं और अनजान लोगों को दूर रखें। पूरी बाँह के कपड़े, लंबी पैंट, बंद जूते, दस्ताने और चश्मा "
       "पहनें। खुले में मिलाएँ, उतना ही मिलाएँ जितना चाहिए, और खाने से पहले हाथ धोएँ।",
)


@dataclass(frozen=True)
class ProductRow:
    product_id: str
    crop: str
    active_ingredient: str
    active_ingredient_hi: str
    brands: tuple[str, ...]


@dataclass(frozen=True)
class DiseaseRow:
    disease_id: str
    name_en: str
    name_hi: str


@dataclass
class RefData:
    products: dict[str, ProductRow] = field(default_factory=dict)
    diseases: dict[str, DiseaseRow] = field(default_factory=dict)
    crops_hi: dict[str, str] = field(default_factory=dict)
    hi_names: dict[str, str] = field(default_factory=dict)          # normalised Latin ingredient -> Devanagari
    safety_lines: list[LocalizedText] = field(default_factory=list)
    # normalised name -> product ids that carry it; an empty set means banned, off-label or otherwise not in any product
    latin_index: dict[str, set[str]] = field(default_factory=dict)
    deva_index: dict[str, set[str]] = field(default_factory=dict)
    disease_latin: dict[str, set[str]] = field(default_factory=dict)
    disease_deva: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._latin_matcher: NameMatcher | None = None
        self._deva_matcher: NameMatcher | None = None
        self._disease_latin_matcher: NameMatcher | None = None
        self._disease_deva_matcher: NameMatcher | None = None
        self._hindi_name_matcher: NameMatcher | None = None

    # ---- names of things
    def crop_name(self, crop_id: str) -> LocalizedText:
        english = crop_id.replace("_", " ").lower()
        return LocalizedText(en=english, hi=self.crops_hi.get(crop_id) or crop_hi(crop_id) or english)

    def disease_name(self, disease_id: str | None) -> LocalizedText | None:
        row = self.diseases.get(disease_id or "")
        return LocalizedText(en=row.name_en, hi=row.name_hi or row.name_en) if row else None

    def hindi_ingredient(self, latin: str) -> str | None:
        return self.hi_names.get(norm_latin(latin))

    # ---- matchers for the validator
    @property
    def latin_matcher(self) -> NameMatcher:
        if self._latin_matcher is None:
            self._latin_matcher = NameMatcher(self.latin_index)
        return self._latin_matcher

    @property
    def deva_matcher(self) -> NameMatcher:
        if self._deva_matcher is None:
            self._deva_matcher = NameMatcher(self.deva_index, devanagari=True)
        return self._deva_matcher

    @property
    def disease_latin_matcher(self) -> NameMatcher:
        if self._disease_latin_matcher is None:
            self._disease_latin_matcher = NameMatcher(self.disease_latin)
        return self._disease_latin_matcher

    @property
    def disease_deva_matcher(self) -> NameMatcher:
        if self._disease_deva_matcher is None:
            self._disease_deva_matcher = NameMatcher(self.disease_deva, devanagari=True)
        return self._disease_deva_matcher

    @property
    def hindi_name_matcher(self) -> NameMatcher:
        """Latin chemical names that have a Hindi spelling (for the Hindi voice)."""
        if self._hindi_name_matcher is None:
            self._hindi_name_matcher = NameMatcher(self.hi_names)
        return self._hindi_name_matcher

    def names_of(self, product: ProductChoice) -> tuple[set[str], set[str]]:
        """Every Latin and Devanagari name that may appear in text about this product (ingredients, synonyms, brands)."""
        latin: set[str] = set()
        deva: set[str] = set()
        row = self.products.get(product.product_id)
        ingredients = [product.active_ingredient]
        ingredients_hi = [product.active_ingredient_hi or ""]
        brands = list(product.brand_examples)
        if row:
            ingredients.append(row.active_ingredient)
            ingredients_hi.append(row.active_ingredient_hi)
            brands.extend(row.brands)
        for ingredient in ingredients:
            for part in components(ingredient):
                latin.add(norm_latin(part))
                latin.update(norm_latin(a) for a in ALIASES.get(norm_latin(part), ()))
        for ingredient in ingredients_hi:
            deva.update(norm_deva(p) for p in components(ingredient))
        for brand in brands:
            latin.update(norm_latin(b) for b in clean_brand(brand) if norm_latin(b) not in COMMON_WORD_BRANDS)
        return {n for n in latin if n}, {n for n in deva if n}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        logger.warning("reference file missing: %s", path.name)
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _add(index: dict[str, set[str]], name: str, product_id: str | None, normaliser: Callable[[str], str]) -> None:
    key = normaliser(name)
    if len(key) < 3:
        return
    index.setdefault(key, set())
    if product_id:
        index[key].add(product_id)


def _load_products(ref: RefData, rows: list[dict[str, str]]) -> None:
    for row in rows:
        brands = [row["brand_example"], *row["hp_evaluated_brands"].split(";")]
        pid = row["product_id"]
        ref.products[pid] = ProductRow(pid, row["crop"], row["active_ingredient"], row["active_ingredient_hi"], tuple(b.strip() for b in brands if b.strip()))
        latin_parts, hindi_parts = components(row["active_ingredient"]), components(row["active_ingredient_hi"])
        for part in latin_parts:
            _add(ref.latin_index, part, pid, norm_latin)
            for alias in ALIASES.get(norm_latin(part), ()):
                _add(ref.latin_index, alias, pid, norm_latin)
        for part in hindi_parts:
            _add(ref.deva_index, part, pid, norm_deva)
        if len(latin_parts) == len(hindi_parts):
            ref.hi_names.update({norm_latin(en): hi for en, hi in zip(latin_parts, hindi_parts, strict=True)})
        for brand in brands:
            for cleaned in clean_brand(brand):
                if norm_latin(cleaned) not in COMMON_WORD_BRANDS:
                    _add(ref.latin_index, cleaned, pid, norm_latin)


def _load_brand_master(ref: RefData, rows: list[dict[str, str]]) -> None:
    by_ingredient: dict[str, set[str]] = {}
    for pid, product in ref.products.items():
        for part in components(product.active_ingredient):
            by_ingredient.setdefault(norm_latin(part), set()).add(pid)
    for row in rows:
        owners = by_ingredient.get(norm_latin(row.get("match_active_ingredient", "")), set())
        for cleaned in clean_brand(row["brand"]):
            if norm_latin(cleaned) not in COMMON_WORD_BRANDS:
                _add(ref.latin_index, cleaned, None, norm_latin)
                ref.latin_index[norm_latin(cleaned)].update(owners)


def _load_blocked(ref: RefData, banned: list[dict[str, str]], offlabel: list[dict[str, str]]) -> None:
    for row in banned:
        for part in components(row["active_ingredient"]):
            _add(ref.latin_index, part, None, norm_latin)
    for row in offlabel:
        for part in components(row["active_ingredient"]):
            _add(ref.latin_index, part, None, norm_latin)
        trade = re.sub(r"\s*\(.*$", "", row["trade_name"]).strip()
        for name in {trade, trade.split(" ", 1)[-1]}:
            if norm_latin(name) not in COMMON_WORD_BRANDS:
                _add(ref.latin_index, name, None, norm_latin)


def _load_diseases(ref: RefData, rows: list[dict[str, str]]) -> None:
    for row in rows:
        did = row["disease_id"]
        ref.diseases[did] = DiseaseRow(did, row["name_en"], row["name_hi"])
        if row["crop"] and row["crop_hi"]:
            ref.crops_hi.setdefault(row["crop"], row["crop_hi"])
        if row["kind"] not in ("disease", "pest"):
            continue
        en = re.split(r"\s*[/(]", row["name_en"])[0].strip()
        hi = re.split(r"\s*[/(]", row["name_hi"])[0].strip()
        binomial = re.match(r"^([A-Z][a-z]{6,}) (?:[a-z]|spp)", row["pathogen_or_pest"])
        genus = binomial.group(1) if binomial else ""
        for name in (en, genus):
            if " " in name or len(name) >= 7:
                _add(ref.disease_latin, name, did, norm_latin)
        if " " in hi and not hi.startswith("स्वस्थ"):
            _add(ref.disease_deva, hi, did, norm_deva)


def _load_glossary(ref: RefData, path: Path) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for en, hi in data.get("active_ingredients", {}).items():
        ref.hi_names.setdefault(norm_latin(en), hi)
        for e_part, h_part in zip(components(en), components(hi), strict=False):
            ref.hi_names.setdefault(norm_latin(e_part), h_part)
    for crop, hi in data.get("crops", {}).items():
        ref.crops_hi.setdefault(crop, hi)


def _load_safety(ref: RefData, path: Path) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            note = json.loads(line)
            tags = str(note.get("tags", "")).split(";")
            text = f"{note.get('text_en', '')} {note.get('text_hi', '')}"
            if note.get("topic") == "rule" and "safety" in tags and "gap" not in tags and not _US_POISON_NUMBER.search(text) \
                    and note.get("text_en") and has_devanagari(note.get("text_hi", "")):
                ref.safety_lines.append(LocalizedText(en=note["text_en"], hi=note["text_hi"]))
    if not ref.safety_lines:
        ref.safety_lines.append(_BUILTIN_SAFETY)


def is_safe_note_text(text: str) -> bool:
    """False for text that carries the US poison-control number (never shown or sent to a model)."""
    return _US_POISON_NUMBER.search(text) is None


@cache
def load_refdata(data_dir: str) -> RefData:
    root = Path(data_dir) / "reference"
    ref = RefData()
    _load_products(ref, _read_csv(root / "product_master.csv"))
    _load_brand_master(ref, _read_csv(root / "brand_master.csv"))
    _load_blocked(ref, _read_csv(root / "banned_restricted.csv"), _read_csv(root / "offlabel_products.csv"))
    _load_diseases(ref, _read_csv(root / "disease_catalogue.csv"))
    _load_glossary(ref, root / "hindi_glossary.json")
    _load_safety(ref, root / "advisory_notes.jsonl")
    return ref
