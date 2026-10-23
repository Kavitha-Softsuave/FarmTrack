from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import AdviceRow, SprayLogRow
from app.db.session import session_scope
from app.domain.types import Severity, WarningItem
from tests.fakes import NOW, lt
from tests.imaging import photo_files


def log_spray(client, auth, **body):
    return client.post("/v1/spray-logs", json={"crop_id": "Apple", **body}, headers=auth)


def scan_advice_id(client, auth):
    return client.post("/v1/scans", files=photo_files(1), headers=auth).json()["advice"]["id"]


def test_sprayed_tick_from_an_advice_saves_and_syncs(api_client, auth, fake_container):
    advice_id = scan_advice_id(api_client, auth)
    response = log_spray(api_client, auth, advice_id=advice_id, product_id="P012")
    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "P012" and body["product_name"] == "Myclobutanil" and body["advice_id"] == advice_id
    assert body["crop_id"] == "Apple" and body["sprayed_at"] == "2026-05-12T08:00:00+05:30"       # default: the demo clock
    assert body["synced_to_zoho"] is True and body["warnings"] == []
    assert body["spoken"]["text"]["en"] == "Done. It is saved in your diary."
    farmer_id, record = fake_container.zoho.spray_writes[0]
    assert farmer_id == "F001" and record.product_id == "P012" and record.source == "app"
    assert record.active_ingredient == "Myclobutanil" and record.frac_irac_code in ("3", None)   # enriched from the product master
    with session_scope() as db:
        row = db.scalars(select(SprayLogRow)).one()
        assert row.synced_to_zoho and row.farmer_id == "F001"


def test_a_single_product_advice_does_not_need_a_product_id(api_client, auth):
    body = log_spray(api_client, auth, advice_id=scan_advice_id(api_client, auth)).json()
    assert body["product_id"] == "P012"


def test_a_product_id_alone_is_named_from_the_product_master(api_client, auth):
    assert log_spray(api_client, auth, product_id="P012").json()["product_name"] == "Myclobutanil"
    assert log_spray(api_client, auth, product_id="P999", free_text="Local mix").json()["product_name"] == "Local mix"


def test_free_text_entry_that_is_not_in_the_catalogue_has_no_product_id(api_client, auth, fake_container):
    body = api_client.post("/v1/spray-logs", json={"crop_id": "Apple", "free_text": "Local mix"}, headers=auth).json()
    assert body["product_id"] is None and body["product_name"] == "Local mix" and body["synced_to_zoho"] is True
    assert [w["code"] for w in body["warnings"]] == ["PRODUCT_NOT_RECOGNISED"]
    assert fake_container.zoho.spray_writes[0][1].trade_name == "Local mix"


def test_free_text_entry_naming_a_catalogue_brand_gets_its_product(api_client, auth, fake_container):
    body = log_spray(api_client, auth, free_text="Bavistin").json()
    assert body["product_id"] == "P009" and body["product_name"] == "Bavistin (Carbendazim)" and body["warnings"] == []
    record = fake_container.zoho.spray_writes[0][1]
    assert record.trade_name == "Bavistin" and record.product_id == "P009" and record.active_ingredient == "Carbendazim"


def test_an_entry_with_nothing_to_record_is_refused(api_client, auth):
    response = log_spray(api_client, auth)
    assert response.status_code == 422 and response.json()["code"] == "spray_needs_product"


def test_rules_warnings_are_returned_stored_and_spoken(api_client, auth, fake_container):
    fake_container.rules.spray_warnings = [
        WarningItem(code="NUTRIENT_SAME_DAY", level=Severity.red, text=lt("Do not mix a nutrient with the fungicide.", "मिलाइए मत।"))]
    body = log_spray(api_client, auth, product_id="P012").json()
    assert body["warnings"] == [{"code": "NUTRIENT_SAME_DAY", "level": "red",
                                 "text": {"en": "Do not mix a nutrient with the fungicide.", "hi": "मिलाइए मत।"}}]
    assert body["spoken"]["text"]["en"] == "Done. It is saved in your diary. There is a warning. Do not mix a nutrient with the fungicide."
    assert api_client.get("/v1/spray-logs", headers=auth).json()[0]["warnings"][0]["code"] == "NUTRIENT_SAME_DAY"


def test_check_sees_zoho_and_earlier_diary_history_but_not_the_new_entry(api_client, auth, fake_container):
    from app.domain.types import SprayRecord

    fake_container.zoho.history = [SprayRecord(sprayed_at=NOW - timedelta(days=5), product_id="P003")]
    log_spray(api_client, auth, product_id="P012", sprayed_at=(NOW - timedelta(days=2)).isoformat())
    log_spray(api_client, auth, product_id="P011")
    first, second = fake_container.rules.spray_checks
    assert [r.product_id for r in first["history"]] == ["P003"]
    assert [r.product_id for r in second["history"]] == ["P003", "P012"] and second["record"].product_id == "P011"


def test_nutrient_entries_are_flagged_for_the_same_day_rule(api_client, auth, fake_container):
    log_spray(api_client, auth, free_text="Zinc and boron mix")
    assert fake_container.rules.spray_checks[0]["record"].nutrient is True


def test_zoho_write_failure_still_saves_the_diary(api_client, auth, fake_container):
    fake_container.zoho.write_ok = False
    body = log_spray(api_client, auth, product_id="P012").json()
    assert body["synced_to_zoho"] is False
    assert len(api_client.get("/v1/spray-logs", headers=auth).json()) == 1


