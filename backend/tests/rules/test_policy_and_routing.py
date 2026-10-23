"""Disease handling and the auto-advice policy: what may get medicine advice and what must go to the expert queue."""
from __future__ import annotations

import pytest

from app.rules.policy import AUTO_ADVICE, ENV_VAR, auto_advice_diseases, is_auto_advice

from .helpers import SCAB, dry_weather, engine_with_products, fake_product, farmer, rule_input, spray

SCAB_DATE = "2026-04-25 10:00"          # band B2: petal fall stage, inside the scab primary season


# ---------------------------------------------------------------------------------------------------------- policy module
def test_default_policy_is_apple_scab_only(ref):
    assert AUTO_ADVICE == {SCAB}
    assert auto_advice_diseases(ref.diseases) == {SCAB}
    assert is_auto_advice(SCAB, ref.diseases)
    assert not is_auto_advice("Apple___Marssonina_blotch", ref.diseases)


def test_env_list_extends_the_policy(ref, monkeypatch):
    monkeypatch.setenv(ENV_VAR, " Apple___Marssonina_blotch , Potato___Late_blight ,, ")
    assert auto_advice_diseases(ref.diseases) == {SCAB, "Apple___Marssonina_blotch", "Potato___Late_blight"}


def test_env_star_means_every_disease_with_chemical_control(ref, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "*")
    allowed = auto_advice_diseases(ref.diseases)
    assert SCAB in allowed and "Apple___Alternaria_leaf_spot" in allowed and "Potato___Late_blight" in allowed
    assert "Tomato___Tomato_Yellow_Leaf_Curl_Virus" not in allowed        # chemical_control == no
    assert "Apple___Cedar_apple_rust" not in allowed                      # expert_referral
    assert "Apple___healthy" not in allowed
    assert allowed == {SCAB} | {d.disease_id for d in ref.diseases.values() if d.chemical_control == "yes"}


def test_empty_env_changes_nothing(ref, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "  ")
    assert auto_advice_diseases(ref.diseases) == {SCAB}


# ---------------------------------------------------------------------------------------------------------- scab is the one auto case
def test_scab_in_season_gets_auto_advice(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE))
    assert (out.status, out.route) == ("advice", "auto_advice")
    assert out.products and out.stage == "petal_fall" and out.stage_source == "calendar"
    assert out.notes_query == {"crop": "Apple", "disease_id": SCAB, "stage": "petal_fall",
                               "product_ids": [p.product_id for p in out.products]}


@pytest.mark.parametrize(
    "disease_id",
    ["Apple___Marssonina_blotch", "Apple___Alternaria_leaf_spot", "Apple___Powdery_mildew", "Apple___Black_rot", "PEST_apple_mites"],
)
def test_other_apple_diseases_go_to_the_expert_queue(engine, disease_id):
    out = engine.recommend(rule_input(now="2026-07-05 08:00", disease_id=disease_id, confidence=0.99))
    assert (out.status, out.route) == ("expert_review", "expert_queue")
    assert out.products == [] and out.excluded == [] and out.timing is None
    assert "not_in_auto_advice_policy" in out.reasons
    assert out.non_chemical, "general non-chemical measures are always given"


def test_low_confidence_goes_to_the_expert_queue(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, confidence=0.64))
    assert (out.status, out.route, out.products) == ("expert_review", "expert_queue", [])
    assert out.reasons == ["low_confidence"]


def test_confidence_at_the_threshold_is_enough(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, confidence=0.65))
    assert out.status == "advice"


def test_unknown_confidence_defaults_to_zero_and_is_not_auto(engine):
    inp = rule_input(now=SCAB_DATE)
    out = engine.recommend(inp.model_copy(update={"disease_confidence": 0.0}))
    assert out.status == "expert_review"


def test_no_disease_goes_to_the_expert_queue(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id=None))
    assert (out.status, out.route, out.reasons) == ("expert_review", "expert_queue", ["disease_unknown"])
    assert out.products == [] and [m.en for m in out.non_chemical]


