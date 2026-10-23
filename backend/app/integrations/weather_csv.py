"""Weather from the demo archive (data/weather/weather_hourly_raw.csv, real Open-Meteo ERA5 for 12 stations).

Hours after `now` come from the same archive, i.e. a 'perfect forecast'. The archive covers 15 Feb to 17 Oct 2026 only: later
timestamps get the last known hours and stale=True.
"""
from __future__ import annotations

import csv
import threading
from datetime import datetime
from pathlib import Path

from app.clock import IST
from app.domain.types import WeatherSnapshot
from app.integrations.errors import WeatherUnavailable
from app.integrations.reference import load_stations, nearest_station
from app.integrations.weather_common import HourlySeries, build_snapshot


class CsvWeatherAdapter:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._lock = threading.Lock()
        self._series: dict[str, HourlySeries] | None = None

    def _load(self) -> dict[str, HourlySeries]:
        with self._lock:
            if self._series is None:
                self._series = self._read()
            return self._series

    def _read(self) -> dict[str, HourlySeries]:
        raw: dict[str, list[tuple[datetime, float, float, float]]] = {}
        path = self._data_dir / "weather" / "weather_hourly_raw.csv"
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    point = (datetime.fromisoformat(row["time_ist"]).replace(tzinfo=IST), float(row["temperature_2m"]),
                             float(row["relative_humidity_2m"]), float(row["precipitation"]))
                except (KeyError, ValueError):
                    continue          # a blank or malformed hour is skipped, never guessed
                raw.setdefault(row["station_id"], []).append(point)
        out = {}
        for station, points in raw.items():
            points.sort(key=lambda p: p[0])
            out[station] = HourlySeries(times=[p[0] for p in points], temp_c=[p[1] for p in points],
                                        rh_pct=[p[2] for p in points], rain_mm=[p[3] for p in points])
        return out

    def _resolve(self, station_id: str | None, lat: float | None, lon: float | None) -> str:
        series = self._load()
        if station_id and station_id in series:
            return station_id
        if lat is not None and lon is not None:
            near = nearest_station(load_stations(self._data_dir), lat, lon)
            if near is not None and near.station_id in series:
                return near.station_id
        raise WeatherUnavailable("no known weather station for the given station id or coordinates")

    def snapshot(self, station_id: str | None, lat: float | None, lon: float | None, now: datetime) -> WeatherSnapshot:
        station = self._resolve(station_id, lat, lon)
        return build_snapshot(self._load()[station], station, now, source="csv")
