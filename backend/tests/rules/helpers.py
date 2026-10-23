"""Builders for the rules tests: farmers, spray records, synthetic weather, and replay of the demo data (scenarios S1..S11).

The demo-data side reads data/mock_zoho/advisory_rows_flat.csv and data/weather/*.csv once per session. Weather snapshots
follow the data scripts' conventions: observed hours are rows <= the clock, forecast hours are the following 48 rows, rain
sums use [clock-24h, clock) and [clock, clock+12h / 48h).
"""
from __future__ import annotations

import csv
import json
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo

from app.config import REPO_ROOT, Settings
from app.domain.types import FarmerProfile, ForecastDay, RuleInput, SprayRecord, WeatherHour, WeatherSnapshot
from app.interfaces import RulesEngine
from app.rules.engine import build_rules_engine

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = REPO_ROOT / "data"
SCAB = "Apple___Apple_scab"


def make_settings() -> Settings:
    return Settings(_env_file=None, data_dir=DATA_DIR)  # type: ignore[call-arg]


def make_engine(disabled=None) -> RulesEngine:
    return build_rules_engine(make_settings(), disabled)


def at(text: str) -> datetime:
    """'2026-05-12 16:00' -> aware IST datetime."""
    return datetime.fromisoformat(text).replace(tzinfo=IST)


# ---------------------------------------------------------------------------------------------------------- synthetic inputs
def farmer(**overrides) -> FarmerProfile:
    base = dict(
        id="F-T1", name="Test Farmer", phone="+910000000001", language="en", station_id="ST01", elevation_m=1800,
        phenology_band="B2", crops=["Apple"], primary_crop="Apple", primary_variety="Royal_Delicious",
    )
    base.update(overrides)
    return FarmerProfile(**base)


def spray(when: str, product_id: str | None = None, **fields) -> SprayRecord:
    return SprayRecord(sprayed_at=at(when), product_id=product_id, **fields)


def nutrient(when: str, name: str = "Zinc, Boron") -> SprayRecord:
    return SprayRecord(sprayed_at=at(when), active_ingredient=name, nutrient=True)


def rule_input(*, now: str = "2026-04-25 10:00", crop_id: str = "Apple", disease_id: str | None = SCAB, confidence: float = 0.9,
               history: list[SprayRecord] | None = None, weather: WeatherSnapshot | None = None, farmer_: FarmerProfile | None = None,
               days_to_harvest: int | None = None, language: str = "en") -> RuleInput:
    return RuleInput(
        farmer=farmer_ or farmer(), crop_id=crop_id, disease_id=disease_id, disease_confidence=confidence, now=at(now),
        history=history or [], weather=weather, days_to_harvest=days_to_harvest, language=language,  # type: ignore[arg-type]
    )


def weather_hour(when: datetime, temp: float = 12.0, rh: float = 60.0, rain: float = 0.0) -> WeatherHour:
    return WeatherHour(time=when, temp_c=temp, rh_pct=rh, rain_mm=rain, leaf_wet=rain >= 0.1 or rh >= 90)


def snapshot(now: datetime, past: list[WeatherHour] | None = None, future: list[WeatherHour] | None = None, *, temp_c: float | None = 12.0,
             rain_next_12h_mm: float | None = None, rain_last_24h_mm: float = 0.0, stale: bool = False) -> WeatherSnapshot:
    future = future or []
    if rain_next_12h_mm is None:
        rain_next_12h_mm = round(sum(h.rain_mm for h in future if h.time < now + timedelta(hours=12)), 1)
    return WeatherSnapshot(
        station_id="ST01", as_of=now, temp_c=temp_c, rh_pct=60.0, rain_last_24h_mm=rain_last_24h_mm,
        rain_next_12h_mm=rain_next_12h_mm, rain_next_48h_mm=round(sum(h.rain_mm for h in future), 1),
        hourly_past=past or [], hourly_future=future, stale=stale,
    )


def hourly(end: datetime, hours: int, *, temp: float = 12.0, rh: float = 60.0, rain: float = 0.0) -> list[WeatherHour]:
    """`hours` identical hourly rows ending at `end` (inclusive), oldest first."""
    return [weather_hour(end - timedelta(hours=hours - 1 - i), temp, rh, rain) for i in range(hours)]


def series(end: datetime, hours: int, fn) -> list[WeatherHour]:
    """`hours` hourly rows ending at `end`; fn(time) -> (temp, rh, rain)."""
    rows = []
    for i in range(hours):
        when = end - timedelta(hours=hours - 1 - i)
        temp, rh, rain = fn(when)
        rows.append(weather_hour(when, temp, rh, rain))
    return rows


