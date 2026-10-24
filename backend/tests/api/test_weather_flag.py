"""WEATHER_ENABLED: on (default) keeps today's behaviour; off means no weather lookup, risk, alert, card or sentence anywhere."""
import pytest

from app.config import Settings
from app.domain.types import ForecastDay, RiskItem, Severity
from app.integrations.errors import WeatherUnavailable
from app.integrations.factory import DisabledWeatherAdapter, build_weather
from tests.fakes import NOW, lt
from tests.imaging import photo_files
from tests.rules.helpers import dry_weather, make_engine, rule_input


def test_default_is_off(monkeypatch):
    monkeypatch.delenv("WEATHER_ENABLED")
    assert Settings(_env_file=None).weather_enabled is False


def test_env_variable_turns_it_on(monkeypatch):
    monkeypatch.setenv("WEATHER_ENABLED", "true")
    assert Settings(_env_file=None).weather_enabled is True


def test_factory_builds_a_disabled_adapter_that_never_looks_anything_up():
    adapter = build_weather(Settings(_env_file=None, weather_enabled=False, weather_provider="openmeteo"))
    assert isinstance(adapter, DisabledWeatherAdapter)
    with pytest.raises(WeatherUnavailable):
        adapter.snapshot("ST01", 31.0, 77.0, NOW)


# ------------------------------------------------------------------------------------------------ /v1/meta
def test_meta_reports_the_flag(api_client, fake_container):
    assert api_client.get("/v1/meta").json()["weather_enabled"] is True
    fake_container.settings.weather_enabled = False
    assert api_client.get("/v1/meta").json()["weather_enabled"] is False


# ------------------------------------------------------------------------------------------------ /v1/field
def test_field_off_has_no_forecast_risks_or_weather_words(api_client, auth, fake_container):
    fake_container.settings.weather_enabled = False
    fake_container.weather.snapshot_value.daily_forecast = [ForecastDay(day=NOW.date(), tmin_c=1.0, tmax_c=9.0, rain_mm=1.0)]
    fake_container.rules.risks = [risk_item()]
    body = api_client.get("/v1/field", headers=auth).json()
    assert fake_container.weather.calls == []                                   # no lookup at all
    assert body["forecast"] == [] and body["risks"] == [] and body["stale"] is False
    assert body["readings"]["temp_c"] == 14.0                                   # the field sensor is not weather
    spoken = body["spoken"]["text"]["en"]
    assert "rain" not in spoken.lower() and "weather" not in spoken.lower()


def test_field_on_still_calls_the_weather(api_client, auth, fake_container):
    api_client.get("/v1/field", headers=auth)
    assert fake_container.weather.calls


def risk_item():
    return RiskItem(id="scab_infection_risk", level=Severity.red, title=lt("t"), text=lt("scab red text"))


# ------------------------------------------------------------------------------------------------ scans
def test_scan_off_runs_the_rules_without_weather(api_client, auth, fake_container):
    fake_container.settings.weather_enabled = False
    response = api_client.post("/v1/scans", files=photo_files(1), data={}, headers=auth)
    assert response.status_code == 200
    assert fake_container.weather.calls == []
    rule_in = fake_container.rules.inputs[0]
    assert rule_in.weather is None and rule_in.weather_enabled is False


def test_scan_on_passes_the_weather(api_client, auth, fake_container):
    api_client.post("/v1/scans", files=photo_files(1), data={}, headers=auth)
    rule_in = fake_container.rules.inputs[0]
    assert rule_in.weather is not None and rule_in.weather_enabled is True


# ------------------------------------------------------------------------------------------------ rules
def test_rules_off_give_silent_timing_and_no_risks():
    engine = make_engine()
    off = rule_input(weather=dry_weather("2026-04-25 10:00"))
    off.weather_enabled = False
    out = engine.recommend(off)
    assert out.status == "advice" and out.products
    assert out.timing.action == "unknown" and out.timing.reasons == ["weather_disabled"]
    assert out.timing.text.en == "" and out.timing.text.hi == ""
    assert out.risks == [] and out.timing.rain_next_12h_mm is None


def test_rules_on_unchanged():
    out = make_engine().recommend(rule_input(weather=dry_weather("2026-04-25 10:00")))
    assert out.timing.action == "spray_now"
