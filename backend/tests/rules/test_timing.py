"""Spray timing: repeat after heavy rain (HP 2026), wait for rain, spray now, unknown without weather."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.rules.timing import rainfast_hours

from .helpers import (
    at,
    dry_weather,
    hourly,
    make_engine,
    nutrient,
    rule_input,
    series,
    snapshot,
    spray,
    weather_hour,
)

NOW = "2026-04-25 10:00"


def run(weather, history=None):
    return make_engine().recommend(rule_input(now=NOW, weather=weather, history=history or []))


def weather_with_rain(rain_at: dict[str, float], *, rain_next_12h: float | None = None):
    """Dry 14 days with the given rain amounts (mm) at the given times; hours after NOW go to the forecast."""
    now = at(NOW)
    extra = {at(k): v for k, v in rain_at.items()}
    past = series(now, 24 * 14, lambda t: (12.0, 60.0, extra.get(t, 0.0)))
    future = [weather_hour(now + timedelta(hours=h), rain=extra.get(now + timedelta(hours=h), 0.0)) for h in range(1, 49)]
    return snapshot(now, past, future, rain_next_12h_mm=rain_next_12h)


def test_no_weather_means_unknown():
    out = run(None)
    assert out.timing.action == "unknown" and out.timing.reasons == ["no_weather_data"]
    assert out.timing.text.en and out.timing.text.hi


def test_dry_next_12_hours_means_spray_now():
    t = run(dry_weather(NOW)).timing
    assert (t.action, t.reasons, t.rain_next_12h_mm) == ("spray_now", ["dry_next_12h"], 0.0)
    assert t.text.en.startswith("No rain") and t.text.hi


@pytest.mark.parametrize(("rain", "action"), [(1.9, "spray_now"), (2.0, "wait"), (7.5, "wait")])
def test_rain_threshold_for_waiting_is_2_mm(rain, action):
    t = run(snapshot(at(NOW), hourly(at(NOW), 24 * 14), [], rain_next_12h_mm=rain)).timing
    assert t.action == action and t.rain_next_12h_mm == rain
    if action == "wait":
        assert "rain_expected_next_12h" in t.reasons and str(rain).rstrip("0").rstrip(".") in t.text.en


def test_wait_text_names_the_dry_hours_the_top_product_needs():
    contact = run(snapshot(at(NOW), hourly(at(NOW), 24 * 14), [], rain_next_12h_mm=5.0))
    assert contact.products[0].behaviour == "contact" and "for 8 hours" in contact.timing.text.en
    systemic = run(snapshot(at(NOW), hourly(at(NOW), 24 * 14), [], rain_next_12h_mm=5.0), history=[spray("2026-04-12 10:00", "P022")])
    assert systemic.products[0].behaviour != "contact"


def test_rainfast_hours_come_from_the_config(ref):
    assert rainfast_hours(ref, ref.products_by_id["P022"]) == 8          # contact
    assert rainfast_hours(ref, ref.products_by_id["P014"]) == 4          # mixed
    assert rainfast_hours(ref, ref.products_by_id["P012"]) == 2          # systemic
    assert rainfast_hours(ref, ref.products_by_id["P052"]) == 8          # behaviour not_applicable: the longest period
    assert rainfast_hours(ref, None) == 8


# ---------------------------------------------------------------------------------------------------------- repeat after heavy rain
SPRAY_AT = "2026-04-24 18:00"


def test_heavy_rain_within_12_hours_after_a_spray_means_repeat_within_7_days():
    weather = weather_with_rain({"2026-04-24 22:00": 12.0})
    out = run(weather, [spray(SPRAY_AT, "P022")])
    t = out.timing
    assert (t.action, t.repeat_within_days, t.reasons) == ("repeat_within_days", 7, ["heavy_rain_after_last_spray"])
    assert "7 days" in t.text.en and "Do not use the same medicine" in t.text.en
    assert "P022" not in {p.product_id for p in out.products}              # never repeat the same chemical


@pytest.mark.parametrize(("rain", "repeat"), [(9.9, False), (10.0, True)])
def test_heavy_rain_threshold_is_10_mm(rain, repeat):
    out = run(weather_with_rain({"2026-04-24 22:00": rain}), [spray(SPRAY_AT, "P022")])
    assert (out.timing.action == "repeat_within_days") is repeat


def test_rain_is_summed_over_the_window():
    out = run(weather_with_rain({"2026-04-24 20:00": 4.0, "2026-04-24 23:00": 4.0, "2026-04-25 02:00": 3.0}), [spray(SPRAY_AT, "P022")])
    assert out.timing.action == "repeat_within_days"


def test_rain_after_the_12_hour_window_does_not_count():
    out = run(weather_with_rain({"2026-04-25 07:00": 20.0}), [spray(SPRAY_AT, "P022")])        # 13 hours after the spray
    assert out.timing.action == "spray_now"


def test_rain_before_the_spray_does_not_count():
    out = run(weather_with_rain({"2026-04-24 12:00": 20.0}), [spray(SPRAY_AT, "P022")])
    assert out.timing.action == "spray_now"


def test_a_spray_older_than_7_days_is_not_repeated():
    old = "2026-04-17 08:00"
    assert run(weather_with_rain({"2026-04-17 10:00": 20.0}), [spray(old, "P022")]).timing.action == "spray_now"
    recent = "2026-04-18 11:00"
    assert run(weather_with_rain({"2026-04-18 12:00": 20.0}), [spray(recent, "P022")]).timing.action == "repeat_within_days"


def test_only_a_fungicide_spray_triggers_the_repeat_rule():
    rain = weather_with_rain({"2026-04-24 22:00": 30.0})
    assert run(rain, [spray(SPRAY_AT, "P052")]).timing.action == "spray_now"              # insecticide
    assert run(rain, [nutrient(SPRAY_AT)]).timing.action == "spray_now"
    assert run(rain, []).timing.action == "spray_now"


def test_the_most_recent_fungicide_spray_is_the_one_checked():
    rain = weather_with_rain({"2026-04-24 02:00": 30.0})                                  # after the first spray, before the second
    history = [spray("2026-04-23 22:00", "P009"), spray(SPRAY_AT, "P022")]
    assert run(rain, history).timing.action == "spray_now"


def test_forecast_rain_alone_does_not_trigger_the_repeat_rule():
    now = at(NOW)
    spray_time = "2026-04-25 08:00"
    forecast_rain = weather_with_rain({"2026-04-25 14:00": 15.0})
    out = run(forecast_rain, [spray(spray_time, "P022")])
    assert out.timing.action in ("wait", "spray_now") and out.timing.action != "repeat_within_days"
    washoff = next(r for r in out.risks if r.id == "rain_washoff")
    assert washoff.level.value == "yellow" and now


def test_repeat_and_wait_when_more_rain_is_coming():
    weather = weather_with_rain({"2026-04-24 22:00": 12.0, "2026-04-25 14:00": 6.0})
    t = run(weather, [spray(SPRAY_AT, "P022")]).timing
    assert t.action == "repeat_within_days" and t.reasons == ["heavy_rain_after_last_spray", "rain_expected_next_12h"]
    assert "wait until the leaves are dry" in t.text.en