def test_zoho_write_exception_still_saves_the_diary(api_client, auth, fake_container):
    def boom(farmer_id, record):
        raise RuntimeError("zoho down")

    fake_container.zoho.write_spray = boom
    assert log_spray(api_client, auth, product_id="P012").json()["synced_to_zoho"] is False


def test_rules_failure_does_not_lose_the_farmers_entry(api_client, auth, fake_container):
    def boom(*_a):
        raise RuntimeError("rules down")

    fake_container.rules.check_spray = boom
    body = log_spray(api_client, auth, product_id="P012").json()
    assert body["warnings"] == [] and body["synced_to_zoho"] is True


def test_sprayed_at_is_normalised_and_bounded(api_client, auth):
    explicit = log_spray(api_client, auth, product_id="P012", sprayed_at="2026-05-10T06:00:00+00:00").json()
    assert explicit["sprayed_at"] == "2026-05-10T11:30:00+05:30"
    naive = log_spray(api_client, auth, product_id="P012", sprayed_at="2026-05-09T09:00:00").json()
    assert naive["sprayed_at"] == "2026-05-09T09:00:00+05:30"
    too_old = log_spray(api_client, auth, product_id="P012", sprayed_at="2024-01-01T09:00:00+05:30")
    assert too_old.status_code == 422 and too_old.json()["code"] == "sprayed_at_too_old"


def test_a_future_date_is_refused_on_a_running_clock_but_allowed_on_the_frozen_demo_clock(api_client, auth, fake_container):
    future = (NOW + timedelta(days=3)).isoformat()
    assert log_spray(api_client, auth, product_id="P012", sprayed_at=future).status_code == 200      # frozen demo clock
    fake_container.clock.set(None)                                                                  # real clock
    real_future = log_spray(api_client, auth, product_id="P012", sprayed_at="2099-01-01T00:00:00+05:30")
    assert real_future.status_code == 422 and real_future.json()["code"] == "sprayed_at_in_future"


def test_another_farmers_advice_cannot_be_referenced(api_client, auth, login):
    advice_id = scan_advice_id(api_client, auth)
    response = log_spray(api_client, login("+910000000002"), advice_id=advice_id, product_id="P012")
    assert response.status_code == 404 and response.json()["code"] == "advice_not_found"
    assert log_spray(api_client, auth, advice_id="0" * 32, product_id="P012").status_code == 404


@pytest.mark.parametrize("body", [{"crop_id": "../x", "free_text": "a"}, {"crop_id": "Apple", "product_id": "bad id!"},
                                  {"crop_id": "Apple", "product_id": "P" * 11}])
def test_invalid_identifiers_are_422(api_client, auth, body):
    assert api_client.post("/v1/spray-logs", json=body, headers=auth).status_code == 422


@pytest.mark.parametrize("body", [{"crop_id": "Apple", "free_text": "x" * 201}, {"crop_id": "Apple", "free_text": "x", "notes": "n" * 301},
                                  {"free_text": "x"}])
def test_schema_limits_are_enforced(api_client, auth, body):
    assert api_client.post("/v1/spray-logs", json=body, headers=auth).status_code == 422


def test_crop_name_is_canonicalised(api_client, auth):
    assert log_spray(api_client, auth, crop_id="apple", free_text="x").json()["crop_id"] == "Apple"


def test_list_is_newest_spray_first_and_private(api_client, auth, login):
    for day in (3, 7, 5):
        log_spray(api_client, auth, free_text=f"day{day}", sprayed_at=NOW.replace(day=day).isoformat())
    assert [e["product_name"] for e in api_client.get("/v1/spray-logs", headers=auth).json()] == ["day7", "day5", "day3"]
    assert api_client.get("/v1/spray-logs?limit=1", headers=auth).json()[0]["product_name"] == "day7"
    assert api_client.get("/v1/spray-logs", headers=login("+910000000002")).json() == []
    assert all(e["spoken"] is None for e in api_client.get("/v1/spray-logs", headers=auth).json())


def test_diary_entries_feed_the_next_scan(api_client, auth, fake_container):
    log_spray(api_client, auth, product_id="P012", sprayed_at=(NOW - timedelta(days=4)).isoformat())
    api_client.post("/v1/scans", files=photo_files(1), headers=auth)
    assert [r.product_id for r in fake_container.rules.inputs[0].history] == ["P012"]


def test_an_entry_already_synced_to_zoho_is_not_counted_twice(api_client, auth, fake_container):
    when = NOW - timedelta(days=4)
    log_spray(api_client, auth, product_id="P012", sprayed_at=when.isoformat())
    farmer_id, record = fake_container.zoho.spray_writes[0]
    fake_container.zoho.history = [record.model_copy(update={"source": "zoho"})]          # Zoho now returns what the app wrote
    api_client.post("/v1/scans", files=photo_files(1), headers=auth)
    assert len(fake_container.rules.inputs[0].history) == 1


def test_advice_row_is_untouched_by_logging(api_client, auth):
    advice_id = scan_advice_id(api_client, auth)
    log_spray(api_client, auth, advice_id=advice_id)
    with session_scope() as db:
        assert db.get(AdviceRow, advice_id).farmer_id == "F001"
