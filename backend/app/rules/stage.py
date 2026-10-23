"""Apple growth stage, scab primary season, harvest date and spray season from the stage calendar.

The calendar (data/reference/stage_calendar.csv) is an ESTIMATE by elevation band B1..B4: each stage has a typical day of
year. The stage at `now` is the latest stage whose typical day has been reached; before the first stage the tree is
'dormant'. The same day-of-year is applied to any year (leap years shift by at most one day).
"""
from __future__ import annotations

from datetime import datetime

from app.domain.types import FarmerProfile
from app.rules.data import Band, ReferenceData, cfg

DORMANT = "dormant"
DEFAULT_CULTIVAR = "Royal_Delicious"
SCAB_SEASON_SLACK_DAYS = 7
SCAB_SEASON_AFTER_PETAL_FALL_DAYS = 21
POST_HARVEST_SEASON_GRACE_DAYS = 30
NON_APPLE_SEASON_MONTHS = (3, 10)      # March..October for crops without a calendar

STAGE_ORDER: tuple[str, ...] = (
    DORMANT, "silver_tip", "green_tip", "half_inch_green_tip", "tight_cluster", "pink_bud", "full_bloom", "petal_fall",
    "fruit_set", "walnut_size", "walnut_plus_20d", "walnut_plus_40d", "pre_harvest", "harvest", "post_harvest",
)
_STAGE_INDEX = {stage: i for i, stage in enumerate(STAGE_ORDER)}


def stage_index(stage: str) -> int:
    """Position of a stage in the season; unknown stages sort first."""
    return _STAGE_INDEX.get(stage, -1)


def day_of_year(now: datetime) -> int:
    return now.timetuple().tm_yday


def band_for(ref: ReferenceData, farmer: FarmerProfile) -> Band | None:
    """The farmer's band from phenology_band, else from elevation, else None."""
    if farmer.phenology_band and farmer.phenology_band.strip().upper() in ref.bands:
        return ref.bands[farmer.phenology_band.strip().upper()]
    if farmer.elevation_m is not None:
        for band in sorted(ref.bands.values(), key=lambda b: b.elev_min):
            if band.elev_min <= farmer.elevation_m < band.elev_max:
                return band
        highest = max(ref.bands.values(), key=lambda b: b.elev_max, default=None)
        if highest is not None and farmer.elevation_m >= highest.elev_max:
            return highest
    return None


def cultivar_for(band: Band, farmer: FarmerProfile) -> str:
    variety = (farmer.primary_variety or "").strip().replace(" ", "_")
    return variety if variety in band.harvest else DEFAULT_CULTIVAR


def stage_doy(band: Band, stage: str) -> int | None:
    for stage_id, doy in band.stages:
        if stage_id == stage:
            return doy
    return None


def current_stage(band: Band, doy: int, cultivar: str) -> str:
    """Latest stage reached on `doy`: spray stages first, then the cultivar's pre_harvest/harvest/post_harvest."""
    reached = DORMANT
    for stage_id, stage_day in band.stages:
        if stage_day <= doy:
            reached = stage_id
    harvest_days = band.harvest.get(cultivar) or band.harvest.get(DEFAULT_CULTIVAR) or {}
    for stage_id in ("pre_harvest", "harvest", "post_harvest"):
        day = harvest_days.get(stage_id)
        if day is not None and day <= doy:
            reached = stage_id
    return reached


def harvest_doy(band: Band, cultivar: str) -> int | None:
    days = band.harvest.get(cultivar) or band.harvest.get(DEFAULT_CULTIVAR) or {}
    return days.get("harvest")


def days_to_harvest(band: Band, cultivar: str, now: datetime) -> int | None:
    """Days until the next harvest start (next year's when this year's has passed)."""
    target = harvest_doy(band, cultivar)
    if target is None:
        return None
    doy = day_of_year(now)
    if target >= doy:
        return target - doy
    return 365 - doy + target


def scab_season_window(band: Band) -> tuple[int, int]:
    """Day-of-year window in which primary scab auto-advice is allowed, slack included on both ends.

    Primary season = green_tip .. petal_fall + 21 days (rules_config apple_scab_mills_table.primary_season).
    """
    start = stage_doy(band, "green_tip")
    petal_fall = stage_doy(band, "petal_fall")
    if start is None or petal_fall is None:
        start, petal_fall = band.stages[0][1], band.stages[-1][1]
    return start - SCAB_SEASON_SLACK_DAYS, petal_fall + SCAB_SEASON_AFTER_PETAL_FALL_DAYS + SCAB_SEASON_SLACK_DAYS


def any_band_scab_window(ref: ReferenceData) -> tuple[int, int]:
    """Widest window over all bands: used when a farmer's band is unknown (alerts err on the side of warning)."""
    windows = [scab_season_window(b) for b in ref.bands.values()]
    return min(w[0] for w in windows), max(w[1] for w in windows)


def scab_season_active(ref: ReferenceData, band: Band | None, now: datetime) -> bool:
    start, end = scab_season_window(band) if band else any_band_scab_window(ref)
    return start <= day_of_year(now) <= end


def leaf_spot_season_active(ref: ReferenceData, now: datetime) -> bool:
    """Marssonina / Alternaria weather rule and diagnosis season: from rules_config marssonina active_from_date_mmdd."""
    mmdd = str(cfg(ref.config, "marssonina_alternaria_weather.active_from_date_mmdd", "06-01"))
    month, day = (int(p) for p in mmdd.split("-"))
    return (now.month, now.day) >= (month, day)


def in_spray_season(ref: ReferenceData, farmer: FarmerProfile, crop: str, now: datetime) -> bool:
    """True while sprays are normally being made (used for the stale-history warning)."""
    if crop == "Apple":
        band = band_for(ref, farmer)
        if band is None:
            return NON_APPLE_SEASON_MONTHS[0] <= now.month <= NON_APPLE_SEASON_MONTHS[1]
        doy = day_of_year(now)
        cultivar = cultivar_for(band, farmer)
        harvest_days = band.harvest.get(cultivar) or band.harvest.get(DEFAULT_CULTIVAR) or {}
        end = harvest_days.get("post_harvest", band.stages[-1][1]) + POST_HARVEST_SEASON_GRACE_DAYS
        return band.stages[0][1] <= doy <= end
    return NON_APPLE_SEASON_MONTHS[0] <= now.month <= NON_APPLE_SEASON_MONTHS[1]
