"""Simulated field sensors (data/iot/sensor_readings.csv, about 69k hourly rows, 12 stations).

The file keeps its planted outages (random gaps of 3-35 h, and ST08 offline 10 Jul 06:00 to 14 Jul 18:00 2026) and glitches, exactly as
a real feed would. `latest` never looks past `now`; `is_stale` is the plain age rule, so the scripted ST08 outage turns stale once the
last reading is more than `max_age_hours` old (from 12 Jul 2026 06:00).
"""
from __future__ import annotations

import csv
import threading
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path

from app.clock import IST
from app.domain.types import SensorReading

_Row = tuple[float | None, float | None, float | None, int | None, float | None, float | None]


def _num(value: str) -> float | None:
    try:
        return float(value) if value != "" else None
    except ValueError:
        return None


class MockIoTAdapter:
    def __init__(self, data_dir: Path) -> None:
        self._path = Path(data_dir) / "iot" / "sensor_readings.csv"
        self._lock = threading.Lock()
        self._index: dict[str, tuple[list[datetime], list[_Row]]] | None = None

    def _load(self) -> dict[str, tuple[list[datetime], list[_Row]]]:
        with self._lock:
            if self._index is None:
                self._index = self._read()
            return self._index

    def _read(self) -> dict[str, tuple[list[datetime], list[_Row]]]:
        raw: dict[str, list[tuple[datetime, _Row]]] = {}
        with self._path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    when = datetime.fromisoformat(row["timestamp_ist"]).replace(tzinfo=IST)
                except (KeyError, ValueError):
                    continue
                wetness = _num(row.get("leaf_wetness_min", ""))
                values: _Row = (_num(row.get("temp_c", "")), _num(row.get("rh_pct", "")), _num(row.get("rain_mm", "")),
                                int(wetness) if wetness is not None else None, _num(row.get("soil_moisture_pct", "")),
                                _num(row.get("battery_v", "")))
                raw.setdefault(row["station_id"], []).append((when, values))
        index = {}
        for station, items in raw.items():
            items.sort(key=lambda item: item[0])
            index[station] = ([i[0] for i in items], [i[1] for i in items])
        return index

    def latest(self, station_id: str, now: datetime) -> SensorReading | None:
        times, rows = self._load().get(station_id, ([], []))
        now = now.replace(tzinfo=IST) if now.tzinfo is None else now
        pos = bisect_right(times, now) - 1
        if pos < 0:
            return None
        temp, rh, rain, wetness, soil, battery = rows[pos]
        return SensorReading(station_id=station_id, time=times[pos], temp_c=temp, rh_pct=rh, rain_mm=rain,
                             leaf_wetness_min=wetness, soil_moisture_pct=soil, battery_v=battery)

    def is_stale(self, station_id: str, now: datetime, max_age_hours: int = 48) -> bool:
        reading = self.latest(station_id, now)
        if reading is None:
            return True
        now = now.replace(tzinfo=IST) if now.tzinfo is None else now
        return now - reading.time > timedelta(hours=max_age_hours)
