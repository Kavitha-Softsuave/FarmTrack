"""RULES_SEASON_CHECK: off in development (owner decision 22 Oct 2026), on = the production behaviour the other rule tests pin."""
from __future__ import annotations

import pytest

from app.config import Settings

from .helpers import SCAB, make_engine, rule_input

MARSSONINA = "Apple___Marssonina_blotch"
ALTERNARIA = "Apple___Alternaria_leaf_spot"


@pytest.fixture
def season_off(monkeypatch, widen_policy):
    widen_policy()
    monkeypatch.setenv("RULES_SEASON_CHECK", "false")
    return make_engine()


@pytest.fixture
def season_on(monkeypatch, widen_policy):
    widen_policy()
    monkeypatch.setenv("RULES_SEASON_CHECK", "true")
    return make_engine()


def test_the_product_default_is_off(monkeypatch):
    monkeypatch.delenv("RULES_SEASON_CHECK", raising=False)
    assert Settings(_env_file=None).rules_season_check is False


@pytest.mark.parametrize("disease", [SCAB, MARSSONINA, ALTERNARIA])
@pytest.mark.parametrize("when", ["2026-03-01 10:00", "2026-05-12 08:00", "2026-07-05 08:00", "2026-10-22 11:00", "2026-12-20 09:00"])
def test_with_the_check_off_the_date_never_stops_advice(season_off, disease, when):
    out = season_off.recommend(rule_input(now=when, disease_id=disease, confidence=0.9))
    assert (out.status, out.route) == ("advice", "auto_advice"), (disease, when, out.reasons)
    assert out.products and "out_of_season_for_disease" not in out.reasons


def test_with_the_check_on_marssonina_is_still_out_of_season_in_may(season_on):
    out = season_on.recommend(rule_input(now="2026-05-12 08:00", disease_id=MARSSONINA, confidence=0.9))
    assert out.status == "expert_review" and out.reasons == ["out_of_season_for_disease"]


def test_with_the_check_on_scab_is_still_out_of_season_in_october(season_on):
    out = season_on.recommend(rule_input(now="2026-10-22 11:00", disease_id=SCAB, confidence=0.9))
    assert out.status == "expert_review"


@pytest.mark.parametrize("disease", ["Apple___Root_rot_collar_rot", "Apple___Brown_spot", "Apple___Black_rot"])
def test_the_other_guards_do_not_depend_on_the_season_switch(season_off, disease):
    out = season_off.recommend(rule_input(now="2026-07-05 08:00", disease_id=disease, confidence=0.95))
    assert out.status == "expert_review" and out.products == [] and "requires_expert_review" in out.reasons


def test_low_confidence_still_goes_to_the_safe_answer_with_the_check_off(season_off):
    out = season_off.recommend(rule_input(now="2026-07-05 08:00", disease_id=MARSSONINA, confidence=0.5))
    assert out.status == "expert_review" and out.products == [] and "low_confidence" in out.reasons
