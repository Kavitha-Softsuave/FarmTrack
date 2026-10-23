"""evaluate_risks: scab infection (revised Mills), Marssonina/Alternaria, late blight (NIPHM), rain wash-off."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.domain.types import WeatherHour

from .helpers import at, farmer, make_engine, nutrient, series, snapshot, spray, weather_hour

NOW = "2026-04-25 10:00"                      # band B2, scab primary season
TOMATO = farmer(crops=["Tomato"], primary_crop="Tomato")
POTATO = farmer(crops=["Potato"], primary_crop="Potato")


def risks(weather, history=None, *, person=None, now=NOW):
    items = make_engine().evaluate_risks(person or farmer(), weather, at(now), history or [])
    return {r.id: r for r in items}


def wet_run_weather(runs, *, temp=10.0, now=NOW, total_hours=24 * 14):
    """Wet runs given as (hours_ago_start, hours_ago_end) offsets before now (inclusive); everything else dry."""
    when = at(now)

    def row(t):
        ago = (when - t) / timedelta(hours=1)
        wet = any(end <= ago <= start for start, end in runs)
        return temp, (95.0 if wet else 50.0), (0.5 if wet else 0.0)

    return snapshot(when, series(when, total_hours, row), [], temp_c=temp)


# ---------------------------------------------------------------------------------------------------------- scab / Mills
@pytest.mark.parametrize(
    ("temp", "wet", "level"),
    [
        (10.0, 12, "red"), (10.0, 11, "red"), (10.0, 10, "yellow"), (10.0, 8, "yellow"), (10.0, 7, "green"),       # needs 11 h
        (5.0, 21, "red"), (5.0, 20, "yellow"), (4.9, 21, "yellow"), (4.9, 28, "red"), (4.9, 19, "green"),          # 21 h at 5 C, 28 h at 3.9-4.9 C
        (16.1, 6, "red"), (20.0, 6, "red"), (25.0, 8, "red"), (25.0, 7, "yellow"), (26.1, 11, "red"), (26.1, 10, "yellow"),
        (13.9, 7, "red"), (13.0, 8, "red"), (13.0, 7, "yellow"),
        (1.1, 41, "red"), (1.1, 40, "yellow"), (1.0, 100, "green"), (-3.0, 100, "green"),                          # below the table: no infection
    ],
)
def test_mills_table_levels(temp, wet, level):
    r = risks(wet_run_weather([(wet - 1, 0)], temp=temp))["scab_infection_risk"]
    assert r.level.value == level


def test_red_detail_describes_the_infection_period():
    r = risks(wet_run_weather([(11, 0)]))["scab_infection_risk"]
    assert r.id == "scab_infection_risk"
    assert r.detail["wet_hours"] == 12 and r.detail["needed_hours"] == 11 and r.detail["mean_temp_c"] == 10.0
    assert r.detail["in_season"] is True and r.detail["period_start"] < r.detail["reached_at"] <= r.detail["period_end"]
    assert "scab" in r.title.en.lower() and r.text.hi and r.title.hi


def test_wet_periods_separated_by_less_than_8_dry_hours_are_joined():
    joined = risks(wet_run_weather([(19, 14), (6, 1)]))["scab_infection_risk"]            # 6 wet, 7 dry, 6 wet
    assert joined.level.value == "red" and joined.detail["wet_hours"] == 12
    apart = risks(wet_run_weather([(20, 15), (6, 1)]))["scab_infection_risk"]             # 8 dry hours between
    assert apart.level.value == "green"


def test_infection_that_ended_long_ago_is_not_an_alert():
    assert risks(wet_run_weather([(60, 49)]))["scab_infection_risk"].level.value == "green"      # reached and ended two days ago


def test_infection_reached_in_the_last_24_hours_is_red_even_after_it_ended():
    assert risks(wet_run_weather([(30, 14)]))["scab_infection_risk"].level.value == "red"


def test_a_long_ongoing_wet_period_stays_red():
    r = risks(wet_run_weather([(70, 0)]))["scab_infection_risk"]
    assert r.level.value == "red" and r.detail["wet_hours"] == 71


def test_scab_risk_only_in_the_primary_season():
    r = risks(wet_run_weather([(30, 0)], now="2026-07-05 08:00"), now="2026-07-05 08:00")["scab_infection_risk"]
    assert r.level.value == "green" and r.detail["in_season"] is False and "not the main scab season" in r.text.en


def test_scab_season_for_a_farmer_without_band_is_the_widest_window():
    person = farmer(phenology_band=None, elevation_m=None)
    r = risks(wet_run_weather([(30, 0)], now="2026-05-30 08:00"), person=person, now="2026-05-30 08:00")["scab_infection_risk"]
    assert r.level.value == "red"


def test_leaf_wet_flag_counts_without_rain_or_humidity():
    when = at(NOW)
    hours = [WeatherHour(time=when - timedelta(hours=h), temp_c=10.0, rh_pct=40.0, rain_mm=0.0, leaf_wet=h < 12) for h in range(24 * 14 - 1, -1, -1)]
    assert risks(snapshot(when, hours))["scab_infection_risk"].level.value == "red"


def test_leaf_wetness_proxy_thresholds():
    when = at(NOW)

    def weather(rain: float, rh: float):
        past = [WeatherHour(time=when - timedelta(hours=h), temp_c=10.0, rh_pct=rh if h < 12 else 50.0, rain_mm=rain if h < 12 else 0.0)
                for h in range(24 * 14 - 1, -1, -1)]
        return snapshot(when, past)

    assert risks(weather(0.1, 50.0))["scab_infection_risk"].level.value == "red"        # rain >= 0.1 mm
    assert risks(weather(0.0, 90.0))["scab_infection_risk"].level.value == "red"        # RH >= 90
    assert risks(weather(0.09, 89.0))["scab_infection_risk"].level.value == "green"


def test_too_little_weather_data_is_reported_not_guessed():
    when = at(NOW)
    r = risks(snapshot(when, series(when, 10, lambda t: (10.0, 95.0, 0.5))))["scab_infection_risk"]
    assert r.level.value == "green" and r.detail.get("insufficient_data") is True


def test_stale_weather_is_flagged_in_the_detail():
    weather = wet_run_weather([(11, 0)]).model_copy(update={"stale": True})
    assert risks(weather)["scab_infection_risk"].detail["weather_stale"] is True


# ---------------------------------------------------------------------------------------------------------- Marssonina / Alternaria
JULY = "2026-07-05 08:00"


def leaf_spot_weather(day_means, *, now=JULY, last_complete="2026-07-04"):
    """day_means: (temp, rh) per day, oldest first, the last entry being `last_complete` (a full day before now)."""
    when = at(now)
    end_day = at(last_complete + " 00:00").date()
    means = {end_day - timedelta(days=len(day_means) - 1 - i): m for i, m in enumerate(day_means)}

    def row(t):
        temp, rh = means.get(t.date(), (15.0, 50.0))
        return temp, rh, 0.0

    return snapshot(when, series(when, 24 * 14, row), [], temp_c=22.0)


def leaf_risk(weather, now=JULY):
    return risks(weather, now=now)["marssonina_alternaria_risk"]


@pytest.mark.parametrize(("days", "level"), [(6, "red"), (5, "red"), (4, "yellow"), (3, "yellow"), (2, "green"), (0, "green")])
def test_marssonina_needs_five_consecutive_warm_humid_days(days, level):
    weather = leaf_spot_weather([(22.0, 75.0)] * days) if days else leaf_spot_weather([(15.0, 50.0)])
    r = leaf_risk(weather)
    assert r.level.value == level and r.detail["consecutive_days"] == days


def test_a_cool_day_breaks_the_run():
    weather = leaf_spot_weather([(22.0, 75.0)] * 3 + [(18.0, 80.0)] + [(22.0, 75.0)] * 2)
    r = leaf_risk(weather)
    assert r.detail["consecutive_days"] == 2 and r.level.value == "green"


@pytest.mark.parametrize(("temp", "rh", "ok"), [(20.0, 80.0, False), (20.1, 80.0, True), (25.0, 70.0, True), (25.0, 69.9, False)])
def test_marssonina_thresholds_are_mean_temp_above_20_and_mean_rh_at_least_70(temp, rh, ok):
    assert (leaf_risk(leaf_spot_weather([(temp, rh)] * 5)).level.value == "red") is ok


def test_marssonina_does_not_apply_before_1_june():
    weather = leaf_spot_weather([(22.0, 75.0)] * 6, now="2026-05-20 08:00", last_complete="2026-05-19")
    r = leaf_risk(weather, "2026-05-20 08:00")
    assert r.level.value == "green" and r.detail["in_season"] is False and "1 June" in r.text.en


def test_days_before_1_june_do_not_count_towards_the_run():
    weather = leaf_spot_weather([(22.0, 75.0)] * 7, now="2026-06-04 08:00", last_complete="2026-06-03")
    r = leaf_risk(weather, "2026-06-04 08:00")
    assert r.detail["consecutive_days"] == 3 and r.level.value == "yellow"


def test_the_unfinished_current_day_is_ignored():
    r = leaf_risk(leaf_spot_weather([(22.0, 75.0)] * 5), now="2026-07-05 03:00")
    assert r.detail["consecutive_days"] == 5          # complete days only: a day is counted once it has all 24 hours


# ---------------------------------------------------------------------------------------------------------- late blight
def late_blight_weather(temp_hours: int, rh_hours: int, *, now=NOW, total=24 * 14):
    """Exactly `temp_hours` in-range temperature hours and `rh_hours` hours with RH > 85 in the last 168 hours."""
    when = at(now)
    start = when - timedelta(hours=167)

    def row(t):
        idx = int((t - start) / timedelta(hours=1))
        if idx < 0:
            return 30.0, 50.0, 0.0
        return (10.0 if idx < temp_hours else 30.0), (90.0 if idx < rh_hours else 50.0), 0.0

    return snapshot(when, series(when, total, row), [], temp_c=10.0)


@pytest.mark.parametrize(
    ("temp_hours", "rh_hours", "level"),
    [(115, 90, "red"), (168, 168, "red"), (114, 90, "yellow"), (115, 89, "yellow"), (92, 72, "yellow"), (91, 72, "green"),
     (115, 71, "green"), (0, 0, "green")],
)
def test_niphm_seven_day_rule(temp_hours, rh_hours, level):
    r = risks(late_blight_weather(temp_hours, rh_hours), person=POTATO)["late_blight_risk"]
    assert r.level.value == level
    assert r.detail["temp_hours"] == temp_hours and r.detail["rh_hours"] == rh_hours


def test_late_blight_is_only_evaluated_for_potato_and_tomato_growers():
    weather = late_blight_weather(150, 120)
    assert "late_blight_risk" not in risks(weather)                                         # apple farmer
    assert "late_blight_risk" in risks(weather, person=TOMATO)
    assert "late_blight_risk" in risks(weather, person=POTATO)
    assert "late_blight_risk" in risks(weather, person=farmer(crops=["Apple", "Potato"]))   # grows potato as a second crop


def test_late_blight_red_text_and_title_are_localised():
    r = risks(late_blight_weather(150, 120), person=POTATO)["late_blight_risk"]
    assert "ten days" in r.text.en and "दस दिन" in r.text.hi and r.title.hi


def test_late_blight_with_only_three_days_of_data_is_not_guessed():
    r = risks(late_blight_weather(40, 40, total=72), person=POTATO)["late_blight_risk"]
    assert r.level.value == "green" and r.detail["insufficient_data"] is True


def test_late_blight_uses_a_168_hour_window_ending_now():
    r = risks(late_blight_weather(168, 168), person=POTATO)["late_blight_risk"]
    assert r.detail["hours_available"] == 168


# ---------------------------------------------------------------------------------------------------------- rain wash-off
def washoff_weather(rain_at: dict[int, float], *, forecast: dict[int, float] | None = None, now=NOW):
    """rain_at: {hours before now: mm}; forecast: {hours after now: mm}."""
    when = at(now)
    rain = {when - timedelta(hours=h): mm for h, mm in rain_at.items()}
    past = series(when, 24 * 14, lambda t: (12.0, 60.0, rain.get(t, 0.0)))
    future = [weather_hour(when + timedelta(hours=h), rain=(forecast or {}).get(h, 0.0)) for h in range(1, 49)]
    return snapshot(when, past, future)


def test_heavy_rain_soon_after_a_spray_is_a_red_washoff():
    r = risks(washoff_weather({1: 12.0}), [spray("2026-04-25 08:00", "P022")])["rain_washoff"]
    assert r.level.value == "red" and r.detail["observed_rain_mm"] == 12.0 and r.detail["threshold_mm"] == 10.0
    assert "12 millimetres" in r.text.en and "7 days" in r.text.en and "मिलीमीटर" in r.text.hi


@pytest.mark.parametrize(("mm", "level"), [(10.0, "red"), (9.9, "green"), (0.0, "green")])
def test_washoff_threshold_is_10_mm(mm, level):
    assert risks(washoff_weather({1: mm}), [spray("2026-04-25 08:00", "P022")])["rain_washoff"].level.value == level


def test_rain_before_the_spray_is_not_a_washoff():
    assert risks(washoff_weather({5: 30.0}), [spray("2026-04-25 08:00", "P022")])["rain_washoff"].level.value == "green"


def test_washoff_only_counts_the_12_hours_after_the_spray():
    r = risks(washoff_weather({1: 6.0}, forecast={4: 20.0}), [spray("2026-04-25 02:00", "P022")])["rain_washoff"]
    assert r.detail["rain_mm"] == 6.0 and r.level.value == "green"                 # window 02:00-14:00 (end exclusive): 20 mm at 14:00 is outside


def test_forecast_rain_makes_it_a_yellow_warning():
    r = risks(washoff_weather({}, forecast={2: 12.0}), [spray("2026-04-25 08:00", "P022")])["rain_washoff"]
    assert r.level.value == "yellow" and "expected" in r.text.en


def test_no_washoff_item_without_a_recent_spray():
    weather = washoff_weather({1: 30.0})
    assert "rain_washoff" not in risks(weather)
    assert "rain_washoff" not in risks(weather, [spray("2026-04-24 09:00", "P022")])                 # 25 hours ago
    assert "rain_washoff" in risks(weather, [spray("2026-04-24 10:00", "P022")])                     # exactly 24 hours ago
    assert "rain_washoff" not in risks(weather, [nutrient("2026-04-25 08:00")])
    assert "rain_washoff" not in risks(weather, [spray("2026-04-25 11:00", "P022")])                 # not sprayed yet


def test_washoff_picks_the_spray_with_the_most_rain_after_it():
    history = [spray("2026-04-24 12:00", "P022"), spray("2026-04-25 09:00", "P011")]
    r = risks(washoff_weather({20: 15.0}), history)["rain_washoff"]
    assert r.detail["spray_at"].startswith("2026-04-24T12:00") and r.level.value == "red"


def test_washoff_applies_to_other_crops_too():
    r = risks(washoff_weather({1: 12.0}), [spray("2026-04-25 08:00", "P084")], person=POTATO)["rain_washoff"]
    assert r.level.value == "red"


# ---------------------------------------------------------------------------------------------------------- general
def test_apple_risks_are_not_given_to_other_crops():
    got = risks(wet_run_weather([(30, 0)]), person=TOMATO)
    assert "scab_infection_risk" not in got and "marssonina_alternaria_risk" not in got
    assert set(got) <= {"late_blight_risk", "rain_washoff"}


def test_apple_farmer_gets_scab_and_marssonina_items():
    assert list(risks(wet_run_weather([(30, 0)]))) == ["scab_infection_risk", "marssonina_alternaria_risk"]


def test_all_risk_items_are_localised_and_json_serialisable():
    weathers = [wet_run_weather([(30, 0)]), late_blight_weather(150, 120), leaf_spot_weather([(22.0, 75.0)] * 6), washoff_weather({1: 12.0})]
    for weather, person in zip(weathers, (farmer(), POTATO, farmer(), farmer()), strict=True):
        for r in make_engine().evaluate_risks(person, weather, weather.as_of, [spray("2026-04-25 08:00", "P022")]):
            assert r.title.en and r.title.hi and r.text.en and r.text.hi, r.id
            json.dumps(r.detail)


def test_risks_are_part_of_the_recommendation_output():
    from .helpers import rule_input

    out = make_engine().recommend(rule_input(now=NOW, weather=wet_run_weather([(11, 0)])))
    assert {r.id: r.level.value for r in out.risks}["scab_infection_risk"] == "red"
    assert out.severity.value == "red"


def test_evaluate_risks_ignores_hours_after_now_for_observed_rules():
    """A perfect forecast of a wet period must not be counted as an infection that already happened."""
    when = at(NOW)
    future = [weather_hour(when + timedelta(hours=h), temp=10.0, rh=95.0, rain=0.5) for h in range(1, 25)]
    weather = snapshot(when, series(when, 24 * 14, lambda t: (10.0, 50.0, 0.0)), future)
    assert risks(weather)["scab_infection_risk"].level.value == "green"
