"""Replay of the demo scenarios S1..S11 (data/demo_scenarios.json) with the real Zoho rows and weather archive.

Each test builds the RuleInput exactly as the app would at the scenario clock (history up to the clock, weather snapshot with
14 days observed and 48 hours of 'perfect forecast') and asserts the rules part of the scenario's expected_behaviour.
"""
from __future__ import annotations

import pytest

from app.rules import codes

from .helpers import (
    SCAB,
    apple_farmers_at,
    history_for,
    make_engine,
    scenario_clock,
    scenario_input,
    snapshot_at,
    world,
)

MARSSONINA = "Apple___Marssonina_blotch"
ALTERNARIA = "Apple___Alternaria_leaf_spot"


def risk_levels(out) -> dict[str, str]:
    return {r.id: r.level.value for r in out.risks}


def test_all_scenarios_are_present():
    assert set(world().scenarios) == {f"S{i}" for i in range(1, 12)}


# ---------------------------------------------------------------------------------------------------------- S1
def test_s1_scab_at_petal_fall_after_carbendazim(engine, ref):
    scenario = world().scenarios["S1"]
    out = engine.recommend(scenario_input("S1", SCAB))
    assert (out.status, out.route, out.stage) == ("advice", "auto_advice", "petal_fall")

    # carbendazim and every FRAC-1 scab product for this stage are excluded; none is recommended
    frac1 = {p.product_id for p in ref.products if p.crop == "Apple" and p.stage == "petal_fall" and SCAB in p.targets
             and codes.MBC in p.components}
    assert {"P009", "P010", "P020"} <= frac1
    assert frac1 <= {e.product_id for e in out.excluded}
    assert not any(codes.MBC in codes.components(p.frac_irac_code) for p in out.products)

    # a non-FRAC-1 petal-fall scab product is recommended, with its waiting period
    myclobutanil = next(p for p in out.products if p.product_id == "P012")
    assert (myclobutanil.dose_min, myclobutanil.dose_unit, myclobutanil.waiting_period_days) == (80.0, "g/200L", 21)
    assert all(p.stage == "petal_fall" for p in out.products)
    assert all(p.waiting_period_days is not None or any(w.code == "NO_WAITING_PERIOD" for w in p.warnings) for p in out.products)

    # timing comes from the next-12-hours rain of the scenario
    assert out.timing.rain_next_12h_mm == scenario["facts"]["rain_next_12h_mm"] == 0.0
    assert out.timing.action == "spray_now"
    # the infection period in the facts is what makes systemic products come first
    infection = scenario["facts"]["infection_period"]
    scab = next(r for r in out.risks if r.id == "scab_infection_risk")
    assert scab.level.value == "red" and scab.detail["wet_hours"] == infection["wet_hours"]
    assert scab.detail["needed_hours"] == infection["mills_hours_needed"]
    assert out.products[0].behaviour == "systemic"
    assert any("Days to harvest" in line for line in out.trace)


# ---------------------------------------------------------------------------------------------------------- S2
def test_s2_marssonina_goes_to_the_expert_with_the_weather_risk(engine):
    scenario = world().scenarios["S2"]
    out = engine.recommend(scenario_input("S2", MARSSONINA))
    assert (out.status, out.route, out.products, out.excluded) == ("expert_review", "expert_queue", [], [])
    assert "not_in_auto_advice_policy" in out.reasons
    assert risk_levels(out)["marssonina_alternaria_risk"] == "red"
    risk = next(r for r in out.risks if r.id == "marssonina_alternaria_risk")
    assert risk.detail["consecutive_days"] >= 5
    assert out.non_chemical and out.severity.value == "red"
    assert scenario["facts"]["marssonina_rule_first_true_day"] <= scenario["demo_clock"][:10]


# ---------------------------------------------------------------------------------------------------------- S3
def test_s3_heavy_rain_after_mancozeb_means_repeat_within_7_days(engine):
    scenario = world().scenarios["S3"]
    out = engine.recommend(scenario_input("S3", SCAB))
    washoff = next(r for r in out.risks if r.id == "rain_washoff")
    assert washoff.level.value == "red"
    assert washoff.detail["observed_rain_mm"] == scenario["facts"]["rain_in_12h_after_spray_mm"] == 15.3
    assert washoff.detail["threshold_mm"] == scenario["facts"]["heavy_rain_threshold_mm_config"]
    assert out.timing.action == "repeat_within_days" and out.timing.repeat_within_days == 7
    assert out.severity.value == "red"
    # the repeat spray must be a different chemical from the mancozeb that was washed off
    assert not any("mancozeb" in p.active_ingredient.lower() for p in out.products)


def test_s3_alert_is_also_available_without_a_scan(engine):
    inp = scenario_input("S3", None)
    risks = engine.evaluate_risks(inp.farmer, inp.weather, inp.now, inp.history)
    assert {r.id: r.level.value for r in risks}["rain_washoff"] == "red"


