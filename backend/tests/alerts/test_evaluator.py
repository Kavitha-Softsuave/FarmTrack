import sys
import types
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.alerts.evaluator import STALE_NOTE, run_once
from app.api.schemas import SpokenOut
from app.clock import IST
from app.config import Settings
from app.db.models import AlertRow
from app.domain.types import LocalizedText, Severity
from app.integrations.iot_mock import MockIoTAdapter
from app.integrations.reference import load_product_master
from app.integrations.weather_csv import CsvWeatherAdapter
from tests.integrations.fakes import (
    NOW,
    FakeIoT,
    FakePush,
    FakeRules,
    FakeWeather,
    FakeZoho,
    all_alerts,
    device_row,
    farmer_row,
    make_container,
    risk,
    spray_log_row,
)

DATA = Settings(_env_file=None).data_dir
PRODUCTS = load_product_master(DATA)
HEAVY = next(p for p in PRODUCTS.values() if p.crop == "Apple" and (p.waiting_period_days or 0) == 30 and p.category == "fungicide")
LIGHT = PRODUCTS["P010"]                                  # waiting period 3 days


def seed(db, *rows):
    """Insert in the given order (no relationship() is declared, so the unit of work will not order FK parents first)."""
    for row in rows:
        db.add(row)
        db.flush()
    db.commit()


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=IST)


# ------------------------------------------------------------------------------------------------- creation and filtering
def test_creates_alerts_for_yellow_and_red_only_with_localised_texts(db, tmp_path):
    seed(db, farmer_row("F901"))
    rules = FakeRules([risk("scab_infection_risk", "yellow", episode="2026-05-04"), risk("late_blight_risk", "green"),
                       risk("marssonina_alternaria_risk", "red", episode="2026-05-10T14:00:00+05:30")])
    created = run_once(db, make_container(tmp_path, rules=rules))
    assert sorted((a.kind, a.level, a.dedupe_key) for a in created) == [
        ("marssonina_alternaria_risk", "red", "marssonina:ST05:2026-05-10:red"),
        ("scab_infection_risk", "yellow", "scab:ST05:2026-05-04"),
    ]
    scab = next(a for a in created if a.kind == "scab_infection_risk")
    assert scab.title == {"en": "scab_infection_risk title", "hi": "scab_infection_risk शीर्षक"}
    assert scab.body["en"] == "scab_infection_risk advice." and scab.body["hi"] == "scab_infection_risk सलाह।"
    assert scab.created_at == NOW and scab.read_at is None and scab.pushed_at is None
    assert scab.payload["risk_id"] == "scab_infection_risk" and scab.payload["station_id"] == "ST05"
    spoken = SpokenOut.model_validate(scab.spoken)
    assert spoken.text.en == "scab_infection_risk title. scab_infection_risk advice."
    assert spoken.text.hi.startswith("scab_infection_risk शीर्षक.")
    assert len(all_alerts(db)) == 2


def test_unknown_risk_ids_and_green_levels_make_no_alert(db, tmp_path):
    seed(db, farmer_row("F901"))
    rules = FakeRules([risk("rotation_limit", "red"), risk("stale_history", "yellow"), risk("rain_washoff", "green")])
    assert run_once(db, make_container(tmp_path, rules=rules)) == []


def test_title_and_body_fall_back_to_english_when_hindi_is_missing(db, tmp_path):
    seed(db, farmer_row("F901"))
    item = risk("scab_infection_risk")
    item.title, item.text = LocalizedText(en="Scab weather"), LocalizedText(en="Spray protectant.")
    created = run_once(db, make_container(tmp_path, rules=FakeRules([item])))
    assert created[0].title["hi"] == "Scab weather" and created[0].body["hi"] == "Spray protectant."


def test_farmers_without_a_station_are_skipped(db, tmp_path):
    seed(db, farmer_row("F901", station_id=None), farmer_row("F902"))
    rules = FakeRules([risk("scab_infection_risk")])
    created = run_once(db, make_container(tmp_path, rules=rules))
    assert [a.farmer_id for a in created] == ["F902"] and len(rules.calls) == 1


