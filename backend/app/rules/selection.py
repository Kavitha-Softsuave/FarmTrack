"""Candidate selection, exclusion rules and ranking for medicine advice (the safety-critical core).

Order of work: candidate rows (crop, disease, stage, approved) -> hard exclusions (each a machine reason code) -> the
rotation rule 'same FRAC/IRAC group as the last spray' (only when an alternative remains) -> ranking -> top 3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.types import ExcludedProduct, ProductChoice, Severity, WarningItem, WeatherSnapshot
from app.rules import codes
from app.rules import messages as msg
from app.rules import stage as stage_rules
from app.rules import weather as wx
from app.rules.data import Product, ReferenceData, cfg, norm_text
from app.rules.history import (
    Spray,
    consecutive_component,
    count_component,
    family_of,
    fungicide_sprays,
    last_of_family,
    match_banned,
    match_offlabel,
    season_sprays,
)

MAX_PRODUCTS = 3
MAX_BRANDS = 4
UNKNOWN_WAITING_DEFAULT_DAYS = 30
QOI_MANY_SPRAYS = 12

# Exclusion reason codes (machine readable, stored in ExcludedProduct.reasons)
R_DISABLED = "disabled_by_admin"
R_BANNED = "banned"
R_OFF_LABEL = "off_label"
R_SAME_ACTIVE = "same_active_as_last_spray"
R_SAME_FRAC = "same_frac_as_last_spray"
R_DMI = "dmi_season_limit"
R_QOI = "qoi_season_limit"
R_QOI_SOLO = "qoi_only_in_mixture"
R_SDHI = "sdhi_consecutive_limit"
R_WP_HARVEST = "waiting_period_exceeds_harvest"
R_WP_UNKNOWN = "unknown_waiting_period_near_harvest"
R_DODINE_HEAT = "dodine_above_30c"
R_CAPTAN_OIL = "captan_within_15_days_of_oil"
R_OIL_CAPTAN = "oil_within_15_days_of_captan"


@dataclass
class Context:
    ref: ReferenceData
    now: datetime
    crop: str
    disease_id: str
    target_ids: frozenset[str]
    stage: str | None                      # apple stage id, None for crops without a calendar
    days_to_harvest: int | None
    weather: WeatherSnapshot | None
    sprays: list[Spray]                    # resolved history, oldest first, no entries after now
    disabled: frozenset[str]
    lang: str = "hi"
    trace: list[str] = field(default_factory=list)
    # False (development): the date does not decide which rows may be used; see candidate_rows
    season_check: bool = True

    @property
    def season(self) -> list[Spray]:
        return season_sprays(self.sprays, self.now)


@dataclass(frozen=True)
class Limits:
    dmi_count: int
    dmi_limit: int
    qoi_count: int
    qoi_limit: int
    sdhi_consecutive: int
    sdhi_limit: int
    fungicide_count: int


def rotation_limits(ref: ReferenceData, sprays: list[Spray], now: datetime, crop: str) -> Limits:
    """DMI / QoI season counts and the SDHI consecutive count from this season's fungicide sprays on `crop`."""
    season = fungicide_sprays(season_sprays(sprays, now), crop)
    qoi_limit = int(cfg(ref.config, "rotation.max_per_season.QoI", 3))
    if len(season) >= QOI_MANY_SPRAYS:
        qoi_limit = int(cfg(ref.config, "rotation.max_per_season.QoI_if_12_or_more_sprays", qoi_limit + 1))
    return Limits(
        dmi_count=count_component(season, codes.DMI),
        dmi_limit=int(cfg(ref.config, "rotation.max_per_season.DMI", 4)),
        qoi_count=count_component(season, codes.QOI),
        qoi_limit=qoi_limit,
        sdhi_consecutive=consecutive_component(season, codes.SDHI),
        sdhi_limit=int(cfg(ref.config, "rotation.SDHI_max_consecutive", 2)),
        fungicide_count=len(season),
    )