# ---------------------------------------------------------------------------------------------------------- S4
def test_s4_scab_infection_is_red_at_the_alert_time_for_every_apple_farmer_at_the_station(engine):
    scenario = world().scenarios["S4"]
    farmers = apple_farmers_at("ST05")
    assert len(farmers) == scenario["facts"]["apple_farmers_alerted"] == 5
    now = scenario_clock("S4")
    weather = snapshot_at("ST05", now)
    for person in farmers:
        risks = {r.id: r for r in engine.evaluate_risks(person, weather, now, history_for(person.id, now))}
        assert risks["scab_infection_risk"].level.value == "red", person.id
        assert risks["scab_infection_risk"].detail["period_start"].startswith("2026-05-04T11:00")


def test_s4_the_alert_is_not_red_before_the_threshold(engine):
    person = apple_farmers_at("ST05")[0]
    early = scenario_clock("S4").replace(hour=12)
    risks = {r.id: r for r in engine.evaluate_risks(person, snapshot_at("ST05", early), early, history_for(person.id, early))}
    assert risks["scab_infection_risk"].level.value == "green"
    late = scenario_clock("S4").replace(hour=21)
    assert {r.id: r for r in engine.evaluate_risks(person, snapshot_at("ST05", late), late, [])}["scab_infection_risk"].level.value == "red"


def test_s4_each_farmers_advice_avoids_their_own_last_chemical_group(engine):
    for person in apple_farmers_at("ST05"):
        inp = scenario_input("S4", SCAB, farmer_id=person.id)
        out = engine.recommend(inp)
        assert out.severity.value == "red"
        if out.status == "advice":
            assert not {p.product_id for p in out.products} & {e.product_id for e in out.excluded}


# ---------------------------------------------------------------------------------------------------------- S5
def test_s5_off_label_history_is_flagged_and_never_recommended(engine, ref, widen_policy):
    out = engine.recommend(scenario_input("S5", SCAB))
    warning = next(w for w in out.warnings if w.code == "OFF_LABEL_HISTORY")
    assert warning.params["products"] == ["Meothrin", "Syngenta Miravis Duo", "Trot (Thiamethoxam 30% FS)"]      # in diary order
    assert "not approved for apple" in warning.text.en

    widen_policy()
    offlabel_actives = {"fenpropathrin", "thiamethoxam", "pydiflumetofen"}
    inp = scenario_input("S5", SCAB)
    for disease in ref.diseases.values():
        if disease.crop != "Apple":
            continue
        result = engine.recommend(inp.model_copy(update={"disease_id": disease.disease_id, "disease_confidence": 0.99}))
        for product in result.products:
            assert not offlabel_actives & {a.strip().lower() for a in product.active_ingredient.split("+")}


# ---------------------------------------------------------------------------------------------------------- S6
def _s6(engine, ref, disease):
    inp = scenario_input("S6", disease)
    out = engine.recommend(inp)
    return inp, out


@pytest.mark.parametrize("disease", [MARSSONINA, ALTERNARIA])
def test_s6_default_policy_sends_leaf_spots_to_the_expert_but_warns_about_the_dmi_limit(engine, ref, disease):
    _, out = _s6(engine, ref, disease)
    assert (out.status, out.products) == ("expert_review", [])
    assert any(w.code == "ROTATION_LIMIT" and w.params["kind"] == "dmi" and w.params["count"] == 4 for w in out.warnings)


@pytest.mark.parametrize("disease", [MARSSONINA, ALTERNARIA])
def test_s6_dmi_limit_excludes_every_product_containing_frac_3_even_in_mixtures(engine, ref, widen_policy, disease):
    widen_policy()
    inp, out = _s6(engine, ref, disease)
    assert out.status == "advice" and out.stage == "walnut_size"
    stage_rows = [p for p in ref.products if p.crop == "Apple" and p.stage == "walnut_size" and disease in p.targets and p.usable]
    dmi_rows = [p for p in stage_rows if codes.DMI in p.components]
    assert dmi_rows and any(len(p.components) > 1 for p in dmi_rows), "the scenario must include DMI mixtures"
    excluded = {e.product_id: e.reasons for e in out.excluded}
    for row in dmi_rows:
        assert "dmi_season_limit" in excluded[row.product_id], row.product_id
    assert all(codes.DMI not in codes.components(p.frac_irac_code) for p in out.products)
    # non-DMI options such as metiram or metiram + pyraclostrobin are offered
    assert {p.active_ingredient for p in out.products} & {"Metiram", "Metiram + Pyraclostrobin", "Propineb"}
    assert any(w.code == "ROTATION_LIMIT" and w.params["kind"] == "dmi" for w in out.warnings)


def test_s6_qoi_count_is_still_zero_so_the_qoi_mixture_is_allowed(engine, ref, widen_policy):
    widen_policy()
    _, out = _s6(engine, ref, MARSSONINA)
    assert "P026" not in {e.product_id for e in out.excluded}                       # metiram + pyraclostrobin


