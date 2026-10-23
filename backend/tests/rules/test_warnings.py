"""Warnings in the rule output: product-level and history-based (stale, off-label, tank mix, rotation limits)."""
from __future__ import annotations

import json

import pytest

from .helpers import farmer, make_engine, nutrient, rule_input, spray

NOW = "2026-04-25 10:00"


def run(history=None, *, now=NOW, engine=None, **kw):
    return (engine or make_engine()).recommend(rule_input(now=now, history=history or [], **kw))


def codes(out) -> list[str]:
    return [w.code for w in out.warnings]


def warning(out, code: str):
    return next(w for w in out.warnings if w.code == code)


# ---------------------------------------------------------------------------------------------------------- product level
def test_proposed_ban_product_carries_a_warning_but_is_still_allowed():
    out = run(engine=make_engine(lambda: {"P011", "P012", "P013", "P014", "P022", "P020"}))
    choice = next(p for p in out.products if p.product_id == "P009")
    w = next(w for w in choice.warnings if w.code == "PROPOSED_BAN")
    assert w.params["ban_status"] == "proposed_ban_2020_draft_still_registered"
    assert "Carbendazim" in w.text.en and "कार्बेन्डाज़िम" in w.text.hi


def test_missing_waiting_period_warning_is_per_product():
    out = run(engine=make_engine(lambda: {"P009", "P010", "P011", "P012", "P014", "P020", "P022"}))      # leaves flusilazole (WP unknown)
    choice = out.products[0]
    assert choice.product_id == "P013" and choice.waiting_period_days is None
    assert "NO_WAITING_PERIOD" in {w.code for w in choice.warnings}


def test_dose_per_200_litres_warning_for_apple_rows_only(widen_policy):
    out = run()
    assert all("DOSE_PER_200L" in {w.code for w in p.warnings} for p in out.products)
    widen_policy()
    potato = make_engine().recommend(rule_input(now="2026-07-10 10:00", crop_id="Potato", disease_id="Potato___Late_blight",
                                                farmer_=farmer(crops=["Potato"], primary_crop="Potato")))
    assert potato.products and not any(w.code == "DOSE_PER_200L" for p in potato.products for w in p.warnings)


def test_no_tank_mix_reminder_accompanies_every_recommendation():
    out = run()
    w = warning(out, "NO_TANK_MIX")
    assert "Do not mix" in w.text.en and "न मिलाएँ" in w.text.hi


# ---------------------------------------------------------------------------------------------------------- STALE_HISTORY
def test_stale_history_after_60_days_in_season():
    history = [spray("2026-02-24 10:00", "P001")]                       # 60 days before 25 Apr
    assert "STALE_HISTORY" not in codes(run(history))
    stale = run([spray("2026-02-23 10:00", "P001")])
    w = warning(stale, "STALE_HISTORY")
    assert w.params["days_since"] == 61 and w.params["last_spray"].startswith("2026-02-23")
    assert "23 Feb" in w.text.en and "23 फ़रवरी" in w.text.hi


def test_stale_history_without_any_record():
    w = warning(run([]), "STALE_HISTORY")
    assert w.params["last_spray"] is None and "no spray record for you" in w.text.en


def test_nutrient_rows_do_not_make_the_history_fresh():
    assert "STALE_HISTORY" in codes(run([nutrient("2026-04-20 10:00")]))


def test_any_spray_counts_as_fresh():
    assert "STALE_HISTORY" not in codes(run([spray("2026-04-10 10:00", "P052")]))                # an insecticide


def test_no_stale_warning_in_winter():
    out = run([], now="2026-01-20 10:00", farmer_=farmer(phenology_band="B2"))
    assert "STALE_HISTORY" not in codes(out)


def test_stale_warning_also_accompanies_expert_routes():
    out = run([], now="2026-07-05 08:00")
    assert out.status == "expert_review" and "STALE_HISTORY" in codes(out)