# ---------------------------------------------------------------------------------------------------------- candidates
def candidate_rows(ctx: Context) -> list[Product]:
    """Approved rows for the crop and disease at the current stage (apple: earlier stage fallback, with a trace line)."""
    rows = [p for p in ctx.ref.usable_products(ctx.crop) if ctx.target_ids & p.targets]
    ctx.trace.append(f"{len(rows)} approved product rows target {', '.join(sorted(ctx.target_ids))} for {ctx.crop}.")
    if ctx.stage is None:
        return rows

    exact = [p for p in rows if p.stage in (ctx.stage, "any")]
    if exact:
        ctx.trace.append(f"Stage {ctx.stage}: {len(exact)} rows match this stage.")
        return exact
    here = stage_rules.stage_index(ctx.stage)
    earlier = [p for p in rows if p.stage != "any" and 0 <= stage_rules.stage_index(p.stage) < here]
    if not earlier:
        if not ctx.season_check:
            ctx.trace.append(f"Stage {ctx.stage}: no row for this stage or any earlier stage; the season is not checked, "
                             f"so every approved row for this disease is used.")
            return rows
        ctx.trace.append(f"Stage {ctx.stage}: no row for this stage or any earlier stage.")
        return []
    best = max(stage_rules.stage_index(p.stage) for p in earlier)
    chosen = [p for p in earlier if stage_rules.stage_index(p.stage) == best]
    ctx.trace.append(
        f"Stage {ctx.stage}: no row for this exact stage; fell back to the latest earlier stage with rows ({chosen[0].stage})."
    )
    return chosen


# ---------------------------------------------------------------------------------------------------------- exclusions
def max_temperature_c(weather: WeatherSnapshot | None, now: datetime) -> float | None:
    """Highest of the current temperature, the next 12 hours of forecast and today's forecast maximum."""
    if weather is None:
        return None
    temps: list[float] = [weather.temp_c] if weather.temp_c is not None else []
    horizon = now + timedelta(hours=12)
    temps += [h.temp for h in wx.forecast(wx.merged_hours(weather), now) if h.t <= horizon]
    temps += [d.tmax_c for d in weather.daily_forecast if d.day == now.date()]
    return max(temps) if temps else None


def unknown_waiting_days(ref: ReferenceData) -> int:
    policy = str(cfg(ref.config, "product_constraints.unknown_waiting_period_policy", ""))
    match = re.search(r"within_(\d+)_days", policy)
    return int(match.group(1)) if match else UNKNOWN_WAITING_DEFAULT_DAYS


def _recent(sprays: list[Spray], now: datetime, days: int, predicate) -> bool:
    return any(0 <= (now - s.at).total_seconds() <= days * 86400 and predicate(s) for s in sprays if not s.nutrient)


def hard_exclusion_reasons(ctx: Context, p: Product, limits: Limits, temp_max: float | None) -> list[str]:
    ref, reasons = ctx.ref, []
    if p.product_id in ctx.disabled:
        reasons.append(R_DISABLED)
    if p.ban_status == "banned" or match_banned(ref, p.active_set):
        reasons.append(R_BANNED)
    if match_offlabel(ref, norm_text(f"{p.active_ingredient} {p.brand_example or ''}"), p.active_set):
        reasons.append(R_OFF_LABEL)

    family = family_of(p.category)
    last = last_of_family(ctx.season, family, ctx.crop) if family in ("fungicide", "pest") else None
    if last is not None and p.active_set & last.actives:
        reasons.append(R_SAME_ACTIVE)

    if family == "fungicide":
        if codes.has_dmi(p.components) and limits.dmi_count >= limits.dmi_limit:
            reasons.append(R_DMI)
        if codes.has_qoi(p.components):
            if limits.qoi_count >= limits.qoi_limit:
                reasons.append(R_QOI)
            if cfg(ref.config, "rotation.qoi_only_in_mixture", True) and p.components == (codes.QOI,):
                reasons.append(R_QOI_SOLO)
        if codes.has_sdhi(p.components) and limits.sdhi_consecutive >= limits.sdhi_limit:
            reasons.append(R_SDHI)

    dth = ctx.days_to_harvest
    if dth is not None:
        if p.waiting_period_days is None:
            if dth <= unknown_waiting_days(ref):
                reasons.append(R_WP_UNKNOWN)
        elif p.waiting_period_days > dth:
            reasons.append(R_WP_HARVEST)

    if "dodine" in p.actives and temp_max is not None and temp_max > float(cfg(ref.config, "product_constraints.dodine_max_air_temp_c", 30)):
        reasons.append(R_DODINE_HEAT)

    gap = int(cfg(ref.config, "product_constraints.captan_oil_gap_days", 15))
    if "captan" in p.actives and _recent(ctx.sprays, ctx.now, gap, lambda s: s.category == "oil"):
        reasons.append(R_CAPTAN_OIL)
    if p.category == "oil" and _recent(ctx.sprays, ctx.now, gap, lambda s: "captan" in s.actives):
        reasons.append(R_OIL_CAPTAN)
    return reasons