def scab_weather(now: str, *, wet_hours: int = 12, temp: float = 10.0, ended_hours_ago: int = 0, rain_next_12h_mm: float = 0.0) -> WeatherSnapshot:
    """14 dry days, then a wet run of `wet_hours` hours ending `ended_hours_ago` hours before now (rain 0.5 mm, RH 95)."""
    when = at(now)
    last_wet = when - timedelta(hours=ended_hours_ago)

    def row(t):
        wet = last_wet - timedelta(hours=wet_hours - 1) <= t <= last_wet
        return temp, (95.0 if wet else 50.0), (0.5 if wet else 0.0)

    return snapshot(when, series(when, 24 * 14, row), [], temp_c=temp, rain_next_12h_mm=rain_next_12h_mm)


def dry_weather(now: str = "2026-04-25 10:00", *, temp: float = 12.0) -> WeatherSnapshot:
    when = at(now)
    return snapshot(when, hourly(when, 24 * 14, temp=temp), hourly(when + timedelta(hours=48), 48, temp=temp), temp_c=temp)


def engine_with_products(extra, disabled=None):
    """An engine on the real reference data plus extra Product rows (to test rules the shipped master has no row for)."""
    from dataclasses import replace

    from app.rules.data import load_reference
    from app.rules.engine import RuleBasedEngine

    ref = load_reference(DATA_DIR)
    products = (*ref.products, *extra)
    return RuleBasedEngine(replace(ref, products=products, products_by_id={p.product_id: p for p in products},
                                   crops={p.crop.lower(): p.crop for p in products if p.usable}), disabled)


def fake_product(product_id: str, active: str, *, crop: str = "Apple", category: str = "fungicide", code: str | None = None,
                 targets: tuple[str, ...] = (SCAB,), stage: str = "petal_fall", wp: int | None = 10, ban: str = "registered"):
    from app.rules.codes import components
    from app.rules.data import Product, active_parts

    return Product(
        product_id=product_id, crop=crop, active_ingredient=active, active_ingredient_hi=None, formulation=None, brand_example=None,
        category=category, frac_irac_code=code, components=components(code), behaviour="contact", targets=frozenset(targets), stage=stage,
        dose_min=1.0, dose_max=1.0, dose_unit="g/200L", waiting_period_days=wp, ban_status=ban, use_note=None, usable=True,
        hp_brand_group=None, hp_brands=(), source_ref=None, confidence="V", actives=active_parts(active),
    )


# ---------------------------------------------------------------------------------------------------------- demo data (real files)
@dataclass(frozen=True)
class Station:
    times: list[datetime]
    rows: list[tuple[datetime, float, float, float]]      # time, temp, rh, rain


@dataclass(frozen=True)
class World:
    weather: dict[str, Station]
    zoho: dict[str, list[dict[str, str]]]
    farmers: dict[str, FarmerProfile]
    scenarios: dict[str, dict]


