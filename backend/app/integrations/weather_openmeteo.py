"""Live weather and forecast from Open-Meteo (forecast API, past_days=14, forecast_days=7, hourly, timezone Asia/Kolkata).

LICENCE: the free api.open-meteo.com endpoint is for NON-COMMERCIAL use only. A commercial deployment needs a paid plan: set
OPEN_METEO_API_KEY and the adapter switches to customer-api.open-meteo.com (see docs/design-notes/integrations.md).

`now` must be the real current time: the forecast API only serves about 14 days back and 7 days ahead of the real today.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import httpx

from app.clock import IST
from app.domain.types import WeatherSnapshot
from app.integrations.errors import WeatherUnavailable
from app.integrations.reference import load_stations
from app.integrations.weather_common import HourlySeries, build_snapshot

FREE_URL = "https://api.open-meteo.com/v1/forecast"
CUSTOMER_URL = "https://customer-api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 30 * 60
MAX_CACHED_PLACES = 512          # each entry is 21 days of hourly data (tens of KB): bound the memory
MAX_CALLS_PER_HOUR = 600         # the 12 demo stations need about 24 a hour; the rest is headroom, not an open tap
_HOURLY = "temperature_2m,relative_humidity_2m,precipitation"


class OpenMeteoAdapter:
    def __init__(self, data_dir: Path | None = None, client: httpx.Client | None = None, ttl_seconds: float = CACHE_TTL_SECONDS,
                 monotonic=time.monotonic, api_key: str | None = None) -> None:  # noqa: ANN001
        self._data_dir = Path(data_dir) if data_dir else None
        self._api_key = api_key or None                  # from Settings (env or .env); the OPEN_METEO_API_KEY variable is the fallback
        self._http = client or httpx.Client(timeout=10.0)
        self._ttl = ttl_seconds
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._cache: dict[tuple[float, float], tuple[float, HourlySeries]] = {}
        self._calls: deque[float] = deque()              # times of the recent outbound requests (the calls are billed or quota-bound)

    def _take_call_budget(self) -> None:
        """A scan may carry client-chosen coordinates, so the number of distinct places is not under our control: cap the
        outbound requests per hour (the scan then simply runs without weather, like any other weather outage)."""
        now = self._monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] >= 3600.0:
                self._calls.popleft()
            if len(self._calls) >= MAX_CALLS_PER_HOUR:
                raise WeatherUnavailable("Open-Meteo request budget for this hour is used up")
            self._calls.append(now)

    def _remember(self, key: tuple[float, float], series: HourlySeries) -> None:
        now = self._monotonic()
        with self._lock:
            self._cache[key] = (now, series)
            if len(self._cache) > MAX_CACHED_PLACES:     # expired places first, then the oldest: memory stays bounded
                for stale in [k for k, (stamp, _) in self._cache.items() if now - stamp >= self._ttl]:
                    del self._cache[stale]
                while len(self._cache) > MAX_CACHED_PLACES:
                    del self._cache[next(iter(self._cache))]

    def _coordinates(self, station_id: str | None, lat: float | None, lon: float | None) -> tuple[float, float, str | None]:
        if lat is not None and lon is not None:
            return lat, lon, station_id
        if station_id and self._data_dir is not None:
            station = load_stations(self._data_dir).get(station_id)
            if station is not None:
                return station.grid_lat, station.grid_lon, station_id
        raise WeatherUnavailable("Open-Meteo needs coordinates or a known station id")

    def _fetch(self, lat: float, lon: float) -> HourlySeries:
        key = (round(lat, 3), round(lon, 3))
        with self._lock:
            hit = self._cache.get(key)
            if hit and self._monotonic() - hit[0] < self._ttl:
                return hit[1]
        self._take_call_budget()
        api_key = self._api_key or os.environ.get("OPEN_METEO_API_KEY")
        params: dict[str, str | int | float] = {"latitude": lat, "longitude": lon, "hourly": _HOURLY, "past_days": 14,
                                                "forecast_days": 7, "timezone": "Asia/Kolkata"}
        if api_key:
            params["apikey"] = api_key
        try:
            resp = self._http.get(CUSTOMER_URL if api_key else FREE_URL, params=params)
        except httpx.HTTPError as exc:
            raise WeatherUnavailable(f"Open-Meteo request failed: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise WeatherUnavailable(f"Open-Meteo answered HTTP {resp.status_code}")
        series = self._parse(resp)
        self._remember(key, series)
        return series

    @staticmethod
    def _parse(resp: httpx.Response) -> HourlySeries:
        try:
            hourly = resp.json()["hourly"]
            stamps, temps, rhs, rains = (hourly["time"], hourly["temperature_2m"], hourly["relative_humidity_2m"],
                                         hourly["precipitation"])
            if not len(stamps) == len(temps) == len(rhs) == len(rains):
                raise ValueError("series lengths differ")
            points = []
            for stamp, temp, rh, rain in zip(stamps, temps, rhs, rains, strict=True):
                if temp is None or rh is None:
                    continue          # a gap is skipped, never guessed
                points.append((datetime.fromisoformat(stamp).replace(tzinfo=IST), float(temp), float(rh), float(rain or 0.0)))
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherUnavailable("Open-Meteo returned an unexpected payload") from exc
        points.sort(key=lambda p: p[0])
        return HourlySeries(times=[p[0] for p in points], temp_c=[p[1] for p in points], rh_pct=[p[2] for p in points],
                            rain_mm=[p[3] for p in points])

    def snapshot(self, station_id: str | None, lat: float | None, lon: float | None, now: datetime) -> WeatherSnapshot:
        latitude, longitude, station = self._coordinates(station_id, lat, lon)
        return build_snapshot(self._fetch(latitude, longitude), station, now, source="openmeteo")
