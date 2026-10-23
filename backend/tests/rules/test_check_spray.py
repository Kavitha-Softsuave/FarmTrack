"""check_spray: warnings for a NEW diary entry (same-day nutrients, repeated chemical or group, limits, banned/off-label, waiting period)."""
from __future__ import annotations

import json

from .helpers import at, engine_with_products, fake_product, farmer, make_engine, nutrient, spray

NOW = "2026-04-25 12:00"


def check(record, history=None, *, person=None, now=NOW, engine=None):
    out = (engine or make_engine()).check_spray(person or farmer(), record, history or [], at(now))
    return {w.code + (":" + w.params["kind"] if "kind" in w.params else ""): w for w in out}


def test_clean_entry_has_no_warnings():
    assert check(spray("2026-04-25 10:00", "P012"), [spray("2026-04-10 10:00", "P022")]) == {}


# ---------------------------------------------------------------------------------------------------------- same-day nutrient (HP point 7)
def test_nutrient_logged_with_a_fungicide_the_same_day_is_flagged_both_ways():
    fungicide_first = check(nutrient("2026-04-25 10:05"), [spray("2026-04-25 10:00", "P012")])
    assert "TANK_MIX_HISTORY" in fungicide_first
    nutrient_first = check(spray("2026-04-25 10:00", "P012"), [nutrient("2026-04-25 09:00", "12.61.00")])
    w = nutrient_first["TANK_MIX_HISTORY"]
    assert w.params == {"dates": ["2026-04-25"]} and "25 Apr" in w.text.en and w.text.hi


def test_nutrient_on_another_day_is_fine():
    assert "TANK_MIX_HISTORY" not in check(nutrient("2026-04-26 10:00"), [spray("2026-04-25 10:00", "P012")])


def test_nutrient_with_an_insecticide_is_fine():
    assert "TANK_MIX_HISTORY" not in check(nutrient("2026-04-25 10:05"), [spray("2026-04-25 10:00", "P052")])


# ---------------------------------------------------------------------------------------------------------- repeated chemical or group
def test_same_active_as_the_previous_fungicide():
    w = check(spray("2026-04-25 10:00", "P012"), [spray("2026-04-10 10:00", "P012")])["ROTATION_LIMIT:same_active"]
    assert "Myclobutanil" in w.text.en and "वही दवा" in w.text.hi and w.params["previous"] == "Myclobutanil"


def test_same_frac_group_with_a_different_active():
    w = check(spray("2026-04-25 10:00", "P011"), [spray("2026-04-10 10:00", "P012")])["ROTATION_LIMIT:same_frac"]
    assert w.params["components"] == "3" and "Change the group" in w.text.en


def test_only_the_previous_fungicide_is_compared():
    history = [spray("2026-04-01 10:00", "P012"), spray("2026-04-10 10:00", "P022")]
    assert check(spray("2026-04-25 10:00", "P012"), history) == {}


def test_a_later_entry_in_the_history_does_not_count_as_previous():
    assert check(spray("2026-04-25 10:00", "P012"), [spray("2026-04-26 10:00", "P012")], now="2026-04-27 10:00") == {}


def test_the_entry_itself_in_the_history_is_not_compared_with_itself():
    record = spray("2026-04-25 10:00", "P012")
    assert check(record, [record.model_copy(), spray("2026-04-10 10:00", "P022")]) == {}


def test_free_text_entry_is_resolved_before_comparing():
    record = spray("2026-04-25 10:00", None, trade_name="Systhane")
    assert "ROTATION_LIMIT:same_active" in check(record, [spray("2026-04-10 10:00", "P012")])


# ---------------------------------------------------------------------------------------------------------- DMI / QoI / SDHI limits
DMI_HISTORY = [spray("2026-03-05 10:00", "P007"), spray("2026-03-20 10:00", "P011"), spray("2026-04-05 10:00", "P013")]


