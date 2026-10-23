"""Spray diary: which medicine an entry is about (advice default, catalogue check, typed names) with the REAL rules engine."""
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.clock import IST
from app.db.models import FarmerRow, SprayLogRow
from app.db.session import session_scope
from app.integrations.reference import harvest_day_of_year
from app.rules.engine import build_rules_engine
from tests import fakes
from tests.fakes import NOW, rule_output, sample_product
from tests.imaging import photo_files


@pytest.fixture
def real_rules(fake_container, api_settings):
    """The rules engine on the real reference data instead of the fake; everything else stays fake."""
    fake_container.rules = build_rules_engine(api_settings)
    return fake_container


def log_spray(client, auth, **body):
    return client.post("/v1/spray-logs", json={"crop_id": "Apple", **body}, headers=auth)


def codes(response) -> list[str]:
    return [w["code"] for w in response.json()["warnings"]]


def two_product_advice(fake_container):
    fake_container.rules.output = rule_output(products=[
        sample_product(),
        sample_product(product_id="P011", active_ingredient="Hexaconazole", active_ingredient_hi="हेक्साकोनाज़ोल", frac_irac_code="3")])


def scan_advice_id(client, auth):
    return client.post("/v1/scans", files=photo_files(1), headers=auth).json()["advice"]["id"]


# ------------------------------------------------------------------------------------------------ 1. the 'I sprayed this' tick
def test_the_tick_with_only_an_advice_id_logs_the_first_product(api_client, auth, fake_container):
    two_product_advice(fake_container)
    advice_id = scan_advice_id(api_client, auth)
    response = log_spray(api_client, auth, advice_id=advice_id)
    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "P012" and body["product_name"] == "Myclobutanil" and body["advice_id"] == advice_id
    assert fake_container.zoho.spray_writes[0][1].product_id == "P012"


def test_the_first_product_is_the_one_read_aloud_even_when_the_advice_lists_several(api_client, auth, fake_container):
    two_product_advice(fake_container)
    advice = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()["advice"]
    assert [p["product_id"] for p in advice["products"]] == ["P012", "P011"]
    assert log_spray(api_client, auth, advice_id=advice["id"]).json()["product_id"] == advice["products"][0]["product_id"]


def test_another_product_of_the_same_advice_can_be_chosen(api_client, auth, fake_container):
    two_product_advice(fake_container)
    response = log_spray(api_client, auth, advice_id=scan_advice_id(api_client, auth), product_id="P011")
    assert response.json()["product_id"] == "P011" and response.json()["product_name"] == "Hexaconazole"


def test_an_advice_without_products_still_needs_a_medicine(api_client, auth, fake_container):
    fake_container.rules.output = rule_output("expert_review")                        # the expert route carries no products
    advice_id = scan_advice_id(api_client, auth)
    response = log_spray(api_client, auth, advice_id=advice_id)
    assert response.status_code == 422 and response.json()["code"] == "spray_needs_product"
    assert log_spray(api_client, auth, advice_id=advice_id, free_text="Mancozeb").status_code == 200   # a typed name is fine


def test_a_product_that_is_not_in_the_advice_must_be_in_the_catalogue(api_client, auth, fake_container):
    advice_id = scan_advice_id(api_client, auth)                                      # advice for P012 only
    assert log_spray(api_client, auth, advice_id=advice_id, product_id="P011").json()["product_id"] == "P011"
    refused = log_spray(api_client, auth, advice_id=advice_id, product_id="P999")
    assert refused.status_code == 422 and refused.json()["code"] == "unknown_product"
    assert log_spray(api_client, auth, product_id="ZZZ").status_code == 422
    with session_scope() as db:
        assert [r.product_id for r in db.scalars(select(SprayLogRow))] == ["P011"]


def test_an_unknown_product_id_with_a_typed_name_falls_back_to_the_name(api_client, auth):
    body = log_spray(api_client, auth, product_id="P999", free_text="Local mix").json()
    assert body["product_id"] is None and body["product_name"] == "Local mix"


def test_the_advice_must_belong_to_the_caller_even_without_a_product(api_client, auth, login):
    advice_id = scan_advice_id(api_client, auth)
    other = login("+910000000002")
    for body in ({"advice_id": advice_id}, {"advice_id": advice_id, "free_text": "x"}):
        response = log_spray(api_client, other, **body)
        assert response.status_code == 404 and response.json()["code"] == "advice_not_found"
    with session_scope() as db:
        assert db.scalars(select(SprayLogRow)).all() == []


# ------------------------------------------------------------------------------------------------ 2. typed names
def test_mancozeb_typed_in_the_diary_runs_the_spray_checks(api_client, auth, real_rules):
    response = log_spray(api_client, auth, free_text="mancozeb")
    body = response.json()
    assert body["product_id"] == "P005" and body["product_name"] == "Mancozeb"
    assert codes(response) == ["PROPOSED_BAN"]                                         # impossible while the name was not resolved
    assert body["warnings"][0]["level"] == "yellow"
    record = real_rules.zoho.spray_writes[0][1]
    assert record.product_id == "P005" and record.frac_irac_code == "M03" and record.category == "fungicide"
    with session_scope() as db:
        row = db.scalars(select(SprayLogRow)).one()
        assert row.product_id == "P005" and row.free_text == "mancozeb"                # what was typed stays on the row


@pytest.mark.parametrize("typed", ["MANCOZEB", "  Mancozeb 75% WP ", "mancozeb-75wp", "Mancozeb.", "मैन्कोज़ेब", "Dithane M-45", "dithane m45",
                                   "P005", "p005"])
def test_typed_names_match_ignoring_case_punctuation_and_formulation(api_client, auth, real_rules, typed):
    body = log_spray(api_client, auth, free_text=typed).json()
    assert body["product_id"] == "P005", typed
    assert "PRODUCT_NOT_RECOGNISED" not in [w["code"] for w in body["warnings"]]