@dataclass
class Eligibility:
    eligible: list[Product]
    excluded: list[ExcludedProduct]
    same_frac_kept: dict[str, tuple[str, ...]]   # product_id -> shared components, kept because no alternative exists
    limits: Limits
    last_fungicide: Spray | None


def apply_exclusions(ctx: Context, rows: list[Product]) -> Eligibility:
    limits = rotation_limits(ctx.ref, ctx.sprays, ctx.now, ctx.crop)
    temp_max = max_temperature_c(ctx.weather, ctx.now)
    reasons: dict[str, list[str]] = {}
    for p in rows:
        found = hard_exclusion_reasons(ctx, p, limits, temp_max)
        if found:
            reasons[p.product_id] = found

    remaining = [p for p in rows if p.product_id not in reasons]
    last = last_of_family(ctx.season, "fungicide", ctx.crop)
    frac_hits: dict[str, tuple[str, ...]] = {}
    if last is not None and last.components:
        for p in remaining:
            if family_of(p.category) == "fungicide":
                overlap = codes.shared(p.components, last.components)
                if overlap:
                    frac_hits[p.product_id] = overlap

    kept: dict[str, tuple[str, ...]] = {}
    if frac_hits and len(frac_hits) < len(remaining):
        for pid in frac_hits:
            reasons[pid] = [R_SAME_FRAC]
        ctx.trace.append(f"Dropped {len(frac_hits)} product(s) in the same FRAC group as the last spray ({last.label if last else ''}).")
    elif frac_hits:
        kept = frac_hits
        ctx.trace.append("Every remaining product shares a FRAC group with the last spray: kept them, with a rotation warning.")

    eligible = [p for p in rows if p.product_id not in reasons]
    excluded = [
        ExcludedProduct(product_id=p.product_id, active_ingredient=p.active_ingredient, reasons=reasons[p.product_id])
        for p in sorted(rows, key=lambda x: x.product_id) if p.product_id in reasons
    ]
    for item in excluded:
        ctx.trace.append(f"Excluded {item.product_id} {item.active_ingredient}: {', '.join(item.reasons)}.")
    return Eligibility(eligible, excluded, kept, limits, last)


# ---------------------------------------------------------------------------------------------------------- warnings per product
def _name(p: Product) -> msg.Bilingual:
    return msg.Bilingual(p.active_ingredient, p.active_ingredient_hi or p.active_ingredient)


def product_warnings(p: Product, same_frac: tuple[str, ...] | None = None) -> list[WarningItem]:
    out: list[WarningItem] = []
    if p.ban_status.startswith("proposed_ban"):
        out.append(WarningItem(code="PROPOSED_BAN", level=Severity.yellow, text=msg.text("PROPOSED_BAN", name=_name(p)),
                               params={"product_id": p.product_id, "ban_status": p.ban_status}))
    if p.waiting_period_days is None:
        out.append(WarningItem(code="NO_WAITING_PERIOD", level=Severity.yellow, text=msg.text("NO_WAITING_PERIOD", name=_name(p)),
                               params={"product_id": p.product_id}))
    if p.dose_unit and "200L" in p.dose_unit.replace(" ", ""):
        out.append(WarningItem(code="DOSE_PER_200L", level=Severity.green, text=msg.text("DOSE_PER_200L"),
                               params={"product_id": p.product_id, "dose_unit": p.dose_unit}))
    if "dodine" in p.actives:
        out.append(WarningItem(code="DODINE_RESTRICTIONS", level=Severity.yellow, text=msg.text("DODINE_RESTRICTIONS"),
                               params={"product_id": p.product_id}))
    if "captan" in p.actives or p.category == "oil":
        out.append(WarningItem(code="CAPTAN_OIL_INFO", level=Severity.green, text=msg.text("CAPTAN_OIL_INFO"),
                               params={"product_id": p.product_id}))
    if same_frac:
        out.append(WarningItem(code="ROTATION_LIMIT", level=Severity.yellow,
                               text=msg.text("SAME_FRAC_NO_ALTERNATIVE", code="+".join(same_frac)),
                               params={"kind": "same_frac_no_alternative", "product_id": p.product_id, "components": list(same_frac)}))
    return out


