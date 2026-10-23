"""Growth stage, scab primary season, harvest estimate and spray season from the (estimated) stage calendar."""
from __future__ import annotations

import pytest

from app.rules import stage as st

from .helpers import SCAB, at, engine_with_products, fake_product, farmer, rule_input


def _stage(ref, band: str, when: str, cultivar: str = "Royal_Delicious") -> str:
    return st.current_stage(ref.bands[band], st.day_of_year(at(when)), cultivar)


@pytest.mark.parametrize(
    ("band", "when", "expected"),
    [
        ("B1", "2026-01-15 10:00", "dormant"),
        ("B1", "2026-02-15 10:00", "dormant"),           # day 46; silver tip is day 47
        ("B1", "2026-02-16 10:00", "silver_tip"),
        ("B1", "2026-04-14 10:00", "petal_fall"),
        ("B3", "2026-05-12 16:00", "petal_fall"),        # scenario S1
        ("B3", "2026-05-14 08:00", "fruit_set"),
        ("B2", "2026-03-30 20:00", "tight_cluster"),
        ("B4", "2026-04-29 08:00", "full_bloom"),
        ("B2", "2026-07-05 08:00", "walnut_plus_40d"),
    ],
)
def test_stage_from_band_and_date(ref, band, when, expected):
    assert _stage(ref, band, when) == expected


def test_stage_reaches_each_calendar_row_on_its_typical_day(ref):
    for band in ref.bands.values():
        for stage_id, doy in band.stages:
            assert st.current_stage(band, doy, "Royal_Delicious") == stage_id
            assert st.current_stage(band, doy - 1, "Royal_Delicious") != stage_id


def test_harvest_stages_follow_the_cultivar(ref):
    b2 = ref.bands["B2"]
    assert st.current_stage(b2, 216, "Royal_Delicious") == "pre_harvest"
    assert st.current_stage(b2, 238, "Royal_Delicious") == "harvest"
    assert st.current_stage(b2, 245, "Royal_Delicious") == "post_harvest"
    assert st.current_stage(b2, 216, "Granny_Smith") == "walnut_plus_40d"       # Granny Smith ripens much later
    assert st.current_stage(b2, 243, "Granny_Smith") == "pre_harvest"
    assert st.current_stage(b2, 216, "Unknown_Variety") == "pre_harvest"        # falls back to Royal Delicious


def test_cultivar_defaults_to_royal_delicious(ref):
    band = ref.bands["B2"]
    assert st.cultivar_for(band, farmer(primary_variety="Gala")) == "Gala"
    assert st.cultivar_for(band, farmer(primary_variety=None)) == "Royal_Delicious"
    assert st.cultivar_for(band, farmer(primary_variety="Golden Delicious")) == "Golden_Delicious"
    assert st.cultivar_for(band, farmer(primary_variety="Mystery")) == "Royal_Delicious"


def test_band_from_phenology_band_or_elevation(ref):
    assert st.band_for(ref, farmer(phenology_band="b3")).band_id == "B3"
    assert st.band_for(ref, farmer(phenology_band=None, elevation_m=1200)).band_id == "B1"
    assert st.band_for(ref, farmer(phenology_band=None, elevation_m=1500)).band_id == "B2"
    assert st.band_for(ref, farmer(phenology_band=None, elevation_m=2400)).band_id == "B3"
    assert st.band_for(ref, farmer(phenology_band=None, elevation_m=3000)).band_id == "B4"
    assert st.band_for(ref, farmer(phenology_band=None, elevation_m=4000)).band_id == "B4"
    assert st.band_for(ref, farmer(phenology_band=None, elevation_m=None)) is None
    assert st.band_for(ref, farmer(phenology_band="B9", elevation_m=1800)).band_id == "B2"   # bad band: use the elevation


def test_days_to_harvest_estimate(ref):
    band = ref.bands["B3"]
    assert st.days_to_harvest(band, "Royal_Delicious", at("2026-05-12 16:00")) == 252 - 132
    assert st.days_to_harvest(band, "Royal_Delicious", at("2026-09-09 09:00")) == 0          # day 252 itself
    assert st.days_to_harvest(band, "Royal_Delicious", at("2026-10-17 09:00")) == 365 - 290 + 252   # next season's harvest


def test_days_to_harvest_override_wins(engine):
    out = engine.recommend(rule_input(now="2026-04-25 10:00", days_to_harvest=5))
    assert any("(given)" in line for line in out.trace)
    assert all(p.waiting_period_days is None or p.waiting_period_days <= 5 for p in out.products) or out.status == "expert_review"


def test_scab_primary_season_window_has_a_week_of_slack(ref):
    b3 = ref.bands["B3"]                                    # green tip day 76, petal fall day 126
    assert st.scab_season_window(b3) == (76 - 7, 126 + 21 + 7)
    for day, expected in [(68, False), (69, True), (132, True), (154, True), (155, False)]:
        assert (st.scab_season_window(b3)[0] <= day <= st.scab_season_window(b3)[1]) is expected


def test_scab_season_active_by_date(ref):
    b2 = ref.bands["B2"]
    assert st.scab_season_active(ref, b2, at("2026-04-25 10:00"))
    assert not st.scab_season_active(ref, b2, at("2026-07-05 08:00"))
    assert not st.scab_season_active(ref, b2, at("2026-02-01 08:00"))
    assert not st.scab_season_active(ref, b2, at("2026-10-17 09:00"))