def test_a_brand_name_keeps_what_the_farmer_typed(api_client, auth, real_rules):
    body = log_spray(api_client, auth, free_text="Bavistin 50 WP").json()
    assert body["product_id"] == "P009" and body["product_name"] == "Bavistin 50 WP (Carbendazim)"
    assert real_rules.zoho.spray_writes[0][1].trade_name == "Bavistin 50 WP"


def test_a_mixture_typed_in_any_order_matches_its_row(api_client, auth, real_rules):
    assert log_spray(api_client, auth, free_text="Carbendazim + Mancozeb").json()["product_id"] == "P020"
    assert log_spray(api_client, auth, free_text="mancozeb and carbendazim").json()["product_id"] == "P020"


def test_a_name_that_fits_several_products_is_not_guessed(api_client, auth, real_rules):
    response = log_spray(api_client, auth, free_text="Ziram")                          # three rows that disagree on the waiting period
    body = response.json()
    assert body["product_id"] is None and body["product_name"] == "Ziram"
    assert "PRODUCT_NOT_RECOGNISED" in codes(response)


def test_an_unknown_name_is_saved_with_a_soft_warning_in_english_and_hindi(api_client, auth, real_rules):
    response = log_spray(api_client, auth, free_text="Local mix")
    body = response.json()
    assert response.status_code == 200 and body["product_id"] is None and body["product_name"] == "Local mix"
    warning = next(w for w in body["warnings"] if w["code"] == "PRODUCT_NOT_RECOGNISED")
    assert warning["level"] == "yellow"
    assert "not in our list" in warning["text"]["en"] and warning["text"]["hi"].startswith("यह दवा हमारी सूची में नहीं")
    assert not any(ch.isdigit() for ch in warning["text"]["en"] + warning["text"]["hi"])      # readable aloud
    assert body["spoken"]["text"]["en"].endswith(warning["text"]["en"])
    assert real_rules.zoho.spray_writes[0][1].trade_name == "Local mix"                       # still saved and synced


def test_text_that_merely_contains_a_known_name_is_not_matched(api_client, auth, real_rules):
    body = log_spray(api_client, auth, free_text="Mancozeb and some other stuff").json()
    assert body["product_id"] is None
    assert "PRODUCT_NOT_RECOGNISED" in [w["code"] for w in body["warnings"]]


def test_a_nutrient_is_not_reported_as_an_unrecognised_medicine(api_client, auth, real_rules):
    body = log_spray(api_client, auth, free_text="Zinc and boron mix").json()
    assert body["product_id"] is None and "PRODUCT_NOT_RECOGNISED" not in [w["code"] for w in body["warnings"]]


def test_a_name_is_matched_for_the_crop_of_the_entry(api_client, auth, real_rules):
    assert log_spray(api_client, auth, crop_id="Tomato", free_text="mancozeb").json()["product_id"] == "P070"
    peach = log_spray(api_client, auth, crop_id="Peach", free_text="mancozeb").json()              # no approved list for peach
    assert peach["product_id"] is None and "PRODUCT_NOT_RECOGNISED" in [w["code"] for w in peach["warnings"]]


def test_the_same_chemical_twice_is_flagged_even_under_another_name(api_client, auth, real_rules):
    log_spray(api_client, auth, free_text="Dithane M-45", sprayed_at=(NOW - timedelta(days=7)).isoformat())
    response = log_spray(api_client, auth, free_text="mancozeb")
    warnings = response.json()["warnings"]
    assert "ROTATION_LIMIT" in codes(response)
    assert any(w["code"] == "ROTATION_LIMIT" and "Mancozeb" in w["text"]["en"] for w in warnings)


def test_a_waiting_period_longer_than_the_time_to_harvest_is_a_red_warning(api_client, auth, real_rules):
    with session_scope() as db:
        farmer = db.get(FarmerRow, "F001")
        doy = harvest_day_of_year(real_rules.settings.data_dir, farmer.phenology_band, farmer.primary_variety)
    assert doy is not None
    harvest = datetime.combine(date(2026, 1, 1) + timedelta(days=doy - 1), time.min, tzinfo=IST)
    response = log_spray(api_client, auth, free_text="Dodine 65 WP", sprayed_at=(harvest - timedelta(days=5)).isoformat())
    assert response.json()["product_id"] in {"P002", "P025"}
    assert "WAITING_PERIOD_EXCEEDS_HARVEST" in codes(response)
    assert next(w for w in response.json()["warnings"] if w["code"] == "WAITING_PERIOD_EXCEEDS_HARVEST")["level"] == "red"


def test_myclobutanil_then_mancozeb_on_the_same_day(api_client, auth, real_rules):
    """Two DIFFERENT fungicides logged on one day. The rules only warn about the proposed ban of mancozeb: they have no rule
    for two different chemicals on the same day (see docs/design-notes/backendfix.md, a question for the agronomist)."""
    first = log_spray(api_client, auth, product_id="P012")
    assert first.json()["warnings"] == []
    second = log_spray(api_client, auth, free_text="mancozeb")
    assert second.json()["product_id"] == "P005"
    assert codes(second) == ["PROPOSED_BAN"]


def test_rules_that_fail_leave_the_typed_entry_saved(api_client, auth, fake_container):
    def boom(*_args):
        raise RuntimeError("rules down")

    fake_container.rules = fakes.FakeRules()
    fake_container.rules.check_spray = boom
    body = log_spray(api_client, auth, free_text="Local mix").json()
    assert [w["code"] for w in body["warnings"]] == ["PRODUCT_NOT_RECOGNISED"]               # the soft warning does not depend on the rules
