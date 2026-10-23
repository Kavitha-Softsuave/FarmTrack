from datetime import datetime, timedelta

import httpx
import pytest

from app.clock import IST
from app.config import Settings
from app.integrations.errors import WeatherUnavailable
from app.integrations.weather_openmeteo import CUSTOMER_URL, FREE_URL, OpenMeteoAdapter

DATA = Settings(_env_file=None).data_dir
NOW = datetime(2026, 10, 19, 8, 0, tzinfo=IST)
START = datetime(2026, 10, 5, 0, 0)          # past_days=14 -> 5 Oct 00:00 local


def payload(rain_at: dict[int, float] | None = None, temp_none_at: int | None = None) -> dict:
    stamps = [(START + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(21 * 24)]
    rain_at = rain_at or {}
    return {"hourly": {
        "time": stamps,
        "temperature_2m": [None if i == temp_none_at else 10.0 + (i % 24) / 2 for i in range(len(stamps))],
        "relative_humidity_2m": [60.0 + (i % 40) for i in range(len(stamps))],
        "precipitation": [rain_at.get(i, 0.0) for i in range(len(stamps))],
    }}


def hour_index(when: datetime) -> int:
    return int((when.replace(tzinfo=None) - START).total_seconds() // 3600)


class Recorder:
    def __init__(self, body=None, status=200):
        self.requests: list[httpx.Request] = []
        self.body = payload() if body is None else body
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)


def adapter(recorder, **kwargs) -> OpenMeteoAdapter:
    return OpenMeteoAdapter(DATA, client=httpx.Client(transport=httpx.MockTransport(recorder)), **kwargs)


def test_request_shape_and_free_endpoint(monkeypatch):
    monkeypatch.delenv("OPEN_METEO_API_KEY", raising=False)
    rec = Recorder()
    adapter(rec).snapshot(None, 31.12, 77.36, NOW)
    req = rec.requests[0]
    assert str(req.url).startswith(FREE_URL)
    params = dict(req.url.params)
    assert params["hourly"] == "temperature_2m,relative_humidity_2m,precipitation"
    assert (params["past_days"], params["forecast_days"], params["timezone"]) == ("14", "7", "Asia/Kolkata")
    assert params["latitude"] == "31.12" and params["longitude"] == "77.36" and "apikey" not in params


def test_api_key_switches_to_the_commercial_endpoint(monkeypatch):
    monkeypatch.setenv("OPEN_METEO_API_KEY", "k-test")
    rec = Recorder()
    adapter(rec).snapshot(None, 31.12, 77.36, NOW)
    assert str(rec.requests[0].url).startswith(CUSTOMER_URL)
    assert rec.requests[0].url.params["apikey"] == "k-test"


def test_mapping_to_weather_snapshot(monkeypatch):
    monkeypatch.delenv("OPEN_METEO_API_KEY", raising=False)
    now_i = hour_index(NOW)
    body = payload(rain_at={now_i - 3: 2.5, now_i - 30: 9.0, now_i + 4: 1.2, now_i + 20: 0.8, now_i + 40: 3.0})
    snap = adapter(Recorder(body)).snapshot("ST01", 31.12, 77.36, NOW)
    assert (snap.source, snap.station_id, snap.stale) == ("openmeteo", "ST01", False)
    assert snap.temp_c == body["hourly"]["temperature_2m"][now_i] and snap.rh_pct == body["hourly"]["relative_humidity_2m"][now_i]
    assert snap.rain_last_24h_mm == 2.5                       # the 9 mm fell 30 h ago
    assert snap.rain_next_12h_mm == 1.2
    assert snap.rain_next_48h_mm == pytest.approx(1.2 + 0.8 + 3.0)
    assert len(snap.hourly_past) == 14 * 24                   # last 14 days, oldest first
    assert snap.hourly_past[-1].time == NOW and snap.hourly_past[0].time == NOW - timedelta(hours=14 * 24 - 1)
    assert len(snap.hourly_future) == 48 and snap.hourly_future[0].time == NOW + timedelta(hours=1)
    assert [d.day.isoformat() for d in snap.daily_forecast] == [f"2026-10-{d}" for d in range(19, 26)]
    wet = next(h for h in snap.hourly_past if h.time == NOW - timedelta(hours=3))
    assert wet.rain_mm == 2.5 and wet.leaf_wet is True


def test_gap_hours_with_null_temperature_are_skipped(monkeypatch):
    monkeypatch.delenv("OPEN_METEO_API_KEY", raising=False)
    gap = hour_index(NOW) - 5
    snap = adapter(Recorder(payload(temp_none_at=gap))).snapshot(None, 31.12, 77.36, NOW)
    times = {h.time for h in snap.hourly_past}
    assert NOW - timedelta(hours=5) not in times and NOW - timedelta(hours=4) in times


def test_responses_are_cached_for_30_minutes():
    clock = [1000.0]
    rec = Recorder()
    om = adapter(rec, monotonic=lambda: clock[0])
    om.snapshot(None, 31.12, 77.36, NOW)
    clock[0] += 29 * 60
    om.snapshot(None, 31.12, 77.36, NOW)
    assert len(rec.requests) == 1
    om.snapshot(None, 32.24, 77.19, NOW)                   # another place is a separate cache entry
    assert len(rec.requests) == 2
    clock[0] += 2 * 60
    om.snapshot(None, 31.12, 77.36, NOW)
    assert len(rec.requests) == 3


def test_station_id_is_resolved_to_coordinates():
    rec = Recorder()
    adapter(rec).snapshot("ST08", None, None, NOW)
    assert rec.requests[0].url.params["latitude"] == "31.458698"


def test_no_place_raises():
    with pytest.raises(WeatherUnavailable):
        adapter(Recorder()).snapshot("ST99", None, None, NOW)
    with pytest.raises(WeatherUnavailable):
        adapter(Recorder()).snapshot(None, None, None, NOW)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_errors_become_weather_unavailable(status):
    with pytest.raises(WeatherUnavailable, match=str(status)):
        adapter(Recorder(status=status)).snapshot(None, 31.12, 77.36, NOW)


@pytest.mark.parametrize("body", [{}, {"hourly": {}}, {"hourly": {"time": ["x"], "temperature_2m": [1], "relative_humidity_2m": [1],
                                                                       "precipitation": [0]}},
                                  {"hourly": {"time": ["2026-10-19T00:00"], "temperature_2m": [], "relative_humidity_2m": [],
                                              "precipitation": []}}])
def test_malformed_payloads_become_weather_unavailable(body):
    with pytest.raises(WeatherUnavailable):
        adapter(Recorder(body)).snapshot(None, 31.12, 77.36, NOW)


def test_network_failure_becomes_weather_unavailable():
    def boom(request):
        raise httpx.ConnectTimeout("slow", request=request)

    om = OpenMeteoAdapter(DATA, client=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(WeatherUnavailable, match="ConnectTimeout"):
        om.snapshot(None, 31.12, 77.36, NOW)


def test_failures_are_not_cached():
    rec = Recorder(status=500)
    om = adapter(rec)
    for _ in range(2):
        with pytest.raises(WeatherUnavailable):
            om.snapshot(None, 31.12, 77.36, NOW)
    assert len(rec.requests) == 2