def test_unknown_band_uses_the_widest_window(ref):
    start, end = st.any_band_scab_window(ref)
    assert start == 54 - 7 and end == 131 + 28          # B1 green tip day 54; B4 petal fall day 131
    assert st.scab_season_active(ref, None, at("2026-05-30 10:00"))
    assert not st.scab_season_active(ref, None, at("2026-07-30 10:00"))


def test_leaf_spot_season_starts_on_1_june(ref):
    assert not st.leaf_spot_season_active(ref, at("2026-05-31 23:00"))
    assert st.leaf_spot_season_active(ref, at("2026-06-01 00:00"))
    assert st.leaf_spot_season_active(ref, at("2026-09-01 00:00"))


def test_spray_season(ref):
    f = farmer(phenology_band="B4")
    assert st.in_spray_season(ref, f, "Apple", at("2026-10-17 09:00"))        # B4 post harvest is day 269, +30 grace
    assert not st.in_spray_season(ref, f, "Apple", at("2026-12-10 09:00"))
    assert not st.in_spray_season(ref, f, "Apple", at("2026-01-10 09:00"))
    assert st.in_spray_season(ref, f, "Tomato", at("2026-07-10 09:00"))
    assert not st.in_spray_season(ref, f, "Tomato", at("2026-12-10 09:00"))
    assert st.in_spray_season(ref, farmer(phenology_band=None, elevation_m=None), "Apple", at("2026-06-10 09:00"))


# ---------------------------------------------------------------------------------------------------------- stage in the engine
def test_scab_season_check_routes_to_the_expert_outside_the_season(engine):
    out = engine.recommend(rule_input(now="2026-07-05 08:00"))
    assert (out.status, out.route, out.reasons, out.products) == ("expert_review", "expert_queue", ["out_of_season_for_disease"], [])
    assert out.stage == "walnut_plus_40d"
    assert any("out of season" in line for line in out.trace)


def test_scab_just_inside_and_just_outside_the_season_edge(engine):
    inside = engine.recommend(rule_input(now="2026-05-20 10:00"))          # B2: season ends day 112 + 28 = 140 (May 20)
    outside = engine.recommend(rule_input(now="2026-05-21 10:00"))
    assert inside.status == "advice"
    assert outside.reasons == ["out_of_season_for_disease"]


def test_apple_without_band_or_elevation_needs_more_info(engine):
    out = engine.recommend(rule_input(farmer_=farmer(phenology_band=None, elevation_m=None)))
    assert (out.status, out.route, out.reasons, out.products) == ("needs_more_info", "expert_queue", ["phenology_band_unknown"], [])
    assert out.stage is None


def test_apple_band_can_come_from_elevation(engine):
    out = engine.recommend(rule_input(farmer_=farmer(phenology_band=None, elevation_m=1800)))
    assert out.status == "advice" and out.stage == "petal_fall"


def test_non_apple_crops_have_no_calendar_stage(engine, widen_policy):
    widen_policy()
    out = engine.recommend(rule_input(crop_id="Potato", disease_id="Potato___Late_blight", farmer_=farmer(crops=["Potato"], primary_crop="Potato")))
    assert out.status == "advice" and out.stage is None and out.stage_source is None
    assert out.notes_query["stage"] is None


def test_stage_fallback_to_the_latest_earlier_stage_with_rows(engine):
    # B2, 2026-05-02 = day 122: fruit_set (day 120) has no scab row; petal_fall (day 112) does.
    out = engine.recommend(rule_input(now="2026-05-02 10:00"))
    assert out.stage == "fruit_set"
    assert out.status == "advice" and {p.stage for p in out.products} == {"petal_fall"}
    assert any("fell back to the latest earlier stage" in line and "petal_fall" in line for line in out.trace)


def test_stage_with_exact_rows_does_not_fall_back(engine):
    out = engine.recommend(rule_input(now="2026-04-25 10:00"))
    assert {p.stage for p in out.products} == {"petal_fall"}
    assert not any("fell back" in line for line in out.trace)


def test_tight_cluster_falls_back_to_green_tip(engine):
    out = engine.recommend(rule_input(now="2026-03-24 10:00"))             # B2 day 83: tight cluster (day 82)
    assert out.stage == "tight_cluster"
    assert {p.stage for p in out.products} == {"green_tip"}


def test_no_rows_at_or_before_the_stage_goes_to_the_expert(engine):
    out = engine.recommend(rule_input(now="2026-02-26 10:00"))             # B2 day 57: silver tip, before any scab row
    assert out.stage == "silver_tip"
    assert (out.status, out.reasons) == ("expert_review", ["no_product_for_disease_and_stage"])


def test_stage_is_computed_from_the_year_of_now(engine):
    out = engine.recommend(rule_input(now="2027-04-25 10:00"))
    assert out.stage == "petal_fall"


def test_a_row_for_a_later_stage_is_never_used_as_a_fallback():
    extra = engine_with_products([fake_product("PX2", "Latecide", stage="pre_harvest", targets=("Apple___Powdery_mildew",))])
    # scab rows exist only from green tip on; a later-stage row must not be pulled back to an earlier stage
    out = extra.recommend(rule_input(now="2026-02-26 10:00", disease_id=SCAB))
    assert out.products == []