# ------------------------------------------------------------------------------------------------- idempotence and episodes
def test_second_run_creates_nothing(db, tmp_path):
    seed(db, farmer_row("F901"), farmer_row("F902"))
    container = make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk", episode="2026-05-04")]))
    assert len(run_once(db, container)) == 2
    assert run_once(db, container) == []
    assert run_once(db, container, now=NOW + timedelta(hours=5)) == []
    assert len(all_alerts(db)) == 2


def test_without_an_episode_date_an_episode_lasts_until_five_quiet_days_have_passed(db, tmp_path):
    seed(db, farmer_row("F901"))
    container = make_container(tmp_path, rules=FakeRules([risk("late_blight_risk", "red")]))
    first = run_once(db, container, now=at("2026-07-12T08:00"))
    assert [a.dedupe_key for a in first] == ["late_blight:ST05:2026-07-12:red"]
    for later in ("2026-07-12T20:00", "2026-07-13T08:00", "2026-07-16T07:00"):
        assert run_once(db, container, now=at(later)) == [], later
    again = run_once(db, container, now=at("2026-07-18T08:00"))
    assert [a.dedupe_key for a in again] == ["late_blight:ST05:2026-07-18:red"]


def test_without_an_episode_date_a_yellow_after_a_red_stays_quiet_but_red_after_yellow_alerts(db, tmp_path):
    seed(db, farmer_row("F901"))
    rules = FakeRules([risk("marssonina_alternaria_risk", "yellow")])
    container = make_container(tmp_path, rules=rules)
    assert len(run_once(db, container, now=at("2026-07-12T08:00"))) == 1
    rules.risks = [risk("marssonina_alternaria_risk", "red")]
    assert [a.dedupe_key for a in run_once(db, container, now=at("2026-07-13T08:00"))] == ["marssonina:ST05:2026-07-12:red"]
    rules.risks = [risk("marssonina_alternaria_risk", "yellow")]
    assert run_once(db, container, now=at("2026-07-14T08:00")) == []


def test_episodes_are_tracked_per_farmer_kind_and_station(db, tmp_path):
    seed(db, farmer_row("F901"), farmer_row("F902"))
    rules = FakeRules(lambda farmer, weather, now, history: [risk("late_blight_risk", "red")] if farmer.id == "F901" else [])
    container = make_container(tmp_path, rules=rules)
    assert len(run_once(db, container, now=at("2026-07-12T08:00"))) == 1
    rules.risks = [risk("late_blight_risk", "red")]
    nxt = run_once(db, container, now=at("2026-07-13T08:00"))
    assert [(a.farmer_id, a.dedupe_key) for a in nxt] == [("F902", "late_blight:ST05:2026-07-13:red")]
    rules.risks = [risk("scab_infection_risk", "red")]                       # another kind starts its own episode
    assert len(run_once(db, container, now=at("2026-07-13T09:00"))) == 2


def test_the_rules_engines_own_detail_keys_define_the_episode(db, tmp_path):
    seed(db, farmer_row("F901"))
    items = [risk("scab_infection_risk", "red", period_start="2026-05-04T11:00:00+05:30", period_end="2026-05-09T06:00:00+05:30"),
             risk("rain_washoff", "red", spray_at="2026-03-30T08:00:00+05:30", rain_mm=15.3)]
    created = run_once(db, make_container(tmp_path, rules=FakeRules(items)))
    assert sorted(a.dedupe_key for a in created) == ["scab:ST05:2026-05-04:red", "washoff:ST05:2026-03-30:red"]


def test_a_new_episode_gets_a_new_alert(db, tmp_path):
    seed(db, farmer_row("F901"))
    rules = FakeRules([risk("scab_infection_risk", episode="2026-05-04")])
    container = make_container(tmp_path, rules=rules)
    run_once(db, container)
    rules.risks = [risk("scab_infection_risk", episode="2026-05-20")]
    assert [a.dedupe_key for a in run_once(db, container)] == ["scab:ST05:2026-05-20"]


def test_escalation_to_red_alerts_again_but_yellow_after_red_does_not(db, tmp_path):
    seed(db, farmer_row("F901"))
    rules = FakeRules([risk("scab_infection_risk", "yellow", episode="2026-05-04")])
    container = make_container(tmp_path, rules=rules)
    assert len(run_once(db, container)) == 1
    rules.risks = [risk("scab_infection_risk", "red", episode="2026-05-04")]
    assert [a.level for a in run_once(db, container)] == ["red"]
    rules.risks = [risk("scab_infection_risk", "yellow", episode="2026-05-04")]
    assert run_once(db, container) == []
    assert sorted(a.level for a in all_alerts(db)) == ["red", "yellow"]


