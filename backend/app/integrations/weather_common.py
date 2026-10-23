"""Builds a WeatherSnapshot from an hourly series. Shared by the CSV archive adapter and the Open-Meteo adapter.

Conventions (match data/demo_scenarios.json facts, which are computed the same way):
  * `now` is floored to the hour; a row stamped T describes the instant T.
  * hourly_past   = rows with time <= now, the last 14 days, oldest first (includes the current hour).
  * hourly_future = rows with time > now, up to 48 h.
  * rain_last_24h = rain in [now-24h, now); rain_next_12h / rain_next_48h = rain in [now, now+N h).
  * leaf_wet is the proxy from rules_config.json: rain >= 0.1 mm or RH >= 90 %.
  * daily_forecast = today and the next 6 days (7 days) from the series, partial days at the end of the data are kept.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.clock import IST
from app.domain.types import ForecastDay, WeatherHour, WeatherSnapshot
from app.integrations.errors import WeatherUnavailable

PAST_DAYS = 14
FUTURE_HOURS = 48
FORECAST_DAYS = 7
STALE_AFTER = timedelta(hours=6)
WET_RAIN_MM = 0.1
WET_RH_PCT = 90.0


@dataclass(frozen=True)
class HourlySeries:
    """Parallel arrays, sorted by time (timezone-aware IST)."""
    times: list[datetime]
    temp_c: list[float]
    rh_pct: list[float]
    rain_mm: list[float]


def floor_hour(value: datetime) -> datetime:
    value = value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)
    return value.replace(minute=0, second=0, microsecond=0)


def _hour(series: HourlySeries, i: int) -> WeatherHour:
    rain, rh = series.rain_mm[i], series.rh_pct[i]
    return WeatherHour(time=series.times[i], temp_c=series.temp_c[i], rh_pct=rh, rain_mm=rain,
                       leaf_wet=rain >= WET_RAIN_MM or rh >= WET_RH_PCT)


def _rain_between(series: HourlySeries, start: datetime, end: datetime) -> float:
    """Rain in [start, end)."""
    lo, hi = bisect_left(series.times, start), bisect_left(series.times, end)
    return round(sum(series.rain_mm[lo:hi]), 1)


def _daily(series: HourlySeries, first_day: date) -> list[ForecastDay]:
    days: list[ForecastDay] = []
    for offset in range(FORECAST_DAYS):
        day = first_day + timedelta(days=offset)
        start = datetime(day.year, day.month, day.day, tzinfo=IST)
        lo, hi = bisect_left(series.times, start), bisect_left(series.times, start + timedelta(days=1))
        if hi > lo:
            temps = series.temp_c[lo:hi]
            days.append(ForecastDay(day=day, tmin_c=min(temps), tmax_c=max(temps), rain_mm=round(sum(series.rain_mm[lo:hi]), 1)))
    return days


def build_snapshot(series: HourlySeries, station_id: str | None, now: datetime, source: str) -> WeatherSnapshot:
    now_h = floor_hour(now)
    end = bisect_right(series.times, now_h)
    if end == 0:
        raise WeatherUnavailable(f"no weather data at or before {now_h.isoformat()}")
    start = bisect_right(series.times, now_h - timedelta(days=PAST_DAYS))
    future_end = bisect_right(series.times, now_h + timedelta(hours=FUTURE_HOURS))
    current = end - 1
    return WeatherSnapshot(
        station_id=station_id,
        as_of=now if now.tzinfo else now.replace(tzinfo=IST),
        temp_c=series.temp_c[current],
        rh_pct=series.rh_pct[current],
        rain_last_24h_mm=_rain_between(series, now_h - timedelta(hours=24), now_h),
        rain_next_12h_mm=_rain_between(series, now_h, now_h + timedelta(hours=12)),
        rain_next_48h_mm=_rain_between(series, now_h, now_h + timedelta(hours=48)),
        hourly_past=[_hour(series, i) for i in range(start, end)],
        hourly_future=[_hour(series, i) for i in range(end, future_end)],
        daily_forecast=_daily(series, now_h.date()),
        stale=now_h - series.times[current] > STALE_AFTER,
        source=source,
    )