# ---------------------------------------------------------------------------------------------------------- S7
def test_s7_late_blight_risk_is_true_for_the_potato_farmer(engine):
    out = engine.recommend(scenario_input("S7", "Potato___Late_blight"))
    risk = next(r for r in out.risks if r.id == "late_blight_risk")
    assert risk.level.value == "red" and risk.detail["met"] is True
    assert risk.detail["temp_hours"] >= 115 and risk.detail["rh_hours"] >= 90
    assert "ten days" in risk.text.en
    # potato late blight is not an auto-advice disease: expert queue plus general measures, never a fungicide
    assert (out.status, out.products) == ("expert_review", [])
    assert out.severity.value == "red"


def test_s7_with_a_wider_policy_the_last_chemical_is_not_repeated(engine, widen_policy):
    """The data scenario suggests mancozeb again, but HP rule 3 (never repeat the same chemical) wins: mancozeb was used 13 days earlier."""
    widen_policy()
    out = engine.recommend(scenario_input("S7", "Potato___Late_blight"))
    assert out.status == "advice"
    assert not any("mancozeb" in p.active_ingredient.lower() for p in out.products)
    assert {e.product_id for e in out.excluded} >= {"P084", "P085", "P086"}
    assert any(w.code == "HARVEST_DATE_UNKNOWN" for w in out.warnings)


# ---------------------------------------------------------------------------------------------------------- S8
def test_s8_tomato_yellow_leaf_curl_virus_has_no_cure_and_no_fungicide(engine, widen_policy):
    for _ in range(2):                                        # default policy, then the widest policy: no change
        out = engine.recommend(scenario_input("S8", "Tomato___Tomato_Yellow_Leaf_Curl_Virus", confidence=0.95))
        assert (out.status, out.route, out.products, out.excluded) == ("expert_review", "expert_queue", [], [])
        assert "no_chemical_cure" in out.reasons
        assert out.non_chemical[0].en.startswith("No cure") and "इलाज" in out.non_chemical[0].hi
        assert any("yellow traps" in m.en for m in out.non_chemical)
        widen_policy()


# ---------------------------------------------------------------------------------------------------------- S9
def test_s9_nutrients_logged_with_a_fungicide_are_flagged(engine):
    out = engine.recommend(scenario_input("S9", SCAB))
    warning = next(w for w in out.warnings if w.code == "TANK_MIX_HISTORY")
    assert warning.params["dates"] == ["2026-04-14"]
    assert "separately" in warning.text.en and "14 Apr" in warning.text.en
    inp = scenario_input("S9", SCAB)
    mixed = [r for r in inp.history if r.sprayed_at.date().isoformat() == "2026-04-14"]
    assert {bool(r.nutrient) for r in mixed} == {True, False}


def test_s9_check_spray_flags_a_new_nutrient_entry_on_a_fungicide_day(engine):
    inp = scenario_input("S9", SCAB)
    fungicide = next(r for r in inp.history if not r.nutrient and r.sprayed_at.date().isoformat() == "2026-04-14")
    nutrients = [r for r in inp.history if r.nutrient]
    others = [r for r in inp.history if r is not nutrients[0]]
    codes_found = {w.code for w in engine.check_spray(inp.farmer, nutrients[0], others, inp.now)}
    assert "TANK_MIX_HISTORY" in codes_found and fungicide


# ---------------------------------------------------------------------------------------------------------- S10
def test_s10_stale_history_warning(engine):
    out = engine.recommend(scenario_input("S10", SCAB))
    warning = next(w for w in out.warnings if w.code == "STALE_HISTORY")
    assert warning.params["days_since"] >= 60
    assert warning.params["last_spray"] < "2026-08-06"
    assert "no spray record after" in warning.text.en


# ---------------------------------------------------------------------------------------------------------- S11
@pytest.mark.skip(reason="S11 (sensor station offline) is an integrations matter, not a rules matter")
def test_s11_sensor_offline():
    raise AssertionError


def test_s11_weather_staleness_is_only_carried_through_the_risk_detail(engine):
    inp = scenario_input("S11", None, farmer_id=apple_farmers_at("ST08")[0].id)
    stale = inp.weather.model_copy(update={"stale": True})
    risks = engine.evaluate_risks(inp.farmer, stale, inp.now, inp.history)
    assert risks and all(r.detail["weather_stale"] is True for r in risks)


# ---------------------------------------------------------------------------------------------------------- whole-dataset sweep
def test_every_scenario_farmer_and_clock_runs_without_error_and_stays_inside_the_approved_list(ref):
    engine = make_engine()
    approved = {p.product_id for p in ref.products if p.usable}
    for sid, scenario in world().scenarios.items():
        fid = scenario["farmer_id"]
        if fid.startswith("("):
            continue
        for disease in ("Apple___Apple_scab", MARSSONINA, "Potato___Late_blight", "Tomato___Early_blight", None):
            out = engine.recommend(scenario_input(sid, disease))
            assert {p.product_id for p in out.products} <= approved
            if out.status != "advice":
                assert out.products == []
