import csv
from datetime import datetime, timedelta

import pytest

from app.clock import IST
from app.config import Settings
from app.integrations.iot_mock import MockIoTAdapter

DATA = Settings(_env_file=None).data_dir


@pytest.fixture(scope="module")
def iot() -> MockIoTAdapter:
    return MockIoTAdapter(DATA)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=IST)


def raw_rows(station: str) -> list[dict]:
    with (DATA / "iot" / "sensor_readings.csv").open(encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if r["station_id"] == station]


def test_latest_matches_the_raw_row_at_or_before_now(iot):
    rows = raw_rows("ST01")
    row = next(r for r in rows if r["timestamp_ist"] == "2026-05-12 08:00:00")
    reading = iot.latest("ST01", at("2026-05-12T08:00:00"))
    assert reading.time == at("2026-05-12T08:00:00")
    assert reading.temp_c == pytest.approx(float(row["temp_c"]))
    assert reading.rh_pct == pytest.approx(float(row["rh_pct"]))
    assert reading.rain_mm == pytest.approx(float(row["rain_mm"]))
    assert reading.leaf_wetness_min == int(row["leaf_wetness_min"])
    assert reading.soil_moisture_pct == pytest.approx(float(row["soil_moisture_pct"]))
    assert reading.battery_v == pytest.approx(float(row["battery_v"]))


def test_latest_never_returns_a_reading_after_now(iot):
    now = at("2026-05-12T08:30:00")
    reading = iot.latest("ST01", now)
    assert reading.time == at("2026-05-12T08:00:00")
    assert reading.time <= now


def test_latest_for_a_naive_now_means_ist(iot):
    assert iot.latest("ST01", datetime(2026, 5, 12, 8, 0)).time == at("2026-05-12T08:00:00")


def test_latest_before_the_data_and_for_unknown_station_is_none(iot):
    assert iot.latest("ST01", at("2026-01-01T00:00:00")) is None
    assert iot.latest("ST99", at("2026-05-12T08:00:00")) is None


def test_after_the_data_ends_the_last_reading_is_returned_and_is_stale(iot):
    late = at("2026-10-25T08:00:00")
    reading = iot.latest("ST01", late)
    assert reading is not None and reading.time <= at("2026-10-17T23:00:00")
    assert iot.is_stale("ST01", late) is True


def test_st08_is_stale_during_the_scripted_outage(iot):
    last_before = iot.latest("ST08", at("2026-07-12T09:00:00"))
    assert last_before.time == at("2026-07-10T05:00:00")                  # nothing between 10 Jul 06:00 and 14 Jul 18:00
    for now in ("2026-07-12T09:00:00", "2026-07-13T09:00:00", "2026-07-14T09:00:00"):
        assert iot.is_stale("ST08", at(now)) is True, now
    assert iot.latest("ST08", at("2026-07-14T09:00:00")).time == at("2026-07-10T05:00:00")


def test_st08_recovers_after_the_outage_and_is_fresh_before_it_goes_stale(iot):
    assert iot.is_stale("ST08", at("2026-07-10T09:00:00")) is False        # only 4 h old: the 48 h rule has not tripped yet
    assert iot.is_stale("ST08", at("2026-07-12T05:00:00")) is False        # exactly 48 h
    assert iot.is_stale("ST08", at("2026-07-12T05:01:00")) is True
    assert iot.is_stale("ST08", at("2026-07-15T09:00:00")) is False


def test_stale_threshold_is_configurable(iot):
    assert iot.is_stale("ST08", at("2026-07-10T09:00:00"), max_age_hours=2) is True
    assert iot.is_stale("ST08", at("2026-07-12T09:00:00"), max_age_hours=100) is False


def test_healthy_station_is_not_stale_and_unknown_station_is(iot):
    assert iot.is_stale("ST01", at("2026-07-12T09:00:00")) is False
    assert iot.is_stale("ST99", at("2026-07-12T09:00:00")) is True


def test_random_gap_shorter_than_the_limit_is_not_stale(iot):
    # ST02 has a 22 h random outage starting 2026-07-29 10:00
    assert iot.is_stale("ST02", at("2026-07-30T07:00:00")) is False
    gap_age = at("2026-07-30T07:00:00") - iot.latest("ST02", at("2026-07-30T07:00:00")).time
    assert gap_age > timedelta(hours=10)
