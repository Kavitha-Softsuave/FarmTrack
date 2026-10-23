"""Spray history resolved against the reference data.

Zoho rows are messy: a product id may be missing, the FRAC cell may be blank or 'M3', the name is free text. Each SprayRecord
is turned into a `Spray` with its active ingredients, normalised FRAC/IRAC components, category family and any off-label or
banned match, so the exclusion rules work on facts instead of strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.domain.types import SprayRecord
from app.rules import codes
from app.rules.data import (
    OffLabel,
    Product,
    ReferenceData,
    active_parts,
    contains_phrase,
    norm_text,
)
from app.rules.weather import as_ist

FUNGICIDE_FAMILY = frozenset({"fungicide", "bactericide"})
PEST_FAMILY = frozenset({"insecticide", "acaricide"})
DEDUPE_WINDOW = timedelta(minutes=5)


@dataclass(frozen=True)
class Spray:
    at: datetime
    record: SprayRecord
    product: Product | None
    actives: frozenset[str]
    components: tuple[str, ...]
    category: str | None
    nutrient: bool
    offlabel: OffLabel | None
    banned: str | None
    label: str

    @property
    def family(self) -> str | None:
        return family_of(self.category)

    @property
    def is_fungicide(self) -> bool:
        return not self.nutrient and self.family == "fungicide"

    @property
    def crop(self) -> str | None:
        return self.product.crop if self.product else None

    @property
    def day(self) -> date:
        return self.at.date()


def family_of(category: str | None) -> str | None:
    if category in FUNGICIDE_FAMILY:
        return "fungicide"
    if category in PEST_FAMILY:
        return "pest"
    if category == "oil":
        return "oil"
    return None


def match_offlabel(ref: ReferenceData, text: str, actives: frozenset[str]) -> OffLabel | None:
    """Off-label product by trade-name alias, or by all of its active ingredients (seed treatments also need the 'fs' token)."""
    for row in ref.offlabel:
        if any(contains_phrase(text, alias) for alias in row.aliases):
            return row
        if row.actives and all(a in actives or contains_phrase(text, a) for a in row.actives):
            if not row.needs_fs_token or contains_phrase(text, "fs"):
                return row
    return None


def match_banned(ref: ReferenceData, actives: frozenset[str]) -> str | None:
    for row in ref.banned:
        if row.actives and all(a in actives for a in row.actives):
            return row.status
    return None


def _actives_from_text(ref: ReferenceData, text: str) -> frozenset[str]:
    found = {a for a in ref.known_actives if contains_phrase(text, a)}
    if found:
        return frozenset(found)
    for brand, active in ref.brand_actives.items():
        if contains_phrase(text, brand):
            return frozenset(active_parts(active))
    return frozenset()


def _category_from_master(ref: ReferenceData, actives: frozenset[str]) -> str | None:
    if not actives:
        return None
    exact = [p for p in ref.products if p.active_set == actives]
    if exact:
        return exact[0].category
    partial = [p for p in ref.products if p.active_set & actives]
    return partial[0].category if partial else None


def resolve_record(ref: ReferenceData, record: SprayRecord) -> Spray:
    product = ref.products_by_id.get(record.product_id) if record.product_id else None
    text = norm_text(" ".join(x for x in (record.trade_name, record.active_ingredient) if x))
    if product is not None:
        actives = product.active_set
    elif text:
        raw_active = norm_text(record.active_ingredient)
        actives = _actives_from_text(ref, text) or (frozenset({raw_active}) if raw_active else frozenset())
    else:
        actives = frozenset()

    comps = product.components if product is not None and product.components else codes.components(record.frac_irac_code)
    if not comps and actives:
        twin = next((p for p in ref.products if p.active_set == actives and p.components), None)
        comps = twin.components if twin else ()

    category = (record.category or "").strip().lower() or None
    if category is None and product is not None:
        category = product.category
    if category is None:
        category = _category_from_master(ref, actives)
    if category is None and comps:
        category = "insecticide" if codes.looks_like_irac(record.frac_irac_code) else "fungicide"
    if record.nutrient:
        category = None

    offlabel = None if product is not None or record.nutrient else match_offlabel(ref, text, actives)
    banned = match_banned(ref, actives) if not record.nutrient else None
    label = record.trade_name or record.active_ingredient or (product.active_ingredient if product else "") or "spray"
    return Spray(
        at=as_ist(record.sprayed_at), record=record, product=product, actives=actives, components=comps,
        category=category, nutrient=bool(record.nutrient), offlabel=offlabel, banned=banned, label=label,
    )


def resolve_history(ref: ReferenceData, history: list[SprayRecord], now: datetime | None = None) -> list[Spray]:
    """Resolved sprays, oldest first, no entries after `now`, near-duplicate rows (self + advisor) collapsed."""
    sprays = [resolve_record(ref, r) for r in history]
    if now is not None:
        sprays = [s for s in sprays if s.at <= now]
    sprays.sort(key=lambda s: s.at)
    unique: list[Spray] = []
    for spray in sprays:
        duplicate = any(
            u.nutrient == spray.nutrient and u.actives == spray.actives and u.components == spray.components
            and abs(u.at - spray.at) <= DEDUPE_WINDOW
            for u in unique[-4:]
        )
        if not duplicate:
            unique.append(spray)
    return unique


def relevant_to_crop(spray: Spray, crop: str) -> bool:
    """A spray counts for `crop` unless it is known to belong to another crop (history rows carry no crop of their own)."""
    return spray.crop is None or spray.crop == crop


def season_sprays(sprays: list[Spray], now: datetime) -> list[Spray]:
    """Sprays since 1 January of now's year (the resistance-management season used for the DMI/QoI limits)."""
    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return [s for s in sprays if start <= s.at <= now]


def fungicide_sprays(sprays: list[Spray], crop: str | None = None) -> list[Spray]:
    return [s for s in sprays if s.is_fungicide and (crop is None or relevant_to_crop(s, crop))]


def count_component(sprays: list[Spray], component: str) -> int:
    return sum(1 for s in sprays if component in s.components)


def consecutive_component(sprays: list[Spray], component: str) -> int:
    """How many of the most recent fungicide sprays in a row contain `component` (sprays oldest first)."""
    count = 0
    for spray in reversed(sprays):
        if component in spray.components:
            count += 1
        else:
            break
    return count


def last_of_family(sprays: list[Spray], family: str, crop: str | None = None) -> Spray | None:
    for spray in reversed(sprays):
        if not spray.nutrient and spray.family == family and (crop is None or relevant_to_crop(spray, crop)):
            return spray
    return None