def test_the_fourth_dmi_spray_reaches_the_limit():
    w = check(spray("2026-04-25 10:00", "P012"), DMI_HISTORY + [spray("2026-04-15 10:00", "P022")])["ROTATION_LIMIT:dmi"]
    assert w.level.value == "yellow" and (w.params["count"], w.params["limit"], w.params["exceeded"]) == (4, 4, False)


def test_the_fifth_dmi_spray_exceeds_it():
    history = [*DMI_HISTORY, spray("2026-04-10 10:00", "P008"), spray("2026-04-20 10:00", "P022")]
    w = check(spray("2026-04-25 10:00", "P012"), history)["ROTATION_LIMIT:dmi"]
    assert w.level.value == "red" and w.params["count"] == 5 and w.params["exceeded"] is True


def test_the_third_dmi_spray_is_fine():
    assert "ROTATION_LIMIT:dmi" not in check(spray("2026-04-25 10:00", "P012"), DMI_HISTORY[:2] + [spray("2026-04-20 10:00", "P022")])


def test_a_non_dmi_entry_is_not_a_dmi_problem():
    assert "ROTATION_LIMIT:dmi" not in check(spray("2026-04-25 10:00", "P022"), DMI_HISTORY + [spray("2026-04-15 10:00", "P008")])


def test_dmi_in_a_mixture_entry_counts():
    assert "ROTATION_LIMIT:dmi" in check(spray("2026-04-25 10:00", "P016"), DMI_HISTORY + [spray("2026-04-15 10:00", "P022")])      # 3 + M04


def test_qoi_limit_and_solo_qoi():
    history = [spray(f"2026-03-{5 + 8 * i:02d} 10:00", "P014") for i in range(2)] + [spray("2026-04-20 10:00", "P022")]
    assert check(spray("2026-04-25 10:00", "P026"), history)["ROTATION_LIMIT:qoi"].params["count"] == 3          # metiram + pyraclostrobin
    solo = check(spray("2026-04-25 10:00", "P071"), [spray("2026-04-10 10:00", "P022")], person=farmer(crops=["Tomato"], primary_crop="Tomato"))
    assert "ROTATION_LIMIT:qoi_solo" in solo and "QoI" in solo["ROTATION_LIMIT:qoi_solo"].text.en


def test_third_consecutive_sdhi_exceeds_the_limit_and_the_second_reaches_it():
    one = [spray("2026-04-01 10:00", "P004")]
    two = [*one, spray("2026-04-10 10:00", "P030")]
    assert check(spray("2026-04-25 10:00", "P017"), one)["ROTATION_LIMIT:sdhi"].level.value == "yellow"
    exceeded = check(spray("2026-04-25 10:00", "P017"), two)["ROTATION_LIMIT:sdhi"]
    assert exceeded.level.value == "red" and exceeded.params["count"] == 3


def test_sdhi_after_a_different_group_starts_a_new_count():
    history = [spray("2026-04-01 10:00", "P004"), spray("2026-04-08 10:00", "P030"), spray("2026-04-15 10:00", "P022")]
    assert "ROTATION_LIMIT:sdhi" not in check(spray("2026-04-25 10:00", "P017"), history)


def test_limits_only_apply_to_fungicide_entries():
    assert check(spray("2026-04-25 10:00", "P052"), DMI_HISTORY) == {}


# ---------------------------------------------------------------------------------------------------------- banned, off-label, proposed ban
def test_off_label_entry_is_flagged():
    for fields in ({"trade_name": "Syngenta Miravis Duo"}, {"active_ingredient": "Fenpropathrin 30% EC"},
                   {"active_ingredient": "Thiamethoxam 30% FS", "frac_irac_code": "IRAC 4A"}):
        w = check(spray("2026-04-25 10:00", None, **fields))["OFF_LABEL_PRODUCT"]
        assert "not approved for apple" in w.text.en and w.text.hi


