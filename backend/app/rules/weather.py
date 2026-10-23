"""Weather-derived disease rules, ported from data/scripts/weather_rules.py without pandas.

Hours come from WeatherSnapshot.hourly_past (observed, time <= now) and hourly_future (forecast, time > now). Leaf wetness is a
proxy: rain >= 0.1 mm or RH >= 90 % (a True leaf_wet flag also counts). Everything is a pure function of the hours given.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.clock import IST
from app.domain.types import WeatherHour, WeatherSnapshot
from app.rules.data import cfg

HOUR = timedelta(hours=1)
WET_RAIN_MM = 0.1
WET_RH_PCT = 90.0
MILLS_GAP_HOURS = 8
YELLOW_FRACTION = 0.7
FLOAT_TOLERANCE = 1e-6


def as_ist(value: datetime) -> datetime:
    """Aware IST datetime; naive values are taken to be IST (weather CSVs are naive IST)."""
    return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)


@dataclass(frozen=True)
class Hour:
    t: datetime
    temp: float
    rh: float
    rain: float
    wet: bool


def _hour(h: WeatherHour) -> Hour:
    wet = bool(h.leaf_wet) or h.rain_mm >= WET_RAIN_MM or h.rh_pct >= WET_RH_PCT
    return Hour(as_ist(h.time), float(h.temp_c), float(h.rh_pct), float(h.rain_mm), wet)


def merged_hours(weather: WeatherSnapshot) -> list[Hour]:
    """Past and future hours, sorted, one per timestamp (the observed value wins over the forecast)."""
    by_time: dict[datetime, Hour] = {}
    for h in weather.hourly_future:
        by_time[as_ist(h.time)] = _hour(h)
    for h in weather.hourly_past:
        by_time[as_ist(h.time)] = _hour(h)
    return [by_time[t] for t in sorted(by_time)]


def observed(hours: list[Hour], now: datetime) -> list[Hour]:
    return [h for h in hours if h.t <= now]


def forecast(hours: list[Hour], now: datetime) -> list[Hour]:
    return [h for h in hours if h.t > now]


def rain_between(hours: list[Hour], start: datetime, end: datetime) -> float:
    """mm of rain in [start, end): same convention as the data scripts' rain_after/rain_between."""
    return sum(h.rain for h in hours if start <= h.t < end)


def rain_after_spray(hours: list[Hour], sprayed_at: datetime, now: datetime, window_hours: int) -> tuple[float, float]:
    """(observed mm, observed + forecast mm) in the `window_hours` after a spray."""
    end = sprayed_at + timedelta(hours=window_hours)
    seen = sum(h.rain for h in hours if sprayed_at <= h.t < end and h.t <= now)
    total = rain_between(hours, sprayed_at, end)
    return seen, total


# ---------------------------------------------------------------------------------------------------------- scab / Mills
def mills_hours(config: dict[str, Any], mean_temp_c: float) -> int | None:
    """Minimum wet hours for a scab infection at the mean temperature (None = below the table: no infection)."""
    rows = cfg(config, "apple_scab_mills_table.rows", [])
    mean_temp_c += FLOAT_TOLERANCE                      # a mean of identical 16.1 values can come out as 16.0999999
    if not rows or mean_temp_c < rows[0]["t_c_from"]:
        return None
    need = None
    for row in rows:
        if mean_temp_c >= row["t_c_from"]:
            need = int(row["min_wet_hours"])
    return need


@dataclass(frozen=True)
class WetRun:
    start: datetime
    end: datetime                 # last wet hour of the (joined) run
    wet_hours: int
    span_hours: int
    mean_temp_c: float
    need_hours: int | None        # Mills requirement at the run's mean temperature
    reached_at: datetime | None   # first hour at which the running wet hours met the running-mean requirement
    rain_mm: float


