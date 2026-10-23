"""Reference data for the rules engine: loaded once per data_dir and cached at module level.

Everything here is read-only and comes from settings.data_dir/reference. Parsing is tolerant (BOM, blank cells) but the
file set is required: a missing file raises, because a rules engine on partial data would be unsafe.
"""
from __future__ import annotations

import csv
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.rules.codes import components

REFERENCE_FILES = (
    "product_master.csv",
    "brand_master.csv",
    "disease_catalogue.csv",
    "stage_calendar.csv",
    "rules_config.json",
    "offlabel_products.csv",
    "banned_restricted.csv",
)

_NON_WORD = re.compile(r"[^a-z0-9+ ]+")
_SPACES = re.compile(r"\s+")
_PARENS = re.compile(r"\([^)]*\)")


def norm_text(value: str | None) -> str:
    """Lower-case, hyphens and punctuation to spaces, collapsed spaces. '+' is kept (it separates mixture parts)."""
    if not value:
        return ""
    text = value.lower().replace("-", " ").replace("%", " ")
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def active_parts(value: str | None) -> tuple[str, ...]:
    """'Carbendazim + Mancozeb' -> ('carbendazim', 'mancozeb')."""
    return tuple(p for p in (norm_text(part) for part in (value or "").split("+")) if p)


def contains_phrase(haystack: str, phrase: str) -> bool:
    """Whole-word(s) containment on already normalised text."""
    return bool(phrase) and f" {phrase} " in f" {haystack} "


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _split(value: str | None, sep: str = ";") -> tuple[str, ...]:
    return tuple(p.strip() for p in (value or "").split(sep) if p.strip())


def _brand_name(entry: str) -> str:
    """'Captaf (Rallis India Ltd)' -> 'Captaf'."""
    return _PARENS.sub("", entry).strip()


@dataclass(frozen=True)
class Product:
    product_id: str
    crop: str
    active_ingredient: str
    active_ingredient_hi: str | None
    formulation: str | None
    brand_example: str | None
    category: str
    frac_irac_code: str | None
    components: tuple[str, ...]
    behaviour: str | None
    targets: frozenset[str]
    stage: str
    dose_min: float | None
    dose_max: float | None
    dose_unit: str | None
    waiting_period_days: int | None
    ban_status: str
    use_note: str | None
    usable: bool
    hp_brand_group: str | None
    hp_brands: tuple[str, ...]
    source_ref: str | None
    confidence: str
    actives: tuple[str, ...] = field(default=())

    @property
    def active_set(self) -> frozenset[str]:
        return frozenset(self.actives)


@dataclass(frozen=True)
class Disease:
    disease_id: str
    kind: str                       # disease | pest | healthy
    crop: str
    name_en: str
    name_hi: str
    chemical_control: str           # yes | no | expert_referral
    treat_as: str | None
    requires_expert_review: bool
    non_chemical: str


@dataclass(frozen=True)
class OffLabel:
    trade_name: str
    active_ingredient: str
    formulation: str
    aliases: tuple[str, ...]        # normalised trade-name aliases
    actives: tuple[str, ...]        # actives that distinguish it from approved apple products; ALL must be present for an active-only match
    needs_fs_token: bool            # seed-treatment formulation: an active-only match needs the 'fs' token


@dataclass(frozen=True)
class BannedActive:
    actives: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class Band:
    band_id: str
    elev_min: float
    elev_max: float
    stages: tuple[tuple[str, int], ...]                 # (stage_id, typical_doy) ordered by doy
    harvest: dict[str, dict[str, int]]                  # cultivar -> {pre_harvest|harvest|post_harvest: doy}


@dataclass(frozen=True)
class ReferenceData:
    products: tuple[Product, ...]
    products_by_id: dict[str, Product]
    crops: dict[str, str]                               # lower-case -> canonical crop name (crops with usable rows)
    brands_by_group: dict[str, tuple[str, ...]]
    brand_actives: dict[str, str]                       # normalised brand -> active ingredient text
    diseases: dict[str, Disease]
    bands: dict[str, Band]
    config: dict[str, Any]
    offlabel: tuple[OffLabel, ...]
    banned: tuple[BannedActive, ...]
    known_actives: frozenset[str]

    def canonical_crop(self, crop_id: str | None) -> str | None:
        return self.crops.get((crop_id or "").strip().lower())

    def usable_products(self, crop: str) -> tuple[Product, ...]:
        return tuple(p for p in self.products if p.usable and p.crop == crop)


# ---------------------------------------------------------------------------------------------------------- loading
def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _product(row: dict[str, str]) -> Product:
    code = row.get("frac_irac_code") or None
    return Product(
        product_id=row["product_id"].strip(),
        crop=row["crop"].strip(),
        active_ingredient=row["active_ingredient"].strip(),
        active_ingredient_hi=row.get("active_ingredient_hi") or None,
        formulation=row.get("formulation") or None,
        brand_example=row.get("brand_example") or None,
        category=(row.get("category") or "").strip().lower(),
        frac_irac_code=code,
        components=components(code),
        behaviour=(row.get("behaviour") or "").strip().lower() or None,
        targets=frozenset(_split(row.get("targets"))),
        stage=(row.get("stage") or "any").strip(),
        dose_min=_float(row.get("dose_min")),
        dose_max=_float(row.get("dose_max")),
        dose_unit=row.get("dose_unit") or None,
        waiting_period_days=_int(row.get("waiting_period_days")),
        ban_status=(row.get("ban_status") or "registered").strip(),
        use_note=row.get("use_note") or None,
        usable=_bool(row.get("usable_for_recommendation")),
        hp_brand_group=row.get("hp_brand_group") or None,
        hp_brands=tuple(_brand_name(b) for b in _split(row.get("hp_evaluated_brands"))),
        source_ref=row.get("source_ref") or None,
        confidence=(row.get("confidence") or "").strip(),
        actives=active_parts(row["active_ingredient"]),
    )