def test_same_risk_twice_in_one_pass_is_stored_once(db, tmp_path):
    seed(db, farmer_row("F901"))
    twice = [risk("scab_infection_risk", episode="2026-05-04")] * 2
    assert len(run_once(db, make_container(tmp_path, rules=FakeRules(twice)))) == 1


def test_naive_now_is_read_as_ist_and_overrides_the_container_clock(db, tmp_path):
    seed(db, farmer_row("F901"))
    container = make_container(tmp_path, rules=FakeRules([risk("late_blight_risk")]))
    created = run_once(db, container, now=datetime(2026, 7, 12, 8, 0))
    assert created[0].created_at == at("2026-07-12T08:00") and created[0].dedupe_key == "late_blight:ST05:2026-07-12"


def test_alerts_are_committed(db, tmp_path):
    from app.db.session import get_session_factory

    seed(db, farmer_row("F901"))
    run_once(db, make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk")])))
    with get_session_factory()() as other:
        assert other.scalar(select(AlertRow.id)) is not None


# ------------------------------------------------------------------------------------------------- scenarios
def test_s4_like_block_alert_reaches_every_farmer_at_the_station_only(db, tmp_path):
    seed(db, *(farmer_row(f"F90{i}", station_id="ST05") for i in range(1, 4)), farmer_row("F909", station_id="ST01"))

    def scab_for_the_jubbal_block(farmer, weather, now, history):
        return [risk("scab_infection_risk", "red", episode="2026-05-04")] if weather.station_id == "ST05" else []

    container = make_container(tmp_path, now=at("2026-05-04T21:00"), rules=FakeRules(scab_for_the_jubbal_block))
    created = run_once(db, container)
    assert sorted(a.farmer_id for a in created) == ["F901", "F902", "F903"]
    assert {a.dedupe_key for a in created} == {"scab:ST05:2026-05-04:red"}
    assert container.weather.calls.count("ST05") == 1                        # weather fetched once per station, not per farmer


def test_s3_like_washoff_alert_uses_the_app_spray_diary(db, tmp_path):
    seed(db, farmer_row("F907", station_id="ST02"), spray_log_row("F907", at("2026-03-30T08:00"), product_id="P007"))
    rules = FakeRules(lambda farmer, weather, now, history: [risk("rain_washoff", "red", episode="2026-03-30T08:00:00+05:30")]
                      if any(h.product_id == "P007" and h.source == "app" for h in history) else [])
    container = make_container(tmp_path, now=at("2026-03-30T20:00"), rules=rules)
    created = run_once(db, container)
    assert [(a.kind, a.level, a.dedupe_key) for a in created] == [("rain_washoff", "red", "washoff:ST02:2026-03-30:red")]
    sent_history = rules.calls[0]["history"]
    assert [h.product_id for h in sent_history] == ["P007"] and sent_history[0].active_ingredient == PRODUCTS["P007"].active_ingredient


def test_history_merges_zoho_and_app_without_double_counting(db, tmp_path):
    from app.domain.types import SprayRecord

    seed(db, farmer_row("F901"), spray_log_row("F901", at("2026-05-01T09:00"), product_id="P001"),
         spray_log_row("F901", at("2026-05-10T09:00"), product_id="P002"))
    zoho = FakeZoho({"F901": [SprayRecord(sprayed_at=at("2026-05-01T09:00"), product_id="P001", active_ingredient="Captan"),
                              SprayRecord(sprayed_at=at("2026-05-20T09:00"), product_id="P003")]})
    rules = FakeRules()
    run_once(db, make_container(tmp_path, rules=rules, zoho=zoho))
    history = rules.calls[0]["history"]
    assert [(h.product_id, h.source) for h in history] == [("P001", "zoho"), ("P002", "app")]       # P003 is after `now`


def test_zoho_outage_falls_back_to_the_app_diary(db, tmp_path):
    seed(db, farmer_row("F901"), spray_log_row("F901", at("2026-05-01T09:00"), product_id="P001"))
    rules = FakeRules([risk("scab_infection_risk")])
    created = run_once(db, make_container(tmp_path, rules=rules, zoho=FakeZoho(raises=True)))
    assert len(created) == 1 and [h.product_id for h in rules.calls[0]["history"]] == ["P001"]


# ------------------------------------------------------------------------------------------------- stale sensor
def test_stale_sensor_is_stated_in_the_alert(db, tmp_path):
    seed(db, farmer_row("F901", station_id="ST08"), farmer_row("F902", station_id="ST01"))

    def scab(farmer, weather, now, history):
        return [risk("scab_infection_risk", episode="2026-07-12")]

    container = make_container(tmp_path, rules=FakeRules(scab), iot=FakeIoT(stale_stations={"ST08"}))
    created = {a.farmer_id: a for a in run_once(db, container)}
    stale, fresh = created["F901"], created["F902"]
    assert stale.body["en"].endswith(STALE_NOTE.en) and stale.body["hi"].endswith(STALE_NOTE.hi)
    assert stale.payload["sensor_stale"] is True
    assert STALE_NOTE.en in SpokenOut.model_validate(stale.spoken).text.en
    assert STALE_NOTE.en not in fresh.body["en"] and fresh.payload["sensor_stale"] is False


def test_stale_weather_and_unknown_sensor_state_are_also_stated(db, tmp_path):
    seed(db, farmer_row("F901"))
    rules = FakeRules([risk("scab_infection_risk", episode="2026-05-01"), risk("late_blight_risk", episode="2026-05-01")])
    by_weather = run_once(db, make_container(tmp_path, rules=rules, weather=FakeWeather(stale=True)))
    assert all(STALE_NOTE.en in a.body["en"] for a in by_weather)
    db.query(AlertRow).delete()
    db.commit()
    unknown = run_once(db, make_container(tmp_path, rules=rules, iot=FakeIoT(raises=True)))
    assert all(a.payload["sensor_stale"] is True for a in unknown)


def test_s11_with_the_real_sensor_and_weather_archive(db, tmp_path):
    seed(db, farmer_row("F901", station_id="ST08"), farmer_row("F902", station_id="ST01"))
    rules = FakeRules(lambda farmer, weather, now, history: [risk("scab_infection_risk", episode="2026-07-12")])
    container = make_container(tmp_path, now=at("2026-07-12T09:00"), rules=rules, iot=MockIoTAdapter(DATA), weather=CsvWeatherAdapter(DATA))
    created = {a.farmer_id: a for a in run_once(db, container)}
    assert STALE_NOTE.en in created["F901"].body["en"]            # ST08 sensor offline since 10 Jul
    assert STALE_NOTE.en not in created["F902"].body["en"]
    weather_seen = {c["weather"].station_id: c["weather"] for c in rules.calls}
    assert weather_seen["ST08"].source == "csv" and len(weather_seen["ST08"].hourly_past) == 336


# ------------------------------------------------------------------------------------------------- failures are isolated
def test_one_failing_farmer_or_station_does_not_stop_the_others(db, tmp_path):
    seed(db, farmer_row("F901", station_id="ST05"), farmer_row("F902", station_id="ST02"), farmer_row("F903", station_id="ST05"))

    def flaky(farmer, weather, now, history):
        if farmer.id == "F903":
            raise RuntimeError("boom")
        return [risk("scab_infection_risk", episode="2026-05-04")]

    container = make_container(tmp_path, rules=FakeRules(flaky), weather=FakeWeather(fail_for={"ST02"}))
    created = run_once(db, container)
    assert [a.farmer_id for a in created] == ["F901"]
    assert run_once(db, container) == []                                    # still idempotent after the failures


# ------------------------------------------------------------------------------------------------- push
def test_push_goes_to_every_device_in_the_farmers_language(db, tmp_path):
    seed(db, farmer_row("F901", language="hi"), farmer_row("F902", language="en"),
         device_row("F901", "tok-hi-1"), device_row("F901", "tok-hi-2"), device_row("F902", "tok-en-1"))
    push = FakePush()
    created = run_once(db, make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk", episode="2026-05-04")]), push=push))
    by_token = {p["token"]: p for p in push.sent}
    assert set(by_token) == {"tok-hi-1", "tok-hi-2", "tok-en-1"}
    assert by_token["tok-hi-1"]["title"] == "scab_infection_risk शीर्षक" and by_token["tok-en-1"]["title"] == "scab_infection_risk title"
    assert by_token["tok-en-1"]["body"] == "scab_infection_risk advice."
    alert = next(a for a in created if a.farmer_id == "F902")
    assert by_token["tok-en-1"]["data"] == {"alert_id": alert.id, "kind": "scab_infection_risk", "level": "yellow"}
    assert all(a.pushed_at == NOW for a in created)
    fresh = {a.farmer_id: a.pushed_at for a in db.scalars(select(AlertRow))}
    assert fresh["F901"] is not None


def test_alerts_are_not_pushed_twice(db, tmp_path):
    seed(db, farmer_row("F901"), device_row("F901"))
    push = FakePush()
    container = make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk", episode="2026-05-04")]), push=push)
    run_once(db, container)
    run_once(db, container)
    assert len(push.sent) == 1


def test_failed_push_keeps_the_alert_unpushed(db, tmp_path):
    seed(db, farmer_row("F901"), device_row("F901"))
    for push in (FakePush(result=False), FakePush(raises=True)):
        db.query(AlertRow).delete()
        db.commit()
        created = run_once(db, make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk")]), push=push))
        assert len(created) == 1 and created[0].pushed_at is None
        assert db.scalar(select(AlertRow.pushed_at)) is None


def test_one_working_device_is_enough_to_mark_pushed(db, tmp_path):
    seed(db, farmer_row("F901"), device_row("F901", "tok-a"), device_row("F901", "tok-b"))

    class HalfBroken(FakePush):
        def send(self, token, title, body, data=None):
            if token == "tok-a":
                raise RuntimeError("expired token")
            return super().send(token, title, body, data)

    created = run_once(db, make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk")]), push=HalfBroken()))
    assert created[0].pushed_at == NOW


def test_no_devices_means_the_alert_stays_in_the_app_only(db, tmp_path):
    seed(db, farmer_row("F901"))
    push = FakePush()
    created = run_once(db, make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk")]), push=push))
    assert len(created) == 1 and created[0].pushed_at is None and push.sent == []


# ------------------------------------------------------------------------------------------------- spoken text
def test_spoken_uses_the_voice_service_when_it_is_available(db, tmp_path, monkeypatch):
    seen = {}

    def fake_spoken_out(store, en, hi):
        seen.update(store=store, en=en, hi=hi)
        return SpokenOut(text=LocalizedText(en=en, hi=hi), audio={"en": {"url": "/audio/x.mp3"}, "hi": None})

    module = types.ModuleType("app.voice.spoken")
    module.spoken_out = fake_spoken_out
    monkeypatch.setitem(sys.modules, "app.voice.spoken", module)
    seed(db, farmer_row("F901"))
    container = make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk")]))
    container.audio = object()
    created = run_once(db, container)
    assert seen["store"] is container.audio and seen["en"].startswith("scab_infection_risk title.")
    assert created[0].spoken["audio"]["en"]["url"] == "/audio/x.mp3"


def test_a_failing_voice_service_never_loses_the_alert(db, tmp_path, monkeypatch):
    def broken(store, en, hi):
        raise RuntimeError("tts down")

    module = types.ModuleType("app.voice.spoken")
    module.spoken_out = broken
    monkeypatch.setitem(sys.modules, "app.voice.spoken", module)
    seed(db, farmer_row("F901"))
    created = run_once(db, make_container(tmp_path, rules=FakeRules([risk("scab_infection_risk")])))
    assert len(created) == 1 and created[0].spoken["text"]["en"].startswith("scab_infection_risk title.")
    assert created[0].spoken.get("audio", {}) == {}


# ------------------------------------------------------------------------------------------------- waiting period
def waiting(db, tmp_path, now: str, sprayed: str, product=HEAVY, extra=(), **farmer_kw):
    seed(db, farmer_row("F901", **farmer_kw), spray_log_row("F901", at(sprayed), product_id=product.product_id), *extra)
    container = make_container(tmp_path, now=at(now), push=FakePush())
    return run_once(db, container), container


def test_waiting_period_alert_when_the_spray_is_too_close_to_harvest(db, tmp_path):
    # Royal Delicious, band B3: expected harvest day 252 = 9 Sep 2026
    created, _ = waiting(db, tmp_path, "2026-08-25T08:00", "2026-08-20T10:00")
    assert len(created) == 1
    alert = created[0]
    assert (alert.kind, alert.level) == ("waiting_period", "yellow")
    assert alert.dedupe_key == f"waiting:{HEAVY.product_id}:2026-08-20"
    assert alert.payload["safe_from"] == "2026-09-19" and alert.payload["expected_harvest"] == "2026-09-09"
    assert alert.payload["days_to_harvest"] == 15 and alert.payload["waiting_period_days"] == 30
    assert HEAVY.active_ingredient in alert.body["en"] and "20 Aug" in alert.body["en"] and "19 Sep" in alert.body["en"]
    assert "अगस्त" in alert.body["hi"] and "सितंबर" in alert.body["hi"]
    assert alert.title["en"] == "Wait before picking fruit"
    assert STALE_NOTE.en not in alert.body["en"]


def test_waiting_period_alert_turns_red_when_harvest_is_a_week_away(db, tmp_path):
    created, _ = waiting(db, tmp_path, "2026-09-05T08:00", "2026-09-01T10:00")
    assert [(a.kind, a.level) for a in created] == [("waiting_period", "red")]


@pytest.mark.parametrize("now,sprayed,product,farmer_kw", [
    ("2026-08-25T08:00", "2026-05-01T10:00", HEAVY, {}),                               # long enough before harvest
    ("2026-08-25T08:00", "2026-08-24T10:00", LIGHT, {}),                               # 3-day waiting period is fine
    ("2026-09-20T08:00", "2026-09-19T10:00", HEAVY, {}),                               # harvest date already passed
    ("2026-08-25T08:00", "2026-08-20T10:00", HEAVY, {"primary_crop": "Potato", "phenology_band": None}),     # no harvest calendar
    ("2026-08-25T08:00", "2026-08-20T10:00", HEAVY, {"phenology_band": None}),         # unknown band: cannot estimate harvest
])
def test_no_waiting_period_alert_when_it_does_not_apply(db, tmp_path, now, sprayed, product, farmer_kw):
    created, _ = waiting(db, tmp_path, now, sprayed, product, **farmer_kw)
    assert created == []


def test_waiting_period_uses_the_latest_safe_date_not_just_the_last_spray(db, tmp_path):
    seed(db, farmer_row("F901"), spray_log_row("F901", at("2026-08-20T10:00"), product_id=HEAVY.product_id),
         spray_log_row("F901", at("2026-08-24T10:00"), product_id=LIGHT.product_id))
    created = run_once(db, make_container(tmp_path, now=at("2026-08-25T08:00")))
    assert [a.payload["product_id"] for a in created] == [HEAVY.product_id]


def test_nutrient_and_zoho_history_count_for_waiting_period_correctly(db, tmp_path):
    from app.domain.types import SprayRecord

    seed(db, farmer_row("F901"), spray_log_row("F901", at("2026-08-24T10:00"), product_id=None, free_text="Zinc, Boron"))
    zoho = FakeZoho({"F901": [SprayRecord(sprayed_at=at("2026-08-20T10:00"), product_id=HEAVY.product_id)]})
    created = run_once(db, make_container(tmp_path, now=at("2026-08-25T08:00"), zoho=zoho))
    assert [a.kind for a in created] == ["waiting_period"]


def test_waiting_period_alert_is_raised_once_per_spray(db, tmp_path):
    created, container = waiting(db, tmp_path, "2026-08-25T08:00", "2026-08-20T10:00")
    assert len(created) == 1
    assert run_once(db, container) == []
    assert run_once(db, container, now=at("2026-08-26T08:00")) == []


def test_waiting_period_alert_is_pushed(db, tmp_path):
    created, container = waiting(db, tmp_path, "2026-08-25T08:00", "2026-08-20T10:00", extra=(device_row("F901"),))
    assert len(container.push.sent) == 1 and container.push.sent[0]["data"]["kind"] == "waiting_period"
    assert created[0].level == Severity.yellow.value