def wet_runs(config: dict[str, Any], hours: list[Hour], gap_hours: int = MILLS_GAP_HOURS) -> list[WetRun]:
    """Wet runs joined when separated by fewer than `gap_hours` dry hours, each with its Mills verdict."""
    runs: list[list[int]] = []
    i, n = 0, len(hours)
    while i < n:
        if hours[i].wet:
            j = i
            while j + 1 < n and hours[j + 1].wet and hours[j + 1].t - hours[j].t <= HOUR:
                j += 1
            runs.append([i, j])
            i = j + 1
        else:
            i += 1
    merged: list[list[int]] = []
    for run in runs:
        if merged:
            gap = (hours[run[0]].t - hours[merged[-1][1]].t) / HOUR - 1
            if gap < gap_hours:
                merged[-1][1] = run[1]
                continue
        merged.append(run[:])

    out: list[WetRun] = []
    for a, b in merged:
        seg = hours[a:b + 1]
        wet = sum(1 for h in seg if h.wet)
        mean_t = sum(h.temp for h in seg) / len(seg)
        reached: datetime | None = None
        cum_wet, cum_temp = 0, 0.0
        for k, h in enumerate(seg, start=1):
            cum_wet += 1 if h.wet else 0
            cum_temp += h.temp
            need_k = mills_hours(config, cum_temp / k)
            if need_k is not None and cum_wet >= need_k:
                reached = h.t
                break
        out.append(WetRun(seg[0].t, seg[-1].t, wet, len(seg), round(mean_t, 1), mills_hours(config, mean_t), reached,
                          round(sum(h.rain for h in seg), 1)))
    return out


# ---------------------------------------------------------------------------------------------------------- Marssonina
def complete_days(hours: list[Hour]) -> dict[date, list[Hour]]:
    """Calendar days with all 24 hourly rows."""
    days: dict[date, list[Hour]] = {}
    for h in hours:
        days.setdefault(h.t.date(), []).append(h)
    return {d: v for d, v in days.items() if len({x.t.hour for x in v}) == 24}


def leaf_spot_run_days(config: dict[str, Any], hours: list[Hour], now: datetime) -> tuple[int, dict[str, float] | None]:
    """Consecutive qualifying days (mean temp > 20 and mean RH >= 70, from 1 June) ending on the latest complete day.

    Returns (run length, stats of the latest complete day). A latest complete day that does not qualify gives 0.
    """
    temp_min = float(cfg(config, "marssonina_alternaria_weather.mean_temp_c_min", 20))
    rh_min = float(cfg(config, "marssonina_alternaria_weather.mean_rh_pct_min", 70))
    month, day_of_month = (int(p) for p in str(cfg(config, "marssonina_alternaria_weather.active_from_date_mmdd", "06-01")).split("-"))
    days = complete_days(observed(hours, now))
    if not days:
        return 0, None
    ordered = sorted(days)
    last_stats: dict[str, float] | None = None
    run = 0
    previous: date | None = None
    for d in ordered:
        rows = days[d]
        mean_t = sum(h.temp for h in rows) / 24
        mean_rh = sum(h.rh for h in rows) / 24
        ok = mean_t > temp_min and mean_rh >= rh_min and (d.month, d.day) >= (month, day_of_month)
        consecutive = previous is not None and (d - previous).days == 1
        run = (run + 1 if consecutive else 1) if ok else 0
        previous = d
        last_stats = {"mean_temp_c": round(mean_t, 1), "mean_rh_pct": round(mean_rh, 0), "rain_mm": round(sum(h.rain for h in rows), 1)}
    return run, last_stats


# ---------------------------------------------------------------------------------------------------------- late blight
def late_blight_counts(config: dict[str, Any], hours: list[Hour], now: datetime) -> dict[str, Any]:
    """NIPHM 7-day rule at `now`: hours with temp in range and hours with RH above the limit in the last 7 days."""
    window_days = int(cfg(config, "late_blight_niphm.window_days", 7))
    lo, hi = cfg(config, "late_blight_niphm.hours_temp_between_c", [7.2, 26.6])
    rh_limit = float(cfg(config, "late_blight_niphm.hours_rh_above_pct", 85))
    need_temp = int(cfg(config, "late_blight_niphm.hours_temp_min_total", 115))
    need_rh = int(cfg(config, "late_blight_niphm.hours_rh_min_total", 90))
    start = now - timedelta(hours=24 * window_days - 1)
    window = [h for h in hours if start <= h.t <= now]
    temp_hours = sum(1 for h in window if lo <= h.temp <= hi)
    rh_hours = sum(1 for h in window if h.rh > rh_limit)
    return {
        "temp_hours": temp_hours, "rh_hours": rh_hours, "need_temp_hours": need_temp, "need_rh_hours": need_rh,
        "hours_available": len(window), "hours_expected": 24 * window_days,
        "met": temp_hours >= need_temp and rh_hours >= need_rh,
    }