# ---------------------------------------------------------------------------------------------------------- ranking
@dataclass(frozen=True)
class Ranked:
    product: Product
    score: float
    reasons: tuple[str, ...]            # message keys explaining the rank
    warnings: tuple[WarningItem, ...]


def _preference(p: Product, infection_active: bool) -> tuple[float, str | None]:
    mode = p.behaviour or ""
    if infection_active:
        pts = {"systemic": 30.0, "mixed": 15.0}.get(mode, 0.0)
        return pts, "RANK_SYSTEMIC_INFECTION" if pts else None
    pts = {"contact": 30.0, "mixed": 15.0}.get(mode, 0.0)
    return pts, "RANK_PROTECTANT" if pts else None


def rank_products(ctx: Context, eligibility: Eligibility, infection_active: bool) -> list[Ranked]:
    ranked: list[Ranked] = []
    for p in eligibility.eligible:
        warnings = tuple(product_warnings(p, eligibility.same_frac_kept.get(p.product_id)))
        pref, pref_reason = _preference(p, infection_active)
        reasons = [pref_reason] if pref_reason else []
        score = pref
        if p.hp_brands or (p.hp_brand_group and p.hp_brand_group in ctx.ref.brands_by_group):
            score += 10
            reasons.append("RANK_HP_BRAND")
        score += {"V": 5.0, "V-s": 2.0}.get(p.confidence, 0.0)
        if p.waiting_period_days is not None:
            score += 3
            reasons.append("RANK_WAITING_KNOWN")
        for w in warnings:
            if w.level == Severity.yellow:
                score -= 3
            if w.code == "PROPOSED_BAN":
                score -= 17
                reasons.append("RANK_PROPOSED_BAN")
        ranked.append(Ranked(p, score, tuple(reasons), warnings))
    ranked.sort(key=lambda r: (-r.score, r.product.product_id))

    top: list[Ranked] = []
    seen_actives: set[str] = set()
    for item in ranked:
        key = item.product.active_ingredient.lower()
        if key in seen_actives:
            continue
        seen_actives.add(key)
        top.append(item)
        if len(top) == MAX_PRODUCTS:
            break
    return top


def brand_examples(ref: ReferenceData, p: Product) -> list[str]:
    names: list[str] = []
    for brand in (*p.hp_brands, *ref.brands_by_group.get(p.hp_brand_group or "", ()), p.brand_example or ""):
        if brand and brand.lower() not in {n.lower() for n in names}:
            names.append(brand)
    return names[:MAX_BRANDS]


def build_choice(ctx: Context, item: Ranked) -> ProductChoice:
    p = item.product
    reason = " ".join(msg.plain(key, ctx.lang) for key in dict.fromkeys(item.reasons))
    return ProductChoice(
        product_id=p.product_id, crop=p.crop, active_ingredient=p.active_ingredient, active_ingredient_hi=p.active_ingredient_hi,
        formulation=p.formulation, brand_examples=brand_examples(ctx.ref, p), category=p.category,
        frac_irac_code=codes.normalise_code(p.frac_irac_code) or None, behaviour=p.behaviour, stage=p.stage,
        dose_min=p.dose_min, dose_max=p.dose_max, dose_unit=p.dose_unit, waiting_period_days=p.waiting_period_days,
        ban_status=p.ban_status, use_note=p.use_note, rank_reason=reason, warnings=list(item.warnings), source_ref=p.source_ref,
    )
