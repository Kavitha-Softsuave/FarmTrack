"""Ranking of the surviving candidates: infection state, HP brands, evidence, warnings; top 3; brand examples."""
from __future__ import annotations

from dataclasses import replace

from app.rules.selection import MAX_BRANDS, brand_examples

from .helpers import (
    SCAB,
    dry_weather,
    engine_with_products,
    fake_product,
    make_engine,
    rule_input,
    scab_weather,
    spray,
)

NOW = "2026-04-25 10:00"


def run(*, weather=None, engine=None, history=None, **kw):
    return (engine or make_engine()).recommend(rule_input(now=NOW, weather=weather, history=history or [], **kw))


def test_systemic_products_come_first_while_an_infection_period_is_active():
    out = run(weather=scab_weather(NOW, wet_hours=12))
    assert {r.id: r.level.value for r in out.risks}["scab_infection_risk"] == "red"
    assert [p.behaviour for p in out.products] == ["systemic"] * 3
    assert all("works inside the leaf" in p.rank_reason for p in out.products)


def test_protectants_come_first_without_an_infection_period():
    out = run(weather=dry_weather(NOW))
    assert out.products[0].product_id == "P022"                    # metiram: the only contact product at petal fall that is not banned-soon
    assert out.products[0].behaviour == "contact"
    assert "cover spray" in out.products[0].rank_reason


def test_without_weather_the_protectant_preference_applies():
    assert run(weather=None).products[0].behaviour == "contact"


def test_a_yellow_scab_risk_is_not_an_active_infection():
    out = run(weather=scab_weather(NOW, wet_hours=8))               # 8 of 11 hours needed at 10 C: building, not reached
    assert {r.id: r.level.value for r in out.risks}["scab_infection_risk"] == "yellow"
    assert out.products[0].behaviour == "contact"


def test_proposed_ban_products_are_allowed_but_ranked_lower_and_flagged():
    out = run(weather=dry_weather(NOW))
    assert all(p.ban_status == "registered" for p in out.products), "registered products fill the top 3 first"
    only_banned_soon = make_engine(lambda: {"P011", "P012", "P013", "P014", "P022"})
    out = run(weather=dry_weather(NOW), engine=only_banned_soon)
    assert out.status == "advice" and {p.product_id for p in out.products} == {"P009", "P010", "P020"}
    for choice in out.products:
        assert "PROPOSED_BAN" in {w.code for w in choice.warnings}
        assert choice.ban_status == "proposed_ban_2020_draft_still_registered"
        assert "may be banned" in choice.rank_reason


def test_products_with_a_known_waiting_period_beat_equal_ones_without():
    """P013 (waiting period unknown) comes after P011 and P012 (known) although all three are systemic."""
    out = run(weather=scab_weather(NOW, wet_hours=12))
    assert [p.product_id for p in out.products] == ["P011", "P012", "P013"]


def test_hp_evaluated_brands_are_preferred_over_equal_products_without():
    plain = fake_product("PX7", "Plaincide", code="M03")
    branded = replace(fake_product("PX8", "Brandcide", code="M03"), hp_brand_group="B15", hp_brands=("Cuman L",))
    engine = engine_with_products([plain, branded], disabled=lambda: {p for p in
                                  ("P009", "P010", "P011", "P012", "P013", "P014", "P020", "P022")})
    out = run(weather=dry_weather(NOW), engine=engine)
    assert [p.product_id for p in out.products] == ["PX8", "PX7"]


def test_verified_evidence_beats_inferred():
    verified = fake_product("PX9", "Verifiedcide", code="M03")
    inferred = replace(fake_product("PX10", "Inferredcide", code="M03"), confidence="I")
    engine = engine_with_products([inferred, verified], disabled=lambda: {"P009", "P010", "P011", "P012", "P013", "P014", "P020", "P022"})
    out = run(weather=dry_weather(NOW), engine=engine)
    assert [p.product_id for p in out.products] == ["PX9", "PX10"]


def test_at_most_three_products_and_one_row_per_active_ingredient():
    twin = fake_product("PX11", "Metiram", code="M03", wp=21)
    out = run(weather=dry_weather(NOW), engine=engine_with_products([twin]))
    assert len(out.products) <= 3
    assert [p.active_ingredient for p in out.products].count("Metiram") == 1


def test_rank_reason_follows_the_input_language():
    en = run(weather=dry_weather(NOW), language="en").products[0].rank_reason
    hi = run(weather=dry_weather(NOW), language="hi").products[0].rank_reason
    assert en.isascii() and not hi.isascii() and "हिमाचल" in hi


def test_brand_examples_list_hp_evaluated_brands_first_and_at_most_four(ref):
    for product in ref.products:
        brands = brand_examples(ref, product)
        assert len(brands) <= MAX_BRANDS
        assert len({b.lower() for b in brands}) == len(brands)
        if product.hp_brands:
            assert brands[0] == product.hp_brands[0]
        elif product.brand_example:
            assert brands == [product.brand_example] or brands[0] in ref.brands_by_group.get(product.hp_brand_group or "", ())


def test_product_choice_carries_the_master_data(ref):
    out = run(weather=dry_weather(NOW))
    choice = out.products[0]
    row = ref.products_by_id[choice.product_id]
    assert (choice.active_ingredient, choice.dose_min, choice.dose_max, choice.dose_unit, choice.waiting_period_days) == (
        row.active_ingredient, row.dose_min, row.dose_max, row.dose_unit, row.waiting_period_days)
    assert choice.frac_irac_code == "M03" and choice.crop == "Apple" and choice.stage == "petal_fall"
    assert choice.source_ref and choice.active_ingredient_hi and choice.brand_examples
    assert "DOSE_PER_200L" in {w.code for w in choice.warnings}


def test_ranking_is_deterministic():
    first = [p.product_id for p in run(weather=dry_weather(NOW), history=[spray("2026-04-10 10:00", "P009")]).products]
    second = [p.product_id for p in run(weather=dry_weather(NOW), history=[spray("2026-04-10 10:00", "P009")]).products]
    assert first == second


def test_scab_label_is_used_in_the_notes_query():
    out = run(weather=dry_weather(NOW))
    assert out.notes_query["disease_id"] == SCAB and out.notes_query["product_ids"] == [p.product_id for p in out.products]