# ---------------------------------------------------------------------------------------------------------- OFF_LABEL_HISTORY
@pytest.mark.parametrize(
    "fields",
    [
        {"trade_name": "Syngenta Miravis Duo"},
        {"trade_name": "Miravis Duo"},
        {"active_ingredient": "Pydiflumetofen 6.89% SC Difenoconazole 11.49% SC", "frac_irac_code": "7 + 3"},
        {"trade_name": "Meothrin", "frac_irac_code": "IRAC 3A"},
        {"active_ingredient": "Fenpropathrin 30% EC"},
        {"trade_name": "Trot"},
        {"active_ingredient": "Thiamethoxam 30% FS", "frac_irac_code": "IRAC 4A"},
    ],
)
def test_off_label_history_is_flagged_for_apple(fields):
    out = run([spray("2026-04-10 10:00", None, **fields)])
    w = warning(out, "OFF_LABEL_HISTORY")
    assert w.params["products"] and "not approved for apple" in w.text.en and "सेब" in w.text.hi


@pytest.mark.parametrize("fields", [{"active_ingredient": "Thiamethoxam 25 WG"}, {"active_ingredient": "Difenoconazole 25 EC"},
                                    {"active_ingredient": "Mancozeb 75 WP"}, {"trade_name": "Score", "active_ingredient": "Difenoconazole"}])
def test_approved_or_unrelated_products_are_not_flagged_off_label(fields):
    assert "OFF_LABEL_HISTORY" not in codes(run([spray("2026-04-10 10:00", None, **fields)]))


def test_the_unapproved_active_alone_is_enough_to_flag_off_label():
    assert "OFF_LABEL_HISTORY" in codes(run([spray("2026-04-10 10:00", None, active_ingredient="Pydiflumetofen")]))


def test_off_label_history_is_not_a_problem_for_other_crops():
    out = make_engine().recommend(rule_input(
        now="2026-07-10 10:00", crop_id="Tomato", disease_id="Tomato___Early_blight", farmer_=farmer(crops=["Tomato"], primary_crop="Tomato"),
        history=[spray("2026-06-10 10:00", None, trade_name="Miravis Duo")]))
    assert "OFF_LABEL_HISTORY" not in codes(out)


def test_off_label_products_are_listed_once_and_never_recommended():
    history = [spray("2026-04-01 10:00", None, trade_name="Meothrin"), spray("2026-04-08 10:00", None, trade_name="Meothrin"),
               spray("2026-04-15 10:00", None, trade_name="Syngenta Miravis Duo")]
    out = run(history)
    assert warning(out, "OFF_LABEL_HISTORY").params["products"] == ["Meothrin", "Syngenta Miravis Duo"]
    assert not any(p.active_ingredient in ("Fenpropathrin", "Pydiflumetofen + Difenoconazole") for p in out.products)


# ---------------------------------------------------------------------------------------------------------- TANK_MIX_HISTORY
def test_nutrient_on_the_day_of_a_fungicide_is_flagged():
    out = run([spray("2026-04-14 10:00", "P009"), nutrient("2026-04-14 10:05"), nutrient("2026-04-14 10:10", "12.61.00")])
    w = warning(out, "TANK_MIX_HISTORY")
    assert w.params["dates"] == ["2026-04-14"] and "14 Apr" in w.text.en and "अलग से छिड़कें" in w.text.hi


def test_nutrient_on_another_day_is_not_flagged():
    assert "TANK_MIX_HISTORY" not in codes(run([spray("2026-04-14 10:00", "P009"), nutrient("2026-04-15 10:05")]))


def test_nutrient_with_an_insecticide_is_not_flagged():
    assert "TANK_MIX_HISTORY" not in codes(run([spray("2026-04-14 10:00", "P052"), nutrient("2026-04-14 10:05")]))


def test_old_tank_mix_is_not_repeated_forever():
    out = run([spray("2026-03-10 10:00", "P009"), nutrient("2026-03-10 10:05"), spray("2026-04-20 10:00", "P003")])
    assert "TANK_MIX_HISTORY" not in codes(out)