def test_disease_missing_from_the_catalogue_goes_to_the_expert_queue(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Apple___Made_up"))
    assert out.status == "expert_review" and out.reasons == ["disease_not_in_catalogue"]


def test_disease_of_another_crop_is_not_trusted(engine, widen_policy):
    widen_policy()
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Tomato___Early_blight"))
    assert out.status == "expert_review" and "disease_crop_mismatch" in out.reasons and out.products == []


def test_requires_expert_review_flag_blocks_auto_advice_even_when_policy_is_wide(engine, widen_policy):
    widen_policy()
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Apple___Apple_scab_rust", confidence=0.99))
    assert out.status == "expert_review" and "requires_expert_review" in out.reasons
    assert out.treat_as == SCAB and out.products == []
    assert any("urea" in m.en for m in out.non_chemical)      # 'See scab' resolves to the scab measures


def test_alias_brown_spot_is_treated_as_marssonina_but_stays_with_the_expert(engine, widen_policy):
    widen_policy()
    out = engine.recommend(rule_input(now="2026-07-05 08:00", disease_id="Apple___Brown_spot", confidence=0.99))
    assert out.treat_as == "Apple___Marssonina_blotch"
    assert (out.status, out.products) == ("expert_review", [])
    assert any("pruned" in m.en for m in out.non_chemical)


def test_expert_referral_disease(engine, widen_policy):
    widen_policy()
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Apple___Cedar_apple_rust", confidence=0.99))
    assert out.status == "expert_review" and "expert_referral" in out.reasons and out.products == []


def test_no_cure_disease_gets_a_no_cure_message_and_no_medicine(engine):
    out = engine.recommend(rule_input(crop_id="Tomato", disease_id="Tomato___Tomato_Yellow_Leaf_Curl_Virus", confidence=0.95,
                                      farmer_=farmer(crops=["Tomato"], primary_crop="Tomato", phenology_band="B1")))
    assert (out.status, out.route, out.products, out.excluded) == ("expert_review", "expert_queue", [], [])
    assert "no_chemical_cure" in out.reasons
    assert out.non_chemical[0].en.startswith("No cure") and "इलाज" in out.non_chemical[0].hi


def test_no_cure_message_is_added_when_the_catalogue_text_does_not_say_it(ref, engine):
    out = engine.recommend(rule_input(crop_id="Tomato", disease_id="Tomato___Tomato_mosaic_virus", confidence=0.95,
                                      farmer_=farmer(crops=["Tomato"], primary_crop="Tomato")))
    assert out.status == "expert_review"
    assert any("has no cure" in m.en for m in out.non_chemical)


def test_disease_without_catalogue_measures_gets_the_generic_measure(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Apple___Gray_spot", confidence=0.9))
    assert out.status == "expert_review"
    assert [m.en for m in out.non_chemical] == ["Remove badly affected leaves and fallen leaves from the field and put them in a compost pit."]


def test_expert_route_never_names_an_oil_spray(engine):
    """The catalogue's San Jose scale measure is 'mineral oil at half-inch green tip': a medicine, so never in expert measures."""
    out = engine.recommend(rule_input(now="2026-03-10 10:00", disease_id="PEST_apple_san_jose_scale", confidence=0.99))
    assert out.status == "expert_review" and out.products == []
    assert [m.en for m in out.non_chemical] == ["Remove badly affected leaves and fallen leaves from the field and put them in a compost pit."]


# ---------------------------------------------------------------------------------------------------------- healthy and no data
def test_healthy_class_is_not_a_disease(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Apple___healthy", confidence=0.9))
    assert (out.status, out.route, out.products, out.severity.value) == ("not_a_disease", "none", [], "green")
    assert out.reasons == ["healthy_class"]


def test_healthy_with_low_confidence_is_not_declared_healthy(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Apple___healthy", confidence=0.4))
    assert out.status == "expert_review" and out.reasons == ["low_confidence"]


@pytest.mark.parametrize("crop_id", ["Pear", "Banana", "Cherry", "Peach", "Orange", "", "Wheat"])
def test_crop_without_approved_data_gets_no_medicine(engine, crop_id, widen_policy):
    widen_policy()
    out = engine.recommend(rule_input(now=SCAB_DATE, crop_id=crop_id, disease_id=SCAB, confidence=0.99))
    assert (out.status, out.route) == ("no_approved_data", "none")
    assert out.products == [] and out.timing is None and out.reasons == ["no_approved_data_for_crop"]


def test_no_data_crop_with_known_disease_still_gets_non_chemical_text(engine):
    out = engine.recommend(rule_input(crop_id="Peach", disease_id="Peach___Bacterial_spot", confidence=0.9))
    assert out.status == "no_approved_data" and out.products == []


def test_crop_id_is_matched_case_insensitively(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, crop_id="apple"))
    assert out.status == "advice" and out.crop_id == "Apple"


def test_crop_whose_rows_are_all_disabled_has_no_approved_data():
    from app.rules.data import load_reference

    from .helpers import DATA_DIR, make_engine

    ref = load_reference(DATA_DIR)
    grape_ids = {p.product_id for p in ref.products if p.crop == "Grape"}
    engine = make_engine(lambda: set(grape_ids))
    out = engine.recommend(rule_input(crop_id="Grape", disease_id="Grape___Leaf_blight_(Isariopsis_Leaf_Spot)", confidence=0.9))
    assert out.status == "no_approved_data"
    assert "Grape" not in engine.supported_crops()


# ---------------------------------------------------------------------------------------------------------- safety sweep over the catalogue
def _farmer_for(crop: str):
    return farmer(crops=[crop], primary_crop=crop)


def test_default_policy_never_gives_medicine_for_anything_but_scab(engine, ref):
    """Whatever the disease and however confident, only apple scab may come back with products."""
    for disease in ref.diseases.values():
        crop = ref.canonical_crop(disease.crop) or disease.crop
        out = engine.recommend(rule_input(now=SCAB_DATE, crop_id=crop, disease_id=disease.disease_id, confidence=0.99,
                                          farmer_=_farmer_for(crop), weather=dry_weather(SCAB_DATE)))
        if disease.disease_id == SCAB:
            assert out.status == "advice"
        else:
            assert out.products == [], disease.disease_id
            assert out.route != "auto_advice", disease.disease_id


def test_wide_policy_only_recommends_approved_rows_that_target_the_disease(engine, ref, widen_policy):
    widen_policy()
    for disease in ref.diseases.values():
        crop = ref.canonical_crop(disease.crop) or disease.crop
        out = engine.recommend(rule_input(now="2026-06-20 10:00", crop_id=crop, disease_id=disease.disease_id, confidence=0.99,
                                          farmer_=_farmer_for(crop), weather=dry_weather("2026-06-20 10:00")))
        for choice in out.products:
            row = ref.products_by_id[choice.product_id]
            assert row.usable and row.crop == crop
            assert disease.disease_id in row.targets or (disease.treat_as and disease.treat_as in row.targets)
        if disease.requires_expert_review or disease.chemical_control != "yes" or disease.kind == "healthy":
            assert out.products == [], disease.disease_id


def test_banned_history_does_not_break_the_policy(engine):
    out = engine.recommend(rule_input(now=SCAB_DATE, history=[spray("2026-04-10 10:00", None, active_ingredient="Dimethoate")]))
    assert out.status == "advice"


def test_extra_product_rows_do_not_widen_the_policy(widen_policy):
    engine = engine_with_products([fake_product("PX1", "Fakecide", targets=("Apple___Powdery_mildew",))])
    out = engine.recommend(rule_input(now=SCAB_DATE, disease_id="Apple___Powdery_mildew"))
    assert out.status == "expert_review" and out.products == []


# ---------------------------------------------------------------------------------------------------------- policy from a setting
def test_configured_setting_extends_the_policy_like_the_env_var(ref):
    assert auto_advice_diseases(ref.diseases, "Apple___Marssonina_blotch") == {SCAB, "Apple___Marssonina_blotch"}
    assert "Potato___Late_blight" in auto_advice_diseases(ref.diseases, "*")
    assert is_auto_advice("Apple___Alternaria_leaf_spot", ref.diseases, "Apple___Alternaria_leaf_spot")


def test_env_var_and_setting_are_both_added(ref, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "Potato___Late_blight")
    assert auto_advice_diseases(ref.diseases, "Apple___Marssonina_blotch") == {SCAB, "Potato___Late_blight", "Apple___Marssonina_blotch"}


def test_engine_reads_the_optional_setting():
    from types import SimpleNamespace

    from app.rules.engine import build_rules_engine

    from .helpers import DATA_DIR

    engine = build_rules_engine(SimpleNamespace(data_dir=DATA_DIR, rules_auto_advice_diseases="Apple___Marssonina_blotch"))  # type: ignore[arg-type]
    out = engine.recommend(rule_input(now="2026-06-20 10:00", disease_id="Apple___Marssonina_blotch", confidence=0.9))
    assert out.status == "advice" and out.products
    plain = build_rules_engine(SimpleNamespace(data_dir=DATA_DIR))  # type: ignore[arg-type]
    assert plain.recommend(rule_input(now="2026-06-20 10:00", disease_id="Apple___Marssonina_blotch", confidence=0.9)).status == "expert_review"
