import csv
import json
from datetime import datetime, timedelta

import pytest

from app.clock import IST
from app.config import Settings
from app.integrations.errors import WeatherUnavailable
from app.integrations.weather_csv import CsvWeatherAdapter

DATA = Settings(_env_file=None).data_dir


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=IST)


@pytest.fixture(scope="module")
def weather() -> CsvWeatherAdapter:
    return CsvWeatherAdapter(DATA)


@pytest.fixture(scope="module")
def raw() -> dict[str, dict[datetime, tuple[float, float, float]]]:
    out: dict[str, dict[datetime, tuple[float, float, float]]] = {}
    with (DATA / "weather" / "weather_hourly_raw.csv").open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["station_id"], {})[at(r["time_ist"])] = (
                float(r["temperature_2m"]), float(r["relative_humidity_2m"]), float(r["precipitation"]))
    return out


def rain(raw, station: str, start: datetime, end: datetime) -> float:
    """Independent reimplementation: rain in [start, end) read straight from the CSV rows."""
    return round(sum(v[2] for t, v in raw[station].items() if start <= t < end), 1)


def test_current_values_and_windows_match_the_raw_rows(weather, raw):
    now = at("2026-05-12T16:00:00")
    snap = weather.snapshot("ST01", None, None, now)
    temp, rh, _ = raw["ST01"][now]
    assert (snap.station_id, snap.source, snap.stale) == ("ST01", "csv", False)
    assert snap.temp_c == temp and snap.rh_pct == rh
    assert snap.rain_last_24h_mm == rain(raw, "ST01", now - timedelta(hours=24), now)
    assert snap.rain_next_12h_mm == rain(raw, "ST01", now, now + timedelta(hours=12))
    assert snap.rain_next_48h_mm == rain(raw, "ST01", now, now + timedelta(hours=48))


def test_hourly_past_is_14_days_oldest_first_and_includes_now(weather, raw):
    now = at("2026-05-12T16:00:00")
    snap = weather.snapshot("ST01", None, None, now)
    assert len(snap.hourly_past) == 14 * 24
    times = [h.time for h in snap.hourly_past]
    assert times == sorted(times) and times[-1] == now and times[0] == now - timedelta(hours=14 * 24 - 1)
    for hour in (snap.hourly_past[0], snap.hourly_past[100], snap.hourly_past[-1]):
        t, rh, mm = raw["ST01"][hour.time]
        assert (hour.temp_c, hour.rh_pct, hour.rain_mm) == (t, rh, mm)


def test_hourly_future_is_the_next_48_hours_from_the_archive(weather, raw):
    now = at("2026-05-12T16:00:00")
    snap = weather.snapshot("ST01", None, None, now)
    assert len(snap.hourly_future) == 48
    assert snap.hourly_future[0].time == now + timedelta(hours=1) and snap.hourly_future[-1].time == now + timedelta(hours=48)
    assert snap.hourly_future[5].rain_mm == raw["ST01"][now + timedelta(hours=6)][2]
    assert not {h.time for h in snap.hourly_past} & {h.time for h in snap.hourly_future}


def test_leaf_wet_proxy(weather, raw):
    snap = weather.snapshot("ST05", None, None, at("2026-05-04T21:00:00"))
    hours = snap.hourly_past + snap.hourly_future
    assert any(h.leaf_wet for h in hours) and any(not h.leaf_wet for h in hours)
    for h in hours:
        assert h.leaf_wet == (h.rain_mm >= 0.1 or h.rh_pct >= 90)


def test_daily_forecast_covers_seven_days_with_min_max_and_rain_sums(weather, raw):
    now = at("2026-05-12T16:00:00")
    snap = weather.snapshot("ST01", None, None, now)
    assert [d.day.isoformat() for d in snap.daily_forecast] == [f"2026-05-{d}" for d in range(12, 19)]
    first = snap.daily_forecast[0]
    day_rows = [v for t, v in raw["ST01"].items() if t.date() == now.date()]
    assert first.tmin_c == min(v[0] for v in day_rows) and first.tmax_c == max(v[0] for v in day_rows)
    assert first.rain_mm == round(sum(v[2] for v in day_rows), 1)


def test_demo_scenario_weather_facts_are_reproduced(weather):
    scenarios = json.loads((DATA / "demo_scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    checked = 0
    for sc in scenarios:
        facts = sc["facts"].get("weather_at_clock", sc["facts"])
        if "rain_next_12h_mm" not in facts:
            continue
        snap = weather.snapshot(sc["station_id"], None, None, at(sc["demo_clock"].replace(" ", "T")))
        assert snap.rain_next_12h_mm == pytest.approx(facts["rain_next_12h_mm"], abs=0.05), sc["id"]
        assert snap.rain_next_48h_mm == pytest.approx(facts["rain_next_48h_mm"], abs=0.05), sc["id"]
        assert snap.rain_last_24h_mm == pytest.approx(facts["rain_prev_24h_mm"], abs=0.05), sc["id"]
        checked += 1
    assert checked >= 4


def test_s3_rain_after_the_spray_is_what_the_scenario_says(weather):
    s3 = next(s for s in json.loads((DATA / "demo_scenarios.json").read_text(encoding="utf-8"))["scenarios"] if s["id"] == "S3")
    spray_time = at(s3["facts"]["spray_datetime"].replace(" ", "T"))
    snap = weather.snapshot(s3["station_id"], None, None, spray_time)
    assert snap.rain_next_12h_mm == pytest.approx(s3["facts"]["rain_in_12h_after_spray_mm"], abs=0.05)
    assert snap.rain_next_12h_mm >= s3["facts"]["heavy_rain_threshold_mm_config"]


def test_naive_now_is_ist_and_minutes_are_floored(weather):
    exact = weather.snapshot("ST02", None, None, at("2026-06-01T10:00:00"))
    naive = weather.snapshot("ST02", None, None, datetime(2026, 6, 1, 10, 40))
    assert naive.temp_c == exact.temp_c and naive.rain_next_12h_mm == exact.rain_next_12h_mm
    assert naive.as_of.tzinfo is not None


def test_station_chosen_by_nearest_coordinates(weather):
    assert weather.snapshot(None, 31.12, 77.36, at("2026-05-12T08:00:00")).station_id == "ST01"       # Theog
    assert weather.snapshot(None, 31.45, 78.25, at("2026-05-12T08:00:00")).station_id == "ST08"       # near Sangla
    assert weather.snapshot("ST99", 32.24, 77.19, at("2026-05-12T08:00:00")).station_id == "ST07"     # unknown id falls back to coordinates


def test_unknown_station_without_coordinates_raises(weather):
    with pytest.raises(WeatherUnavailable):
        weather.snapshot("ST99", None, None, at("2026-05-12T08:00:00"))
    with pytest.raises(WeatherUnavailable):
        weather.snapshot(None, None, None, at("2026-05-12T08:00:00"))


def test_before_the_archive_raises_and_after_it_is_stale(weather):
    with pytest.raises(WeatherUnavailable):
        weather.snapshot("ST01", None, None, at("2026-01-01T00:00:00"))
    late = weather.snapshot("ST01", None, None, at("2026-10-19T08:00:00"))
    assert late.stale is True and late.hourly_future == [] and late.temp_c is not None


def test_start_of_archive_has_a_short_past(weather):
    snap = weather.snapshot("ST01", None, None, at("2026-02-16T00:00:00"))
    assert len(snap.hourly_past) == 25 and snap.hourly_past[0].time == at("2026-02-15T00:00:00")