def _disease(row: dict[str, str]) -> Disease:
    return Disease(
        disease_id=row["disease_id"].strip(),
        kind=(row.get("kind") or "disease").strip().lower(),
        crop=(row.get("crop") or "").strip(),
        name_en=row.get("name_en") or "",
        name_hi=row.get("name_hi") or "",
        chemical_control=(row.get("chemical_control") or "").strip().lower(),
        treat_as=(row.get("treat_as") or "").strip() or None,
        requires_expert_review=_bool(row.get("requires_expert_review")),
        non_chemical=(row.get("non_chemical") or "").strip(),
    )


def _offlabel(row: dict[str, str], approved_actives: frozenset[str]) -> OffLabel:
    trade = row["trade_name"].strip()
    aliases = {norm_text(_PARENS.sub("", trade))}
    words = norm_text(_PARENS.sub("", trade)).split()
    if len(words) > 1:
        aliases.add(" ".join(words[1:]))            # 'syngenta miravis duo' -> 'miravis duo' (company prefix dropped)
    formulation = row.get("formulation") or ""
    parts = active_parts(row["active_ingredient"])
    distinct = tuple(a for a in parts if a not in approved_actives)       # 'difenoconazole' alone is approved; 'pydiflumetofen' is not
    return OffLabel(
        trade_name=trade,
        active_ingredient=row["active_ingredient"].strip(),
        formulation=formulation,
        aliases=tuple(sorted(a for a in aliases if a)),
        actives=distinct or parts,
        needs_fs_token=formulation.strip().upper().endswith("FS"),
    )


def _bands(rows: list[dict[str, str]]) -> dict[str, Band]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["band_id"].strip(), []).append(row)
    bands: dict[str, Band] = {}
    for band_id, items in grouped.items():
        stages = sorted(
            ((r["stage_id"].strip(), int(r["typical_doy"])) for r in items if not (r.get("cultivar") or "").strip()),
            key=lambda s: s[1],
        )
        harvest: dict[str, dict[str, int]] = {}
        for r in items:
            cultivar = (r.get("cultivar") or "").strip()
            if cultivar:
                harvest.setdefault(cultivar, {})[r["stage_id"].strip()] = int(r["typical_doy"])
        bands[band_id] = Band(
            band_id=band_id,
            elev_min=float(items[0]["elev_min_m"]),
            elev_max=float(items[0]["elev_max_m"]),
            stages=tuple(stages),
            harvest=harvest,
        )
    return bands


def _load(data_dir: Path) -> ReferenceData:
    ref_dir = data_dir / "reference"
    missing = [name for name in REFERENCE_FILES if not (ref_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"rules reference data missing in {ref_dir}: {', '.join(missing)}")

    products = tuple(_product(r) for r in _rows(ref_dir / "product_master.csv"))
    brand_rows = _rows(ref_dir / "brand_master.csv")
    brands_by_group: dict[str, list[str]] = {}
    brand_actives: dict[str, str] = {}
    for row in brand_rows:
        name = row["brand"].strip()
        brands_by_group.setdefault(row["group_id"].strip(), []).append(name)
        brand_actives[norm_text(name)] = row.get("match_active_ingredient", "").strip()
    for product in products:
        if product.brand_example:
            brand_actives.setdefault(norm_text(product.brand_example), product.active_ingredient)

    apple_actives = frozenset(a for p in products if p.crop == "Apple" for a in p.actives)
    offlabel = tuple(_offlabel(r, apple_actives) for r in _rows(ref_dir / "offlabel_products.csv"))
    banned = tuple(
        BannedActive(actives=active_parts(r["active_ingredient"]), status=r["status"].strip())
        for r in _rows(ref_dir / "banned_restricted.csv")
    )
    known: set[str] = set()
    for p in products:
        known.update(p.actives)
    for o in offlabel:
        known.update(o.actives)
    for b in banned:
        known.update(b.actives)

    return ReferenceData(
        products=products,
        products_by_id={p.product_id: p for p in products},
        crops={p.crop.lower(): p.crop for p in products if p.usable},
        brands_by_group={k: tuple(v) for k, v in brands_by_group.items()},
        brand_actives={k: v for k, v in brand_actives.items() if k},
        diseases={d.disease_id: d for d in (_disease(r) for r in _rows(ref_dir / "disease_catalogue.csv"))},
        bands=_bands(_rows(ref_dir / "stage_calendar.csv")),
        config=json.loads((ref_dir / "rules_config.json").read_text(encoding="utf-8")),
        offlabel=offlabel,
        banned=banned,
        known_actives=frozenset(known),
    )


_CACHE: dict[str, ReferenceData] = {}
_LOCK = threading.Lock()


def load_reference(data_dir: Path | str) -> ReferenceData:
    """Load (once) and return the reference data for `data_dir`."""
    key = str(Path(data_dir).resolve())
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            cached = _CACHE[key] = _load(Path(key))
        return cached


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def cfg(config: dict[str, Any], path: str, default: Any) -> Any:
    """config['a']['b'] by dotted path, with a default when any level is missing."""
    node: Any = config
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
