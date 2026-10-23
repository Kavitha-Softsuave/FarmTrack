"""History-based warnings (shown with advice) and the check of a NEW spray-diary entry (check_spray)."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.types import FarmerProfile, Severity, SprayRecord, WarningItem
from app.rules import codes
from app.rules import messages as msg
from app.rules import stage as stage_rules
from app.rules.data import ReferenceData, cfg
from app.rules.history import (
    DEDUPE_WINDOW,
    Spray,
    consecutive_component,
    count_component,
    fungicide_sprays,
    last_of_family,
    relevant_to_crop,
    resolve_history,
    resolve_record,
    season_sprays,
)
from app.rules.risks import farmer_crops
from app.rules.selection import QOI_MANY_SPRAYS, Limits, unknown_waiting_days
from app.rules.weather import as_ist

STALE_AFTER_DAYS = 60
TANK_MIX_LOOKBACK_DAYS = 30


def _warning(warning_code: str, level: Severity, key: str, params: dict | None = None, **text_params: object) -> WarningItem:
    return WarningItem(code=warning_code, level=level, text=msg.text(key, **text_params), params=params or {})


def _name(spray: Spray) -> msg.Bilingual:
    product = spray.product
    if product is not None:
        return msg.Bilingual(product.active_ingredient, product.active_ingredient_hi or product.active_ingredient)
    return msg.Bilingual(spray.label, spray.label)


def _grows_apple(farmer: FarmerProfile, crop: str | None) -> bool:
    return (crop or "").lower() == "apple" or "apple" in farmer_crops(farmer)


def rotation_limit_warnings(limits: Limits) -> list[WarningItem]:
    out: list[WarningItem] = []
    if limits.dmi_count >= limits.dmi_limit:
        out.append(_warning("ROTATION_LIMIT", Severity.yellow, "ROTATION_DMI",
                            {"kind": "dmi", "count": limits.dmi_count, "limit": limits.dmi_limit},
                            count=limits.dmi_count, limit=limits.dmi_limit))
    if limits.qoi_count >= limits.qoi_limit:
        out.append(_warning("ROTATION_LIMIT", Severity.yellow, "ROTATION_QOI",
                            {"kind": "qoi", "count": limits.qoi_count, "limit": limits.qoi_limit},
                            count=limits.qoi_count, limit=limits.qoi_limit))
    if limits.sdhi_consecutive >= limits.sdhi_limit:
        out.append(_warning("ROTATION_LIMIT", Severity.yellow, "ROTATION_SDHI",
                            {"kind": "sdhi", "count": limits.sdhi_consecutive, "limit": limits.sdhi_limit},
                            count=limits.sdhi_consecutive))
    return out


def stale_history_warning(ref: ReferenceData, farmer: FarmerProfile, crop: str, sprays: list[Spray], now: datetime) -> WarningItem | None:
    if not stage_rules.in_spray_season(ref, farmer, crop, now):
        return None
    last = next((s for s in reversed(sprays) if not s.nutrient and relevant_to_crop(s, crop)), None)
    if last is not None and now - last.at <= timedelta(days=STALE_AFTER_DAYS):
        return None
    if last is None:
        return _warning("STALE_HISTORY", Severity.yellow, "STALE_HISTORY_NONE", {"last_spray": None, "days_since": None})
    return _warning("STALE_HISTORY", Severity.yellow, "STALE_HISTORY",
                    {"last_spray": last.at.isoformat(), "days_since": (now - last.at).days}, date=last.at)


def off_label_history_warning(farmer: FarmerProfile, crop: str, sprays: list[Spray]) -> WarningItem | None:
    if not _grows_apple(farmer, crop):
        return None
    names: list[str] = []
    for s in sprays:
        if s.offlabel is not None and s.offlabel.trade_name not in names:
            names.append(s.offlabel.trade_name)
    if not names:
        return None
    return _warning("OFF_LABEL_HISTORY", Severity.yellow, "OFF_LABEL_HISTORY", {"products": names}, products=names)


def tank_mix_warning(sprays: list[Spray], now: datetime) -> WarningItem | None:
    """A nutrient row on the same calendar day as a fungicide (HP 2026 point 7: spray nutrients separately)."""
    cutoff = now - timedelta(days=TANK_MIX_LOOKBACK_DAYS)
    fungicide_days = {s.day for s in sprays if s.is_fungicide}
    days = sorted({s.day for s in sprays if s.nutrient and s.at >= cutoff and s.day in fungicide_days})
    if not days:
        return None
    return _warning("TANK_MIX_HISTORY", Severity.yellow, "TANK_MIX_HISTORY", {"dates": [d.isoformat() for d in days]}, date=days[-1])


def history_warnings(ref: ReferenceData, farmer: FarmerProfile, crop: str, sprays: list[Spray], now: datetime,
                     limits: Limits) -> list[WarningItem]:
    found = [
        stale_history_warning(ref, farmer, crop, sprays, now),
        off_label_history_warning(farmer, crop, sprays),
        tank_mix_warning(sprays, now),
    ]
    return [w for w in found if w is not None] + rotation_limit_warnings(limits)


# ---------------------------------------------------------------------------------------------------------- check_spray
def _same(a: Spray, b: Spray) -> bool:
    return (a.nutrient == b.nutrient and a.actives == b.actives and a.components == b.components
            and abs(a.at - b.at) <= DEDUPE_WINDOW)


def _limit_warning(kind: str, rotation_key: str, count: int, limit: int, **text_params: object) -> WarningItem | None:
    if count < limit:
        return None
    level = Severity.red if count > limit else Severity.yellow
    return _warning("ROTATION_LIMIT", level, rotation_key, {"kind": kind, "count": count, "limit": limit, "exceeded": count > limit},
                    count=count, limit=limit, **text_params)


def check_new_spray(ref: ReferenceData, farmer: FarmerProfile, record: SprayRecord, history: list[SprayRecord],
                    now: datetime) -> list[WarningItem]:
    new = resolve_record(ref, record)
    now = max(as_ist(now), new.at)
    everything = [s for s in resolve_history(ref, history, now) if not _same(s, new)]
    prior = [s for s in everything if s.at < new.at]
    crop = new.crop or ref.canonical_crop(farmer.primary_crop) or farmer.primary_crop
    out: list[WarningItem] = []

    # 1. nutrient and fungicide on the same day (either order)
    same_day = [s for s in everything if s.day == new.day]
    if (new.nutrient and any(s.is_fungicide for s in same_day)) or (new.is_fungicide and any(s.nutrient for s in same_day)):
        out.append(_warning("TANK_MIX_HISTORY", Severity.yellow, "TANK_MIX_HISTORY", {"dates": [new.day.isoformat()]}, date=new.day))

    # 2. rotation: same chemical / group as the previous fungicide, DMI / QoI / SDHI limits
    if new.is_fungicide:
        season = fungicide_sprays(season_sprays(prior, new.at), crop)
        last = last_of_family(season, "fungicide", crop)
        if last is not None and new.actives & last.actives:
            out.append(_warning("ROTATION_LIMIT", Severity.yellow, "ROTATION_SAME_ACTIVE",
                                {"kind": "same_active", "previous": last.label}, name=_name(new)))
        elif last is not None and codes.shared(new.components, last.components):
            shared = "+".join(codes.shared(new.components, last.components))
            out.append(_warning("ROTATION_LIMIT", Severity.yellow, "ROTATION_SAME_FRAC",
                                {"kind": "same_frac", "components": shared, "previous": last.label}, name=_name(new), code=shared))
        if codes.has_dmi(new.components):
            limit = _limit_warning("dmi", "ROTATION_DMI", count_component(season, codes.DMI) + 1,
                                   int(cfg(ref.config, "rotation.max_per_season.DMI", 4)))
            if limit:
                out.append(limit)
        if codes.has_qoi(new.components):
            qoi_limit = int(cfg(ref.config, "rotation.max_per_season.QoI", 3))
            if len(season) + 1 >= QOI_MANY_SPRAYS:
                qoi_limit = int(cfg(ref.config, "rotation.max_per_season.QoI_if_12_or_more_sprays", qoi_limit + 1))
            limit = _limit_warning("qoi", "ROTATION_QOI", count_component(season, codes.QOI) + 1, qoi_limit)
            if limit:
                out.append(limit)
            if cfg(ref.config, "rotation.qoi_only_in_mixture", True) and new.components == (codes.QOI,):
                out.append(_warning("ROTATION_LIMIT", Severity.yellow, "ROTATION_QOI_SOLO", {"kind": "qoi_solo"}, name=_name(new)))
        if codes.has_sdhi(new.components):
            limit = _limit_warning("sdhi", "ROTATION_SDHI", consecutive_component(season, codes.SDHI) + 1,
                                   int(cfg(ref.config, "rotation.SDHI_max_consecutive", 2)))
            if limit:
                out.append(limit)

    # 3. banned / off-label / proposed ban
    if new.banned or (new.product is not None and new.product.ban_status == "banned"):
        out.append(_warning("BANNED_PRODUCT", Severity.red, "BANNED_PRODUCT", {"status": new.banned or "banned"}, name=_name(new)))
    if new.offlabel is not None and _grows_apple(farmer, crop):
        out.append(_warning("OFF_LABEL_PRODUCT", Severity.yellow, "OFF_LABEL_PRODUCT", {"product": new.offlabel.trade_name},
                            name=msg.Bilingual(new.offlabel.trade_name, new.offlabel.trade_name)))
    if new.product is not None and new.product.ban_status.startswith("proposed_ban"):
        out.append(_warning("PROPOSED_BAN", Severity.yellow, "PROPOSED_BAN", {"product_id": new.product.product_id}, name=_name(new)))

    # 4. waiting period against the harvest date
    if new.product is not None and crop == "Apple":
        band = stage_rules.band_for(ref, farmer)
        if band is not None:
            dth = stage_rules.days_to_harvest(band, stage_rules.cultivar_for(band, farmer), new.at)
            wp = new.product.waiting_period_days
            if dth is not None and wp is not None and wp > dth:
                out.append(_warning("WAITING_PERIOD_EXCEEDS_HARVEST", Severity.red, "WAITING_PERIOD_EXCEEDS_HARVEST",
                                    {"waiting_period_days": wp, "days_to_harvest": dth}, name=_name(new), wp=wp, days=dth))
            elif dth is not None and wp is None and dth <= unknown_waiting_days(ref):
                out.append(_warning("NO_WAITING_PERIOD", Severity.yellow, "NO_WAITING_PERIOD",
                                    {"product_id": new.product.product_id, "days_to_harvest": dth}, name=_name(new)))

    # 5. captan and oil need 15 days between them
    gap = timedelta(days=int(cfg(ref.config, "product_constraints.captan_oil_gap_days", 15)))
    near = [s for s in prior if new.at - s.at <= gap]
    if ("captan" in new.actives and any(s.category == "oil" for s in near)) or (
            new.category == "oil" and any("captan" in s.actives for s in near)):
        out.append(_warning("CAPTAN_OIL_GAP", Severity.yellow, "CAPTAN_OIL_GAP", {"days": gap.days}))
    return out
