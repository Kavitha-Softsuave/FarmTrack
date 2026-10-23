import pytest
from sqlalchemy import select

from app.db.models import DeviceRow
from app.db.session import session_scope
from tests.fakes import NOW


def test_me_returns_the_profile_with_a_masked_phone(api_client, auth):
    body = api_client.get("/v1/me", headers=auth).json()
    assert body["id"] == "F001" and body["language"] == "hi" and body["primary_crop"] == "Apple"
    assert body["crops"] == ["Apple"] and body["station_id"] == "ST01" and body["district"] == "Shimla"
    assert body["phone_masked"] == "+91******0001" and "0000000001" not in str(body)


def test_me_lists_every_crop_the_farmer_grows(api_client, login):
    body = api_client.get("/v1/me", headers=login("+910000000003")).json()          # F003: Apple and Potato
    assert body["crops"] == ["Apple", "Potato"]


def test_patch_me_changes_language_and_name(api_client, auth):
    patched = api_client.patch("/v1/me", json={"language": "en", "name": "  Dinesh S.  "}, headers=auth)
    assert patched.status_code == 200 and patched.json()["language"] == "en" and patched.json()["name"] == "Dinesh S."
    assert api_client.get("/v1/me", headers=auth).json()["language"] == "en"


def test_patch_me_with_one_field_leaves_the_other(api_client, auth):
    before = api_client.get("/v1/me", headers=auth).json()
    after = api_client.patch("/v1/me", json={"language": "en"}, headers=auth).json()
    assert after["name"] == before["name"] and after["language"] == "en"


@pytest.mark.parametrize("payload", [{"language": "fr"}, {"name": "x" * 81}, {"name": "   "}, {"name": "\x00\x01"}, {"language": 5}])
def test_patch_me_validates(api_client, auth, payload):
    assert api_client.patch("/v1/me", json=payload, headers=auth).status_code == 422


def test_patch_me_cannot_change_protected_fields(api_client, auth):
    api_client.patch("/v1/me", json={"language": "en", "phone": "+919999999999", "id": "F002", "crops": ["Grape"]}, headers=auth)
    body = api_client.get("/v1/me", headers=auth).json()
    assert body["id"] == "F001" and body["crops"] == ["Apple"] and body["phone_masked"].endswith("0001")


def test_language_change_reaches_the_rules_input(api_client, auth, fake_container):
    from tests.imaging import photo_files

    api_client.patch("/v1/me", json={"language": "en"}, headers=auth)
    api_client.post("/v1/scans", files=photo_files(1), headers=auth)
    assert fake_container.rules.inputs[0].language == "en"


def test_register_device_creates_then_updates(api_client, auth):
    body = {"platform": "android", "push_token": "tok-1", "app_version": "1.0.0"}
    assert api_client.post("/v1/devices", json=body, headers=auth).status_code == 204
    assert api_client.post("/v1/devices", json={**body, "app_version": "1.1.0"}, headers=auth).content == b""
    with session_scope() as db:
        rows = db.scalars(select(DeviceRow)).all()
        assert len(rows) == 1 and rows[0].farmer_id == "F001" and rows[0].app_version == "1.1.0"
        assert rows[0].updated_at.replace(tzinfo=None) == NOW.replace(tzinfo=None)


def test_a_push_token_moves_to_the_farmer_who_logs_in_on_that_phone(api_client, auth, login):
    api_client.post("/v1/devices", json={"platform": "ios", "push_token": "shared"}, headers=auth)
    api_client.post("/v1/devices", json={"platform": "ios", "push_token": "shared"}, headers=login("+910000000002"))
    with session_scope() as db:
        assert [d.farmer_id for d in db.scalars(select(DeviceRow))] == ["F002"]


@pytest.mark.parametrize("payload", [{"platform": "windows", "push_token": "t"}, {"platform": "ios", "push_token": ""},
                                     {"platform": "ios", "push_token": "   "}, {"platform": "ios"}, {"platform": "ios", "push_token": "t" * 5000}])
def test_register_device_validates(api_client, auth, payload):
    assert api_client.post("/v1/devices", json=payload, headers=auth).status_code in (422,)


def test_meta_reports_providers_crops_and_the_demo_clock(api_client, fake_container):
    body = api_client.get("/v1/meta").json()
    assert body["supported_languages"] == ["hi", "en"] and body["env"] == "test"
    assert body["supported_crops"] == ["Apple", "Tomato", "Potato", "Maize", "Grape"]
    assert body["demo_clock"] == "2026-05-12T08:00:00+05:30"
    assert body["providers"]["llm"] == "mock" and body["providers"]["zoho"] == "mock" and body["providers"]["weather"] == "csv"
    assert not any("key" in k or "secret" in k for k in body["providers"])


def test_meta_supported_crops_come_from_the_rules_engine(api_client, fake_container):
    fake_container.rules.crops = ["Apple", "Pear"]
    assert api_client.get("/v1/meta").json()["supported_crops"] == ["Apple", "Pear"]


def test_meta_has_no_demo_clock_on_the_real_clock(api_client, fake_container):
    fake_container.clock.set(None)
    assert api_client.get("/v1/meta").json()["demo_clock"] is None


def test_meta_does_not_leak_secrets(api_client, api_settings):
    text = api_client.get("/v1/meta").text
    assert api_settings.secret_key not in text and api_settings.admin_api_key not in text


def test_health_is_ok(api_client):
    assert api_client.get("/health").json() == {"status": "ok", "db": True}