def test_nutrient_before_midnight_is_a_different_day():
    out = run([spray("2026-04-14 00:10", "P009"), nutrient("2026-04-13 23:50")])
    assert "TANK_MIX_HISTORY" not in codes(out)


# ---------------------------------------------------------------------------------------------------------- ROTATION_LIMIT
def test_rotation_limit_warning_when_dmi_is_used_up():
    history = [spray(f"2026-03-{5 + 4 * i:02d} 10:00", pid) for i, pid in enumerate(["P007", "P011", "P012", "P013"])]
    history.append(spray("2026-04-20 10:00", "P022"))
    w = warning(run(history), "ROTATION_LIMIT")
    assert w.params == {"kind": "dmi", "count": 4, "limit": 4}
    assert "DMI" in w.text.en and "डीएमआई" in w.text.hi


def test_rotation_limit_warning_for_two_consecutive_sdhi_sprays():
    history = [spray("2026-02-20 10:00", "P004"), spray("2026-03-01 10:00", "P030")]
    w = warning(run(history, now="2026-03-05 10:00"), "ROTATION_LIMIT")
    assert w.params["kind"] == "sdhi" and w.params["count"] == 2


def test_rotation_limit_warning_for_qoi():
    history = [spray(f"2026-03-{5 + 4 * i:02d} 10:00", "P014") for i in range(3)] + [spray("2026-04-20 10:00", "P022")]
    w = warning(run(history), "ROTATION_LIMIT")
    assert w.params["kind"] == "qoi" and w.params["limit"] == 3


def test_no_rotation_warning_below_the_limits():
    assert "ROTATION_LIMIT" not in codes(run([spray("2026-04-10 10:00", "P007"), spray("2026-04-20 10:00", "P022")]))


# ---------------------------------------------------------------------------------------------------------- harvest
def test_near_harvest_warning():
    out = run(days_to_harvest=15)
    w = warning(out, "NEAR_HARVEST")
    assert w.params["days_to_harvest"] == 15 and "15 days" in w.text.en


def test_no_near_harvest_warning_with_plenty_of_time():
    assert "NEAR_HARVEST" not in codes(run(days_to_harvest=22))


def test_unknown_harvest_date_warning_for_crops_without_a_calendar(widen_policy):
    widen_policy()
    out = make_engine().recommend(rule_input(now="2026-07-10 10:00", crop_id="Potato", disease_id="Potato___Late_blight",
                                             farmer_=farmer(crops=["Potato"], primary_crop="Potato")))
    assert "HARVEST_DATE_UNKNOWN" in codes(out)
    given = make_engine().recommend(rule_input(now="2026-07-10 10:00", crop_id="Potato", disease_id="Potato___Late_blight",
                                               farmer_=farmer(crops=["Potato"], primary_crop="Potato"), days_to_harvest=60))
    assert "HARVEST_DATE_UNKNOWN" not in codes(given)


# ---------------------------------------------------------------------------------------------------------- every warning is localised and JSON-safe
def test_all_warnings_have_english_and_hindi_text_and_json_safe_params():
    histories = [
        [spray("2026-02-10 10:00", "P001")],
        [spray("2026-04-14 10:00", "P009"), nutrient("2026-04-14 10:05"), spray("2026-04-15 10:00", None, trade_name="Meothrin")],
        [spray(f"2026-03-{5 + 4 * i:02d} 10:00", pid) for i, pid in enumerate(["P007", "P011", "P012", "P013"])],
        [],
    ]
    seen = set()
    for history in histories:
        out = run(history, days_to_harvest=15)
        for w in [*out.warnings, *[w for p in out.products for w in p.warnings]]:
            assert w.text.en.strip() and w.text.hi.strip(), w.code
            json.dumps(w.params)
            seen.add(w.code)
    assert {"STALE_HISTORY", "OFF_LABEL_HISTORY", "TANK_MIX_HISTORY", "ROTATION_LIMIT", "NEAR_HARVEST", "NO_TANK_MIX",
            "DOSE_PER_200L", "PROPOSED_BAN"} <= seen
