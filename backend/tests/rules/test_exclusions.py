"""Every exclusion rule, one by one. Base case: apple scab at petal fall (band B2, 25 Apr 2026, 123 days to harvest).

Petal-fall scab rows: P009 carbendazim (1), P010 thiophanate-methyl (1), P011 hexaconazole (3), P012 myclobutanil (3, WP 21),
P013 flusilazole (3, WP unknown), P014 mancozeb+pyraclostrobin (M03+11, WP unknown), P020 carbendazim+mancozeb (1+M03), P022 metiram (M03).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain.types import Severity

from .helpers import (
    at,
    engine_with_products,
    fake_product,
    hourly,
    make_engine,
    nutrient,
    rule_input,
    snapshot,
    spray,
    weather_hour,
)

NOW = "2026-04-25 10:00"
PETAL_FALL_SCAB = {"P009", "P010", "P011", "P012", "P013", "P014", "P020", "P022"}


def run(history=None, *, now=NOW, engine=None, **kw):
    return (engine or make_engine()).recommend(rule_input(now=now, history=history or [], **kw))


def reasons_of(out) -> dict[str, list[str]]:
    return {e.product_id: e.reasons for e in out.excluded}


def product_ids(out) -> list[str]:
    return [p.product_id for p in out.products]


def test_without_history_nothing_is_excluded():
    out = run()
    assert out.excluded == []
    assert len(out.products) == 3 and set(product_ids(out)) <= PETAL_FALL_SCAB


# ---------------------------------------------------------------------------------------------------------- same active / FRAC group
def test_same_active_as_the_last_spray_is_excluded_and_so_is_its_frac_group_when_alternatives_exist():
    out = run([spray("2026-04-10 10:00", "P012")])
    reasons = reasons_of(out)
    assert reasons["P012"] == ["same_active_as_last_spray"]
    assert reasons["P011"] == reasons["P013"] == ["same_frac_as_last_spray"]
    assert not {"P011", "P012", "P013"} & set(product_ids(out))


def test_only_the_last_fungicide_spray_counts_for_rotation():
    out = run([spray("2026-04-01 10:00", "P012"), spray("2026-04-12 10:00", "P022")])
    reasons = reasons_of(out)
    assert reasons["P022"] == ["same_active_as_last_spray"]
    assert reasons["P014"] == reasons["P020"] == ["same_frac_as_last_spray"]        # share group M03 with metiram
    assert "P012" not in reasons


def test_every_frac_1_product_follows_carbendazim():
    out = run([spray("2026-04-10 10:00", "P009")])
    reasons = reasons_of(out)
    assert reasons["P009"] == ["same_active_as_last_spray"]
    assert reasons["P020"] == ["same_active_as_last_spray"]                           # carbendazim + mancozeb
    assert reasons["P010"] == ["same_frac_as_last_spray"]                             # thiophanate-methyl is FRAC 1 too
    assert not {"P009", "P010", "P020"} & set(product_ids(out))


def test_same_frac_is_kept_with_a_warning_when_no_alternative_exists():
    others = PETAL_FALL_SCAB - {"P011", "P012", "P013"}
    engine = make_engine(lambda: set(others))
    out = run([spray("2026-04-10 10:00", "P007")], engine=engine)          # difenoconazole: FRAC 3, not one of the candidates
    assert sorted(product_ids(out)) == ["P011", "P012", "P013"]
    assert all(r == ["disabled_by_admin"] for r in reasons_of(out).values())
    for choice in out.products:
        warning = next(w for w in choice.warnings if w.code == "ROTATION_LIMIT")
        assert warning.params["kind"] == "same_frac_no_alternative" and warning.params["components"] == ["3"]
        assert warning.text.en and warning.text.hi


def test_group_rotation_ignores_insecticide_sprays_and_nutrients():
    out = run([spray("2026-04-10 10:00", "P052"), nutrient("2026-04-12 10:00")])        # thiacloprid, zinc/boron
    assert out.excluded == []


def test_a_spray_dated_after_now_is_ignored():
    assert run([spray("2026-04-26 10:00", "P012")]).excluded == []


def test_sprays_of_another_crop_do_not_drive_apple_rotation():
    history = [spray("2026-04-20 10:00", "P084")] + [spray(f"2026-04-0{i} 10:00", "P089") for i in range(1, 6)]   # potato mancozeb, maize hexaconazole
    assert run(history).excluded == []


def test_free_text_history_is_resolved_through_the_brand_master():
    out = run([spray("2026-04-10 10:00", None, trade_name="Bavistin")])
    assert reasons_of(out)["P009"] == ["same_active_as_last_spray"]
    assert reasons_of(out)["P010"] == ["same_frac_as_last_spray"]


def test_free_text_history_with_a_messy_frac_code():
    out = run([spray("2026-04-10 10:00", None, active_ingredient="Mancozeb 75 WP", frac_irac_code="M3")])
    reasons = reasons_of(out)
    assert reasons["P022"] == ["same_frac_as_last_spray"]                 # metiram: another active, same M03 group
    assert reasons["P014"] == reasons["P020"] == ["same_active_as_last_spray"]    # both mixtures contain mancozeb


# ---------------------------------------------------------------------------------------------------------- DMI
def _dmi_history(n: int, last: str = "P022"):
    """n DMI sprays in March 2026 followed by a non-DMI spray (so the DMI limit is the only rule in play)."""
    ids = ["P007", "P011", "P012", "P013"][:n]
    history = [spray(f"2026-03-{5 + 4 * i:02d} 10:00", pid) for i, pid in enumerate(ids)]
    return history + [spray("2026-04-20 10:00", last)]


def test_dmi_limit_excludes_every_product_with_frac_3():
    out = run(_dmi_history(4))
    reasons = reasons_of(out)
    for pid in ("P011", "P012", "P013"):
        assert reasons[pid] == ["dmi_season_limit"]
    assert not any("3" in p.frac_irac_code.split("+") for p in out.products if p.frac_irac_code)


def test_three_dmi_sprays_are_still_allowed():
    out = run(_dmi_history(3))
    assert not any("dmi_season_limit" in r for r in reasons_of(out).values())
    assert {"P011", "P012", "P013"} & (set(product_ids(out)) | set(reasons_of(out)))


def test_dmi_sprays_of_last_year_do_not_count():
    history = [spray(f"2025-0{m}-10 10:00", pid) for m, pid in zip((5, 6, 7, 8), ("P007", "P011", "P012", "P013"), strict=True)]
    assert not any("dmi_season_limit" in r for r in reasons_of(run(history)).values())


def test_dmi_inside_mixtures_counts():
    mixtures = ["P008", "P016", "P027", "P004"]               # 3+M03, 3+M04, 3+M04, 7+3
    history = [spray(f"2026-03-{5 + 4 * i:02d} 10:00", pid) for i, pid in enumerate(mixtures)] + [spray("2026-04-20 10:00", "P022")]
    out = run(history)
    assert all(reasons_of(out)[pid] == ["dmi_season_limit"] for pid in ("P011", "P012", "P013"))
    warning = next(w for w in out.warnings if w.code == "ROTATION_LIMIT")
    assert warning.params == {"kind": "dmi", "count": 4, "limit": 4}


def test_dmi_is_counted_from_free_text_and_frac_code_alone():
    history = [spray(f"2026-03-{5 + 4 * i:02d} 10:00", None, active_ingredient=name, frac_irac_code="3")
               for i, name in enumerate(["myclobutanil", "difenoconazole", "flusilazole", "tebuconazole"])]
    out = run(history + [spray("2026-04-20 10:00", "P022")])
    assert all("dmi_season_limit" in reasons_of(out)[pid] for pid in ("P011", "P012", "P013"))


def test_duplicate_zoho_rows_for_one_spray_count_once():
    first = spray("2026-03-05 10:00", "P007")
    history = [first, first.model_copy(), spray("2026-03-09 10:00", "P011"), spray("2026-03-13 10:00", "P012"), spray("2026-04-20 10:00", "P022")]
    assert not any("dmi_season_limit" in r for r in reasons_of(run(history)).values())


def test_irac_3a_insecticide_is_not_a_dmi_spray():
    history = [spray(f"2026-03-{5 + 4 * i:02d} 10:00", None, active_ingredient="Fenpropathrin 30% EC", frac_irac_code="IRAC 3A")
               for i in range(5)]
    assert not any("dmi_season_limit" in r for r in reasons_of(run(history)).values())


# ---------------------------------------------------------------------------------------------------------- QoI
def _qoi_history(qoi: int, total: int):
    """`total` fungicide sprays since January, `qoi` of them QoI mixtures (P014), the last one a plain metiram."""
    sprays = []
    for i in range(total - 1):
        pid = "P014" if i < qoi else "P033"
        sprays.append(spray(f"2026-01-{5 + 2 * i:02d} 10:00", pid))
    sprays.append(spray("2026-04-20 10:00", "P022"))
    return sprays


def test_qoi_limit_of_three_excludes_qoi_products():
    out = run(_qoi_history(3, 4))
    assert "qoi_season_limit" in reasons_of(out)["P014"]


def test_two_qoi_sprays_are_allowed():
    out = run(_qoi_history(2, 4))
    assert "qoi_season_limit" not in reasons_of(out).get("P014", [])


def test_qoi_limit_is_four_after_twelve_sprays():
    assert "qoi_season_limit" not in reasons_of(run(_qoi_history(3, 12))).get("P014", [])
    assert "qoi_season_limit" in reasons_of(run(_qoi_history(4, 12)))["P014"]


def test_a_qoi_product_alone_is_excluded_but_the_mixture_is_not(widen_policy):
    widen_policy()
    from .helpers import farmer

    out = make_engine().recommend(rule_input(
        now="2026-07-10 10:00", crop_id="Tomato", disease_id="Tomato___Early_blight", confidence=0.9,
        farmer_=farmer(crops=["Tomato"], primary_crop="Tomato")))
    assert reasons_of(out)["P071"] == ["qoi_only_in_mixture"]            # azoxystrobin alone
    assert "P072" in product_ids(out) or "P070" in product_ids(out)       # metiram + pyraclostrobin or mancozeb
    assert "P071" not in product_ids(out)


# ---------------------------------------------------------------------------------------------------------- SDHI
GREEN_TIP = "2026-03-05 10:00"          # band B2 day 64: green tip; scab rows P001 captan, P002 dodine, P003 ziram, P004 (7+3)


def test_two_consecutive_sdhi_sprays_exclude_sdhi_products():
    out = run([spray("2026-02-20 10:00", "P004"), spray("2026-03-01 10:00", "P030")], now=GREEN_TIP)
    assert reasons_of(out)["P004"] == ["sdhi_consecutive_limit"]
    assert "P004" not in product_ids(out)


def test_sdhi_count_resets_after_another_group():
    out = run([spray("2026-02-18 10:00", "P004"), spray("2026-02-25 10:00", "P001"), spray("2026-03-01 10:00", "P030")], now=GREEN_TIP)
    assert "sdhi_consecutive_limit" not in reasons_of(out).get("P004", [])


def test_one_sdhi_spray_is_not_a_limit():
    out = run([spray("2026-02-25 10:00", "P004")], now=GREEN_TIP)
    assert "sdhi_consecutive_limit" not in reasons_of(out).get("P004", [])


# ---------------------------------------------------------------------------------------------------------- waiting period
def test_waiting_period_longer_than_days_to_harvest_is_excluded():
    out = run(days_to_harvest=10)
    reasons = reasons_of(out)
    assert reasons["P011"] == reasons["P012"] == reasons["P022"] == ["waiting_period_exceeds_harvest"]
    assert "P010" not in reasons                                          # thiophanate-methyl: 3 days
    assert {p.waiting_period_days for p in out.products} <= {3}


@pytest.mark.parametrize(("days", "p012_excluded"), [(21, False), (20, True), (22, False)])
def test_waiting_period_boundary(days, p012_excluded):
    out = run(days_to_harvest=days)
    assert ("P012" in reasons_of(out)) is p012_excluded


def test_unknown_waiting_period_near_harvest_is_excluded():
    out = run(days_to_harvest=10)
    assert reasons_of(out)["P013"] == ["unknown_waiting_period_near_harvest"]
    assert reasons_of(out)["P014"] == ["unknown_waiting_period_near_harvest"]


@pytest.mark.parametrize(("days", "excluded"), [(30, True), (31, False)])
def test_unknown_waiting_period_policy_boundary_is_30_days(days, excluded):
    out = run([spray("2026-04-10 10:00", "P022")], days_to_harvest=days)
    assert ("P013" in reasons_of(out)) is excluded
    if not excluded:
        shown = [p for p in out.products if p.product_id == "P013"]
        assert not shown or any(w.code == "NO_WAITING_PERIOD" for w in shown[0].warnings)


def test_waiting_period_check_uses_the_calendar_when_no_override_is_given():
    # B2 Royal Delicious harvests on day 238; scab at pre-harvest (day 216 on) with rows P041 captan, P042 ziram (WP unknown)
    out = run(now="2026-08-05 10:00", days_to_harvest=None)
    assert any("calendar estimate" in line for line in out.trace)


# ---------------------------------------------------------------------------------------------------------- dodine and temperature
def _weather_with(now: str, *, temp: float | None, future_temp: float | None = None, daily_max: float | None = None):
    from app.domain.types import ForecastDay

    when = at(now)
    future = [weather_hour(when + timedelta(hours=h), temp=future_temp if future_temp is not None else 10.0) for h in range(1, 13)]
    snap = snapshot(when, hourly(when, 24, temp=10.0), future, temp_c=temp)
    if daily_max is not None:
        snap = snap.model_copy(update={"daily_forecast": [ForecastDay(day=when.date(), tmin_c=5, tmax_c=daily_max, rain_mm=0)]})
    return snap


def test_dodine_is_excluded_above_30_degrees():
    out = run(now=GREEN_TIP, weather=_weather_with(GREEN_TIP, temp=31.0))
    assert reasons_of(out)["P002"] == ["dodine_above_30c"]


def test_dodine_is_allowed_at_exactly_30_degrees():
    out = run(now=GREEN_TIP, weather=_weather_with(GREEN_TIP, temp=30.0))
    assert "P002" not in reasons_of(out)


def test_dodine_is_excluded_when_the_forecast_goes_above_30():
    assert "P002" in reasons_of(run(now=GREEN_TIP, weather=_weather_with(GREEN_TIP, temp=20.0, future_temp=33.0)))
    assert "P002" in reasons_of(run(now=GREEN_TIP, weather=_weather_with(GREEN_TIP, temp=20.0, daily_max=32.0)))


def test_dodine_is_not_excluded_without_weather():
    assert "P002" not in reasons_of(run(now=GREEN_TIP, weather=None))


def test_dodine_carries_its_restrictions_warning():
    engine = make_engine(lambda: {"P001", "P003", "P004"})                    # leave dodine as the only green-tip scab row
    out = run(now=GREEN_TIP, weather=_weather_with(GREEN_TIP, temp=15.0), engine=engine)
    assert product_ids(out) == ["P002"]
    assert "DODINE_RESTRICTIONS" in {w.code for w in out.products[0].warnings}


# ---------------------------------------------------------------------------------------------------------- captan and oil
def test_captan_is_excluded_within_15_days_of_an_oil_spray():
    out = run([spray("2026-02-23 10:00", "P051")], now=GREEN_TIP)             # horticultural mineral oil, 10 days earlier
    assert reasons_of(out)["P001"] == ["captan_within_15_days_of_oil"]


def test_captan_is_allowed_16_days_after_oil():
    out = run([spray("2026-02-17 10:00", "P051")], now=GREEN_TIP)
    assert "P001" not in reasons_of(out)


def test_oil_is_excluded_within_15_days_of_captan(widen_policy):
    widen_policy()
    out = make_engine().recommend(rule_input(
        now="2026-05-26 10:00", disease_id="PEST_apple_mites", confidence=0.9, history=[spray("2026-05-16 10:00", "P001")]))
    assert reasons_of(out)["P057"] == ["oil_within_15_days_of_captan"]
    assert "P057" not in product_ids(out)


# ---------------------------------------------------------------------------------------------------------- banned, off-label, disabled
def test_banned_active_is_never_a_candidate():
    engine = engine_with_products([
        fake_product("PX1", "Dimethoate", category="insecticide"),          # in banned_restricted.csv
        fake_product("PX2", "Safecide", ban="banned"),                      # master row flagged banned
    ])
    out = run(engine=engine)
    assert reasons_of(out)["PX1"] == ["banned"] and reasons_of(out)["PX2"] == ["banned"]
    assert not {"PX1", "PX2"} & set(product_ids(out))


def test_off_label_product_is_never_a_candidate():
    engine = engine_with_products([fake_product("PX3", "Fenpropathrin", category="insecticide")])
    out = run(engine=engine)
    assert reasons_of(out)["PX3"] == ["off_label"]


def test_products_whose_every_candidate_is_banned_or_off_label_end_with_the_expert():
    engine = engine_with_products([fake_product("PX4", "Pydiflumetofen + Difenoconazole", stage="walnut_plus_20d"),
                                   fake_product("PX5", "Dimethoate", stage="walnut_plus_20d")], disabled=None)
    out = engine.recommend(rule_input(now="2026-06-20 10:00", disease_id="Apple___Marssonina_blotch"))
    assert out.products == []


def test_admin_disabled_product_is_never_recommended_and_is_listed():
    out = run(engine=make_engine(lambda: {"P012"}))
    assert reasons_of(out)["P012"] == ["disabled_by_admin"]
    assert "P012" not in product_ids(out)


def test_disabled_set_is_read_on_every_call():
    state: set[str] = set()
    engine = make_engine(lambda: set(state))
    assert "P012" not in reasons_of(run(engine=engine))
    state.add("P012")
    assert reasons_of(run(engine=engine))["P012"] == ["disabled_by_admin"]
    state.clear()
    assert "P012" not in reasons_of(run(engine=engine))


def test_disabled_callable_may_return_none_or_empty():
    assert run(engine=make_engine(lambda: set())).excluded == []
    assert run(engine=make_engine(lambda: None)).excluded == []        # type: ignore[arg-type,return-value]


def test_disabling_the_whole_stage_leaves_the_expert_queue_with_the_reasons():
    out = run(engine=make_engine(lambda: set(PETAL_FALL_SCAB)))
    assert (out.status, out.route, out.reasons) == ("expert_review", "expert_queue", ["no_product_after_exclusions"])
    assert out.products == [] and {e.product_id for e in out.excluded} == PETAL_FALL_SCAB


def test_rows_not_usable_for_recommendation_are_ignored():
    from dataclasses import replace

    row = replace(fake_product("PX6", "Ghostcide", crop="Zzz"), usable=False)
    engine = engine_with_products([row])
    out = engine.recommend(rule_input(crop_id="Zzz"))
    assert out.status == "no_approved_data"
    assert "Zzz" not in engine.supported_crops()


# ---------------------------------------------------------------------------------------------------------- invariants
ALLOWED_REASONS = {
    "disabled_by_admin", "banned", "off_label", "same_active_as_last_spray", "same_frac_as_last_spray", "dmi_season_limit",
    "qoi_season_limit", "qoi_only_in_mixture", "sdhi_consecutive_limit", "waiting_period_exceeds_harvest",
    "unknown_waiting_period_near_harvest", "dodine_above_30c", "captan_within_15_days_of_oil", "oil_within_15_days_of_captan",
}


def test_excluded_reason_codes_are_from_the_documented_set():
    seen: set[str] = set()
    for days in (5, 20, 25, 100):
        for history in ([], [spray("2026-04-10 10:00", "P012")], _dmi_history(4), [spray("2026-04-10 10:00", "P009")]):
            seen.update(r for e in run(history, days_to_harvest=days).excluded for r in e.reasons)
    assert seen and seen <= ALLOWED_REASONS


def test_a_recommended_product_never_breaks_a_hard_rule(ref):
    """Across many histories and harvest horizons, nothing recommended may share an active or violate a limit."""
    for days in (3, 12, 21, 40, 120):
        for history in ([], [spray("2026-04-10 10:00", "P012")], _dmi_history(4), [spray("2026-04-10 10:00", "P022")],
                        [spray("2026-04-10 10:00", "P009")]):
            out = run(history, days_to_harvest=days)
            for choice in out.products:
                row = ref.products_by_id[choice.product_id]
                assert row.waiting_period_days is not None or days > 30
                assert row.waiting_period_days is None or row.waiting_period_days <= days
                assert row.ban_status != "banned"


def test_severity_of_advice_is_at_least_yellow():
    assert run().severity in (Severity.yellow, Severity.red)
