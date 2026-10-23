from datetime import timedelta

import pytest

from app.db.models import AlertRow
from app.db.session import session_scope
from app.domain.types import ForecastDay, RiskItem, Severity
from tests.fakes import NOW, lt


def risk(level: Severity, rid: str = "scab_infection_risk") -> RiskItem:
    return RiskItem(id=rid, level=level, title=lt(f"{rid} title"), text=lt(f"{rid} {level.value} text"))


# ------------------------------------------------------------------------------------------------ /v1/field
def test_field_returns_readings_forecast_risks_and_speech(api_client, auth, fake_container):
    fake_container.weather.snapshot_value.daily_forecast = [
        ForecastDay(day=(NOW + timedelta(days=i)).date(), tmin_c=5.0 + i, tmax_c=15.0 + i, rain_mm=float(i)) for i in range(9)]
    fake_container.weather.snapshot_value.rain_last_24h_mm = 3.5
    fake_container.rules.risks = [risk(Severity.green, "rain_washoff"), risk(Severity.red)]
    response = api_client.get("/v1/field", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["station_id"] == "ST01" and body["village"] == "Theog" and body["stale"] is False
    assert body["as_of"] == "2026-05-12T07:00:00+05:30"                          # the sensor reading time
    assert body["readings"] == {"temp_c": 14.0, "rh_pct": 80.0, "rain_24h_mm": 3.5, "leaf_wetness_min": 10, "soil_moisture_pct": 40.0}
    assert len(body["forecast"]) == 7 and body["forecast"][0] == {"day": "2026-05-12", "tmin_c": 5.0, "tmax_c": 15.0, "rain_mm": 0.0}
    assert [r["id"] for r in body["risks"]] == ["rain_washoff", "scab_infection_risk"]
    spoken = body["spoken"]["text"]
    assert "cool" in spoken["en"] and "No rain is expected" in spoken["en"]
    assert "scab_infection_risk red text" in spoken["en"] and "rain_washoff green text" not in spoken["en"]   # only notable risks
    assert body["spoken"]["audio"]["hi"]["url"].startswith("/audio/")


def test_field_passes_the_demo_clock_station_and_history_to_the_providers(api_client, auth, fake_container):
    api_client.get("/v1/field", headers=auth)
    assert fake_container.weather.calls[0][0] == "ST01" and fake_container.weather.calls[0][3] == NOW
    assert fake_container.zoho.history_calls == [NOW]


def test_stale_sensor_sets_the_flag_and_speaks_the_warning(api_client, auth, fake_container):
    fake_container.iot.stale = True
    fake_container.iot.reading = fake_container.iot.reading.model_copy(update={"time": NOW - timedelta(days=4)})
    body = api_client.get("/v1/field", headers=auth).json()
    assert body["stale"] is True and body["as_of"] == "2026-05-08T08:00:00+05:30"
    assert body["spoken"]["text"]["en"].startswith("This information is old.")


def test_stale_weather_also_sets_the_flag(api_client, auth, fake_container):
    fake_container.weather.snapshot_value.stale = True
    assert api_client.get("/v1/field", headers=auth).json()["stale"] is True


def test_no_sensor_reading_falls_back_to_the_weather_snapshot(api_client, auth, fake_container):
    fake_container.iot.reading = None
    body = api_client.get("/v1/field", headers=auth).json()
    assert body["readings"] == {"temp_c": 14.0, "rh_pct": 80.0, "rain_24h_mm": 0.5, "leaf_wetness_min": None,
                                "soil_moisture_pct": None}
    assert body["as_of"] == "2026-05-12T08:00:00+05:30"


def test_everything_unavailable_is_stale_with_a_no_data_message(api_client, auth, fake_container):
    fake_container.iot.raises = RuntimeError("sensor api down")
    fake_container.weather.raises = RuntimeError("weather api down")
    response = api_client.get("/v1/field", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is True and body["readings"] is None and body["forecast"] == [] and body["risks"] == []
    assert body["spoken"]["text"]["en"] == "This information is old. There is no information yet."


def test_a_risk_engine_failure_only_removes_the_risks(api_client, auth, fake_container):
    def boom(*_a):
        raise RuntimeError("rules down")

    fake_container.rules.evaluate_risks = boom
    body = api_client.get("/v1/field", headers=auth).json()
    assert body["risks"] == [] and body["readings"] is not None


@pytest.mark.parametrize("rain,phrase", [(0.2, "No rain is expected"), (4.0, "light rain"), (25.0, "Heavy rain")])
def test_rain_wording(api_client, auth, fake_container, rain, phrase):
    fake_container.weather.snapshot_value.rain_next_48h_mm = rain
    assert phrase in api_client.get("/v1/field", headers=auth).json()["spoken"]["text"]["en"]


def test_field_without_a_station_still_works_from_the_weather(api_client, auth):
    with session_scope() as db:
        from app.db.models import FarmerRow

        db.get(FarmerRow, "F001").station_id = None
        db.commit()
    body = api_client.get("/v1/field", headers=auth).json()
    assert body["station_id"] is None and body["readings"]["temp_c"] == 14.0


# ------------------------------------------------------------------------------------------------ /v1/alerts
def add_alert(farmer_id="F001", key="k1", hours=0, read=False, kind="scab_infection_risk", spoken=None):
    with session_scope() as db:
        alert = AlertRow(farmer_id=farmer_id, kind=kind, level="red", dedupe_key=key, title={"en": f"T {key}", "hi": f"शी {key}"},
                         body={"en": f"B {key}", "hi": f"बॉ {key}"}, spoken=spoken or {}, payload={},
                         created_at=NOW - timedelta(hours=hours), read_at=NOW if read else None)
        db.add(alert)
        db.flush()
        return alert.id


def test_alerts_list_newest_first_with_unread_count(api_client, auth):
    old, new, read = add_alert(key="old", hours=5), add_alert(key="new", hours=1), add_alert(key="read", hours=3, read=True)
    body = api_client.get("/v1/alerts", headers=auth).json()
    assert [a["id"] for a in body["items"]] == [new, read, old] and body["unread"] == 2
    first = body["items"][0]
    assert first["kind"] == "scab_infection_risk" and first["level"] == "red" and first["read_at"] is None
    assert first["title"] == {"en": "T new", "hi": "शी new"} and first["created_at"] == "2026-05-12T07:00:00+05:30"
    assert body["items"][1]["read_at"] is not None


def test_alert_spoken_defaults_to_the_body_text_without_audio(api_client, auth):
    add_alert()
    spoken = api_client.get("/v1/alerts", headers=auth).json()["items"][0]["spoken"]
    assert spoken == {"text": {"en": "B k1", "hi": "बॉ k1"}, "audio": {}}


def test_alert_spoken_from_the_scheduler_is_passed_through(api_client, auth):
    stored = {"text": {"en": "Spoken", "hi": "बोला"}, "audio": {"en": {"url": "/audio/" + "a" * 64 + ".mp3", "sha256": "a" * 64}, "hi": None}}
    add_alert(spoken=stored)
    spoken = api_client.get("/v1/alerts", headers=auth).json()["items"][0]["spoken"]
    assert spoken["audio"]["en"]["url"].endswith(".mp3") and spoken["audio"]["hi"] is None


def test_alerts_limit(api_client, auth):
    for i in range(5):
        add_alert(key=f"a{i}", hours=i)
    body = api_client.get("/v1/alerts?limit=2", headers=auth).json()
    assert len(body["items"]) == 2 and body["unread"] == 5


def test_alerts_are_private(api_client, auth, login):
    add_alert(farmer_id="F002", key="theirs")
    assert api_client.get("/v1/alerts", headers=auth).json() == {"items": [], "unread": 0}
    assert api_client.get("/v1/alerts", headers=login("+910000000002")).json()["unread"] == 1


def test_mark_read_sets_the_time_once(api_client, auth, fake_container):
    alert_id = add_alert()
    first = api_client.post(f"/v1/alerts/{alert_id}/read", headers=auth)
    assert first.status_code == 200 and first.json()["read_at"] == "2026-05-12T08:00:00+05:30"
    fake_container.clock.set(NOW + timedelta(hours=2))
    again = api_client.post(f"/v1/alerts/{alert_id}/read", headers=auth).json()
    assert again["read_at"] == "2026-05-12T08:00:00+05:30"                       # idempotent: the first read time stays
    assert api_client.get("/v1/alerts", headers=auth).json()["unread"] == 0


def test_mark_read_ownership_is_404_not_403(api_client, auth, login):
    alert_id = add_alert(farmer_id="F002")
    response = api_client.post(f"/v1/alerts/{alert_id}/read", headers=auth)
    assert response.status_code == 404 and response.json()["code"] == "alert_not_found"
    assert api_client.post("/v1/alerts/" + "0" * 32 + "/read", headers=auth).status_code == 404
    with session_scope() as db:
        assert db.get(AlertRow, alert_id).read_at is None                          # untouched
