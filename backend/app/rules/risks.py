"""Weather-based risk items (evaluate_risks): scab infection, Marssonina/Alternaria, late blight, rain wash-off."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from app.domain.types import FarmerProfile, RiskItem, Severity, SprayRecord, WeatherSnapshot
from app.rules import messages as msg
from app.rules import stage as stage_rules
from app.rules import weather as wx
from app.rules.data import ReferenceData, cfg
from app.rules.history import Spray, resolve_history

LEAF_SPOT_YELLOW_BEFORE = 2        # yellow from (needed days - 2) consecutive qualifying days
LATE_BLIGHT_YELLOW_FRACTION = 0.8
LATE_BLIGHT_MIN_DATA = 0.9
SCAB_MIN_HOURS = 24


def farmer_crops(farmer: FarmerProfile) -> set[str]:
    crops = {c.strip().lower() for c in farmer.crops if c and c.strip()}
    if farmer.primary_crop:
        crops.add(farmer.primary_crop.strip().lower())
    return crops


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _risk(risk_id: str, level: Severity, title_key: str, text_key: str, detail: dict, weather: WeatherSnapshot, **params: object) -> RiskItem:
    detail = {**detail, "weather_stale": weather.stale}
    return RiskItem(id=risk_id, level=level, title=msg.text(title_key), text=msg.text(text_key, **params), detail=detail)


# ---------------------------------------------------------------------------------------------------------- scab
def scab_infection_risk(ref: ReferenceData, farmer: FarmerProfile, weather: WeatherSnapshot, hours: list[wx.Hour],
                        now: datetime) -> RiskItem:
    band = stage_rules.band_for(ref, farmer)
    in_season = stage_rules.scab_season_active(ref, band, now)
    detail: dict = {"in_season": in_season, "band": band.band_id if band else None}
    if not in_season:
        return _risk("scab_infection_risk", Severity.green, "RISK_SCAB_TITLE", "RISK_SCAB_OFF_SEASON", detail, weather)

    seen = wx.observed(hours, now)
    if len(seen) < SCAB_MIN_HOURS:
        return _risk("scab_infection_risk", Severity.green, "RISK_SCAB_TITLE", "RISK_NO_DATA",
                     {**detail, "insufficient_data": True}, weather)

    runs = wx.wet_runs(ref.config, seen)
    day_ago = now - timedelta(hours=24)
    still_open = now - timedelta(hours=wx.MILLS_GAP_HOURS)       # a run that ended later than this could still be joined
    reached = [r for r in runs if r.reached_at and (r.reached_at >= day_ago or r.end >= still_open)]
    building = [r for r in runs if r.end >= still_open and r.need_hours and r.wet_hours >= wx.YELLOW_FRACTION * r.need_hours]

    if reached:
        run, level, key = max(reached, key=lambda r: r.reached_at or r.end), Severity.red, "RISK_SCAB_RED"
    elif building:
        run, level, key = max(building, key=lambda r: r.wet_hours / (r.need_hours or 1)), Severity.yellow, "RISK_SCAB_YELLOW"
    else:
        return _risk("scab_infection_risk", Severity.green, "RISK_SCAB_TITLE", "RISK_SCAB_GREEN", detail, weather)

    detail.update({
        "period_start": _iso(run.start), "period_end": _iso(run.end), "wet_hours": run.wet_hours,
        "needed_hours": run.need_hours, "mean_temp_c": run.mean_temp_c, "rain_mm": run.rain_mm, "reached_at": _iso(run.reached_at),
    })
    return _risk("scab_infection_risk", level, "RISK_SCAB_TITLE", key, detail, weather)


# ---------------------------------------------------------------------------------------------------------- Marssonina / Alternaria
def leaf_spot_risk(ref: ReferenceData, weather: WeatherSnapshot, hours: list[wx.Hour], now: datetime) -> RiskItem:
    if not stage_rules.leaf_spot_season_active(ref, now):
        return _risk("marssonina_alternaria_risk", Severity.green, "RISK_LEAFSPOT_TITLE", "RISK_LEAFSPOT_OFF_SEASON",
                     {"in_season": False}, weather)
    needed = int(cfg(ref.config, "marssonina_alternaria_weather.consecutive_days", 5))
    run, stats = wx.leaf_spot_run_days(ref.config, hours, now)
    detail = {"in_season": True, "consecutive_days": run, "needed_days": needed, **(stats or {})}
    if run >= needed:
        return _risk("marssonina_alternaria_risk", Severity.red, "RISK_LEAFSPOT_TITLE", "RISK_LEAFSPOT_RED", detail, weather)
    if run >= max(1, needed - LEAF_SPOT_YELLOW_BEFORE):
        return _risk("marssonina_alternaria_risk", Severity.yellow, "RISK_LEAFSPOT_TITLE", "RISK_LEAFSPOT_YELLOW", detail, weather)
    return _risk("marssonina_alternaria_risk", Severity.green, "RISK_LEAFSPOT_TITLE", "RISK_LEAFSPOT_GREEN", detail, weather)


# ---------------------------------------------------------------------------------------------------------- late blight
def late_blight_risk(ref: ReferenceData, weather: WeatherSnapshot, hours: list[wx.Hour], now: datetime) -> RiskItem:
    counts = wx.late_blight_counts(ref.config, hours, now)
    detail = dict(counts)
    if counts["met"]:
        return _risk("late_blight_risk", Severity.red, "RISK_BLIGHT_TITLE", "RISK_BLIGHT_RED", detail, weather)
    if counts["hours_available"] < LATE_BLIGHT_MIN_DATA * counts["hours_expected"]:
        return _risk("late_blight_risk", Severity.green, "RISK_BLIGHT_TITLE", "RISK_NO_DATA", {**detail, "insufficient_data": True}, weather)
    close = (counts["temp_hours"] >= LATE_BLIGHT_YELLOW_FRACTION * counts["need_temp_hours"]
             and counts["rh_hours"] >= LATE_BLIGHT_YELLOW_FRACTION * counts["need_rh_hours"])
    key, level = ("RISK_BLIGHT_YELLOW", Severity.yellow) if close else ("RISK_BLIGHT_GREEN", Severity.green)
    return _risk("late_blight_risk", level, "RISK_BLIGHT_TITLE", key, detail, weather)


# ---------------------------------------------------------------------------------------------------------- rain wash-off
def rain_washoff_risk(ref: ReferenceData, weather: WeatherSnapshot, hours: list[wx.Hour], now: datetime,
                      sprays: Iterable[Spray]) -> RiskItem | None:
    heavy = float(cfg(ref.config, "rain.heavy_rain_mm_default", 10))
    window = int(cfg(ref.config, "rain.heavy_rain_window_hours", 12))
    days = int(cfg(ref.config, "rain.repeat_spray_within_days", 7))
    recent = [s for s in sprays if not s.nutrient and timedelta(0) <= now - s.at <= timedelta(hours=24)]
    if not recent:
        return None
    scored = [(s, *wx.rain_after_spray(hours, s.at, now, window)) for s in recent]
    spray, seen, total = max(scored, key=lambda item: item[2])
    detail = {"spray_at": _iso(spray.at), "product": spray.label, "rain_mm": round(total, 1), "observed_rain_mm": round(seen, 1),
              "threshold_mm": heavy, "window_hours": window}
    if seen >= heavy:
        return _risk("rain_washoff", Severity.red, "RISK_WASHOFF_TITLE", "RISK_WASHOFF_RED", detail, weather, rain=round(seen, 1), days=days)
    if total >= heavy:
        return _risk("rain_washoff", Severity.yellow, "RISK_WASHOFF_TITLE", "RISK_WASHOFF_YELLOW", detail, weather, rain=round(total, 1))
    return _risk("rain_washoff", Severity.green, "RISK_WASHOFF_TITLE", "RISK_WASHOFF_GREEN", detail, weather)


def evaluate(ref: ReferenceData, farmer: FarmerProfile, crops: set[str], weather: WeatherSnapshot, now: datetime,
             history: list[SprayRecord]) -> list[RiskItem]:
    """All risks that apply to a farmer growing `crops`, from the weather snapshot and the spray history."""
    now = wx.as_ist(now)
    hours = wx.merged_hours(weather)
    items: list[RiskItem] = []
    if "apple" in crops:
        items.append(scab_infection_risk(ref, farmer, weather, hours, now))
        items.append(leaf_spot_risk(ref, weather, hours, now))
    blight_crops = {str(c).lower() for c in cfg(ref.config, "late_blight_niphm.applies_to", ["Potato", "Tomato"])}
    if crops & blight_crops:
        items.append(late_blight_risk(ref, weather, hours, now))
    washoff = rain_washoff_risk(ref, weather, hours, now, resolve_history(ref, history, now))
    if washoff is not None:
        items.append(washoff)
    return items
