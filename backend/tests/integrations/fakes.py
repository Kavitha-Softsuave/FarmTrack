"""Shared fakes for the integrations, alerts and admin tests (no dependency on other agents' code or on tests/api)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.clock import IST, Clock
from app.config import Settings
from app.db.models import AlertRow, DeviceRow, FarmerRow, SprayLogRow
from app.domain.types import LocalizedText, RiskItem, Severity, SprayRecord, WeatherSnapshot

NOW = datetime(2026, 5, 12, 8, 0, tzinfo=IST)


def risk(kind: str, level: Severity | str = Severity.yellow, episode: str | None = None, **detail: Any) -> RiskItem:
    if episode:
        detail["episode"] = episode
    return RiskItem(id=kind, level=Severity(level), title=LocalizedText(en=f"{kind} title", hi=f"{kind} शीर्षक"),
                    text=LocalizedText(en=f"{kind} advice.", hi=f"{kind} सलाह।"), detail=detail)


class FakeRules:
    """evaluate_risks returns `risks` (a list, or a callable (farmer, weather, now, history) -> list)."""

    def __init__(self, risks: list[RiskItem] | Callable[..., list[RiskItem]] | None = None) -> None:
        self.risks = risks or []
        self.calls: list[dict[str, Any]] = []

    def evaluate_risks(self, farmer, weather, now, history):  # noqa: ANN001, ANN201
        self.calls.append({"farmer": farmer, "weather": weather, "now": now, "history": history})
        return self.risks(farmer, weather, now, history) if callable(self.risks) else list(self.risks)


class FakeWeather:
    def __init__(self, stale: bool = False, fail_for: set[str] | None = None) -> None:
        self.stale = stale
        self.fail_for = fail_for or set()
        self.calls: list[str | None] = []

    def snapshot(self, station_id, lat, lon, now):  # noqa: ANN001, ANN201
        self.calls.append(station_id)
        if station_id in self.fail_for:
            raise RuntimeError("weather down")
        return WeatherSnapshot(station_id=station_id, as_of=now, temp_c=15.0, rh_pct=80.0, stale=self.stale, source="fake")


class FakeIoT:
    def __init__(self, stale_stations: set[str] | None = None, raises: bool = False) -> None:
        self.stale_stations = stale_stations or set()
        self.raises = raises

    def latest(self, station_id, now):  # noqa: ANN001, ANN201
        return None

    def is_stale(self, station_id, now, max_age_hours=48):  # noqa: ANN001, ANN201
        if self.raises:
            raise RuntimeError("iot down")
        return station_id in self.stale_stations


class FakeZoho:
    def __init__(self, histories: dict[str, list[SprayRecord]] | None = None, raises: bool = False) -> None:
        self.histories = histories or {}
        self.raises = raises

    def get_farmer(self, farmer_id):  # noqa: ANN001, ANN201
        return None

    def get_history(self, farmer_id, until=None):  # noqa: ANN001, ANN201
        if self.raises:
            raise RuntimeError("zoho down")
        return [r for r in self.histories.get(farmer_id, []) if until is None or r.sprayed_at <= until]

    def write_spray(self, farmer_id, record):  # noqa: ANN001, ANN201
        return True

    def write_diagnosis(self, farmer_id, payload):  # noqa: ANN001, ANN201
        return True


class FakePush:
    def __init__(self, result: bool = True, raises: bool = False) -> None:
        self.result = result
        self.raises = raises
        self.sent: list[dict[str, Any]] = []

    def send(self, token, title, body, data=None):  # noqa: ANN001, ANN201
        if self.raises:
            raise RuntimeError("push down")
        self.sent.append({"token": token, "title": title, "body": body, "data": data})
        return self.result


@dataclass
class FakeContainer:
    settings: Settings
    clock: Clock
    rules: Any = field(default_factory=FakeRules)
    zoho: Any = field(default_factory=FakeZoho)
    iot: Any = field(default_factory=FakeIoT)
    weather: Any = field(default_factory=FakeWeather)
    push: Any = field(default_factory=FakePush)
    audio: Any = None


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Settings that ignore the repo-root .env (it holds real secrets) and keep storage in tmp_path."""
    values: dict[str, Any] = {"env": "test", "storage_dir": tmp_path / "storage", "demo_clock": "2026-05-12T08:00:00+05:30"}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_container(tmp_path: Path, now: datetime = NOW, **parts: Any) -> FakeContainer:
    return FakeContainer(settings=make_settings(tmp_path), clock=Clock(now), **parts)


def farmer_row(farmer_id: str = "F900", station_id: str | None = "ST05", **overrides: Any) -> FarmerRow:
    digits = "".join(ch for ch in farmer_id if ch.isdigit()) or "0"
    values: dict[str, Any] = {
        "id": farmer_id, "name": f"Test Farmer {farmer_id}", "phone": f"+91000{digits.zfill(7)}", "language": "en",
        "district": "Shimla", "village": "Jubbal", "station_id": station_id, "elevation_m": 2119.0, "phenology_band": "B3",
        "crops": ["Apple"], "primary_crop": "Apple", "primary_variety": "Royal_Delicious", "created_at": NOW,
    }
    values.update(overrides)
    return FarmerRow(**values)


def device_row(farmer_id: str, token: str = "token-abcdef-1234") -> DeviceRow:
    return DeviceRow(farmer_id=farmer_id, platform="android", push_token=token, updated_at=NOW)


def spray_log_row(farmer_id: str, sprayed_at: datetime, product_id: str | None = "P001", **overrides: Any) -> SprayLogRow:
    values: dict[str, Any] = {"farmer_id": farmer_id, "crop_id": "Apple", "product_id": product_id, "product_name": None,
                              "sprayed_at": sprayed_at, "created_at": sprayed_at}
    values.update(overrides)
    return SprayLogRow(**values)


def all_alerts(session) -> list[AlertRow]:  # noqa: ANN001
    from sqlalchemy import select

    return list(session.scalars(select(AlertRow).order_by(AlertRow.farmer_id, AlertRow.dedupe_key)).all())