def _csv(path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@cache
def world() -> World:
    raw: dict[str, list[tuple[datetime, float, float, float]]] = {}
    for r in _csv(DATA_DIR / "weather" / "weather_hourly_raw.csv"):
        raw.setdefault(r["station_id"], []).append(
            (datetime.fromisoformat(r["time_ist"]).replace(tzinfo=IST), float(r["temperature_2m"]),
             float(r["relative_humidity_2m"]), float(r["precipitation"])))
    stations = {sid: Station([row[0] for row in rows], rows) for sid, rows in raw.items()}

    zoho: dict[str, list[dict[str, str]]] = {}
    for r in _csv(DATA_DIR / "mock_zoho" / "advisory_rows_flat.csv"):
        zoho.setdefault(r["farmer_id"], []).append(r)

    farmers: dict[str, FarmerProfile] = {}
    for r in _csv(DATA_DIR / "farmers.csv"):
        crops = [r["primary_crop"], *[c for c in r["other_crops"].split(";") if c]]
        farmers[r["farmer_id"]] = FarmerProfile(
            id=r["farmer_id"], name=r["name"], phone="+910000000000", language=r["preferred_language"] or "hi",  # type: ignore[arg-type]
            village=r["village"], district=r["district"], station_id=r["station_id"], elevation_m=float(r["orchard_elevation_m"]),
            phenology_band=r["phenology_band"], crops=crops, primary_crop=r["primary_crop"],
            primary_variety=r["primary_variety"] or None, zoho_contact_id=r["zoho_contact_id"],
        )
    scenarios = {s["id"]: s for s in json.loads((DATA_DIR / "demo_scenarios.json").read_text(encoding="utf-8"))["scenarios"]}
    return World(stations, zoho, farmers, scenarios)


def scenario_clock(scenario_id: str) -> datetime:
    return datetime.fromisoformat(world().scenarios[scenario_id]["demo_clock"]).replace(tzinfo=IST)


def _row_to_record(r: dict[str, str]) -> SprayRecord:
    advisor = r["row_kind"] == "advisor"
    text = r["Name"] if advisor else r["Self_Sprayed"]
    return SprayRecord(
        sprayed_at=datetime.fromisoformat(r["_spray_datetime"]).replace(tzinfo=IST),
        product_id=r["_product_id"] or None,
        active_ingredient=None if advisor else (text or None),
        frac_irac_code=(r["F_T_A_Frac_Group"] if advisor else r["Self_Spray_Frac_Group"]) or None,
        trade_name=(r["Name"] if advisor else r["Self_Spray_Trade_Name"]) or None,
        nutrient=r["_nutrient"] == "true",
        rain_mm_since=float(r["Total_Rainfall_Since_Last_Spray"]) if r["Total_Rainfall_Since_Last_Spray"] else None,
        source="zoho",
    )


def history_for(farmer_id: str, until: datetime) -> list[SprayRecord]:
    """The farmer's Zoho rows up to the clock (rows dated after it are never returned)."""
    records = [_row_to_record(r) for r in world().zoho.get(farmer_id, [])]
    return sorted((rec for rec in records if rec.sprayed_at <= until), key=lambda rec: rec.sprayed_at)


def snapshot_at(station_id: str, now: datetime) -> WeatherSnapshot:
    station = world().weather[station_id]

    def window(start: datetime, end: datetime, *, include_end: bool = False):
        lo = bisect_left(station.times, start)
        hi = bisect_right(station.times, end) if include_end else bisect_left(station.times, end)
        return station.rows[lo:hi]

    def to_hour(row) -> WeatherHour:
        return WeatherHour(time=row[0], temp_c=row[1], rh_pct=row[2], rain_mm=row[3], leaf_wet=row[3] >= 0.1 or row[2] >= 90)

    past = [to_hour(r) for r in window(now - timedelta(days=14), now, include_end=True)]
    future = [to_hour(r) for r in window(now + timedelta(seconds=1), now + timedelta(hours=48), include_end=True)]
    current = window(now, now + timedelta(hours=1))
    daily: list[ForecastDay] = []
    for offset in range(1, 8):
        day = now.date() + timedelta(days=offset)
        rows = window(datetime(day.year, day.month, day.day, tzinfo=IST), datetime(day.year, day.month, day.day, tzinfo=IST) + timedelta(days=1))
        if rows:
            daily.append(ForecastDay(day=day, tmin_c=min(r[1] for r in rows), tmax_c=max(r[1] for r in rows), rain_mm=round(sum(r[3] for r in rows), 1)))
    return WeatherSnapshot(
        station_id=station_id, as_of=now, temp_c=current[0][1] if current else None, rh_pct=current[0][2] if current else None,
        rain_last_24h_mm=round(sum(r[3] for r in window(now - timedelta(hours=24), now)), 1),
        rain_next_12h_mm=round(sum(r[3] for r in window(now, now + timedelta(hours=12))), 1),
        rain_next_48h_mm=round(sum(r[3] for r in window(now, now + timedelta(hours=48))), 1),
        hourly_past=past, hourly_future=future, daily_forecast=daily, source="csv",
    )


def scenario_input(scenario_id: str, disease_id: str | None, *, farmer_id: str | None = None, crop_id: str | None = None,
                   confidence: float = 0.9, language: str = "en") -> RuleInput:
    """RuleInput for a scenario: farmer, history and weather exactly as the app would see them at the scenario clock."""
    scenario = world().scenarios[scenario_id]
    now = scenario_clock(scenario_id)
    fid = farmer_id or scenario["farmer_id"]
    person = world().farmers[fid]
    return RuleInput(
        farmer=person, crop_id=crop_id or scenario["crop"], disease_id=disease_id, disease_confidence=confidence, now=now,
        history=history_for(fid, now), weather=snapshot_at(scenario["station_id"], now), language=language,  # type: ignore[arg-type]
    )


def apple_farmers_at(station_id: str) -> list[FarmerProfile]:
    return [f for f in world().farmers.values() if f.station_id == station_id and f.primary_crop == "Apple"]


def day_of(value: datetime) -> date:
    return value.date()