def test_off_label_entry_for_another_crop_is_not_flagged():
    assert check(spray("2026-04-25 10:00", None, trade_name="Miravis Duo"), person=farmer(crops=["Tomato"], primary_crop="Tomato")) == {}


def test_banned_active_entry_is_red():
    w = check(spray("2026-04-25 10:00", None, active_ingredient="Dimethoate 30% EC"))["BANNED_PRODUCT"]
    assert w.level.value == "red" and "banned" in w.text.en


def test_banned_master_row_entry_is_red():
    engine = engine_with_products([fake_product("PX1", "Safecide", ban="banned")])
    assert check(spray("2026-04-25 10:00", "PX1"), engine=engine)["BANNED_PRODUCT"].level.value == "red"


def test_proposed_ban_entry_gets_a_gentle_warning():
    w = check(spray("2026-04-25 10:00", "P009"))["PROPOSED_BAN"]
    assert w.level.value == "yellow" and "Carbendazim" in w.text.en


# ---------------------------------------------------------------------------------------------------------- waiting period, captan and oil
def test_waiting_period_longer_than_the_days_to_harvest():
    person = farmer(phenology_band="B2")                                      # Royal Delicious harvest: day 238 = 26 Aug
    w = check(spray("2026-08-16 10:00", "P012"), person=person, now="2026-08-16 12:00")["WAITING_PERIOD_EXCEEDS_HARVEST"]
    assert (w.params["waiting_period_days"], w.params["days_to_harvest"]) == (21, 10) and w.level.value == "red"
    assert "21 days" in w.text.en and "10 days" in w.text.en


def test_waiting_period_within_the_days_to_harvest_is_fine():
    assert "WAITING_PERIOD_EXCEEDS_HARVEST" not in check(spray("2026-07-01 10:00", "P012"), now="2026-07-01 12:00")


def test_unknown_waiting_period_close_to_harvest_is_noted():
    out = check(spray("2026-08-16 10:00", "P013"), now="2026-08-16 12:00")
    assert "NO_WAITING_PERIOD" in out


def test_captan_after_oil_and_oil_after_captan():
    after_oil = check(spray("2026-04-25 10:00", "P001"), [spray("2026-04-15 10:00", "P051")])
    assert "CAPTAN_OIL_GAP" in after_oil and after_oil["CAPTAN_OIL_GAP"].params == {"days": 15}
    after_captan = check(spray("2026-04-25 10:00", "P057"), [spray("2026-04-15 10:00", "P001")])
    assert "CAPTAN_OIL_GAP" in after_captan
    assert "CAPTAN_OIL_GAP" not in check(spray("2026-04-25 10:00", "P001"), [spray("2026-04-09 10:00", "P051")])


def test_captan_mixture_after_oil():
    assert "CAPTAN_OIL_GAP" in check(spray("2026-04-25 10:00", "P016"), [spray("2026-04-15 10:00", "P051")])


# ---------------------------------------------------------------------------------------------------------- shape
def test_warnings_are_localised_and_json_safe():
    history = DMI_HISTORY + [spray("2026-04-15 10:00", "P022"), spray("2026-04-25 09:00", None, trade_name="Meothrin"), nutrient("2026-04-25 10:30")]
    out = make_engine().check_spray(farmer(), spray("2026-04-25 10:00", "P009"), history, at(NOW))
    assert out
    for w in out:
        assert w.text.en and w.text.hi, w.code
        json.dumps(w.params)


def test_check_spray_accepts_naive_and_aware_times_consistently():
    record = spray("2026-04-25 10:00", "P012")
    aware = make_engine().check_spray(farmer(), record, [spray("2026-04-10 10:00", "P012")], at(NOW))
    naive = make_engine().check_spray(farmer(), record, [spray("2026-04-10 10:00", "P012")], at(NOW).replace(tzinfo=None))
    assert [w.code for w in aware] == [w.code for w in naive]
