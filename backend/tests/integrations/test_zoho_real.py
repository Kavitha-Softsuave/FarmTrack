"""The real Zoho adapter is an UNTESTED skeleton (field names assumed): these tests only pin its request shapes and failure behaviour."""
import json
from datetime import datetime

import httpx
import pytest

from app.clock import IST
from app.config import Settings
from app.domain.types import SprayRecord
from app.integrations.errors import NotConfigured, ZohoError
from app.integrations.zoho_real import RealZohoAdapter, ZohoConfig

DATA = Settings(_env_file=None).data_dir
ENV = {"ZOHO_CLIENT_ID": "cid", "ZOHO_CLIENT_SECRET": "csecret", "ZOHO_REFRESH_TOKEN": "rtoken"}


def test_missing_credentials_raise_a_clear_error(monkeypatch):
    for name in (*ENV, "ZOHO_ACCOUNTS_URL", "ZOHO_API_BASE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    with pytest.raises(NotConfigured) as exc:
        ZohoConfig.from_env()
    assert "ZOHO_CLIENT_SECRET" in str(exc.value) and "ZOHO_REFRESH_TOKEN" in str(exc.value)
    assert "cid" not in str(exc.value)


def test_config_defaults_to_the_india_data_centre(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ZOHO_ACCOUNTS_URL", raising=False)
    monkeypatch.delenv("ZOHO_API_BASE", raising=False)
    cfg = ZohoConfig.from_env()
    assert cfg.accounts_url == "https://accounts.zoho.in" and cfg.api_base == "https://www.zohoapis.in/crm/v6"
    monkeypatch.setenv("ZOHO_API_BASE", "https://example.test/crm/v6/")
    assert ZohoConfig.from_env().api_base == "https://example.test/crm/v6"


class FakeZohoApi:
    def __init__(self, contact=None, token_status=200, api_status=200):
        self.contact = contact if contact is not None else {"id": "C1", "Advisory": []}
        self.token_status, self.api_status = token_status, api_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "accounts.zoho.in":
            body = {"access_token": "at-1", "expires_in": 3600} if self.token_status == 200 else {"error": "invalid_code"}
            return httpx.Response(self.token_status, json=body)
        if self.api_status != 200:
            return httpx.Response(self.api_status, json={})
        if request.method == "GET":
            return httpx.Response(200, json={"data": [self.contact]} if self.contact else {})
        return httpx.Response(200, json={"data": [{"code": "SUCCESS"}]})


def adapter(api: FakeZohoApi, clock=lambda: 0.0) -> RealZohoAdapter:
    return RealZohoAdapter(ZohoConfig("cid", "csecret", "rtoken"), DATA, client=httpx.Client(transport=httpx.MockTransport(api)),
                           monotonic=clock)


def test_oauth_refresh_flow_and_token_reuse():
    api = FakeZohoApi()
    now = [0.0]
    zoho = adapter(api, lambda: now[0])
    zoho.get_history("F001")
    zoho.get_history("F001")
    token_calls = [r for r in api.requests if r.url.host == "accounts.zoho.in"]
    assert len(token_calls) == 1
    form = dict(httpx.QueryParams(token_calls[0].content.decode()))
    assert form == {"grant_type": "refresh_token", "client_id": "cid", "client_secret": "csecret", "refresh_token": "rtoken"}
    assert token_calls[0].url.path == "/oauth/v2/token"
    assert all(r.headers["authorization"] == "Zoho-oauthtoken at-1" for r in api.requests if r.url.host != "accounts.zoho.in")
    now[0] += 4000
    zoho.get_history("F001")
    assert len([r for r in api.requests if r.url.host == "accounts.zoho.in"]) == 2


def test_history_is_parsed_from_the_advisory_subform_and_clipped():
    contact = {"id": "C1", "Advisory": [
        {"Self_Spray_Dt": "14/04/2026", "Self_Sprayed": "Carbendazim 50% WP", "Self_Spray_Frac_Group": "1", "Self_Spray_Trade_Name": "Bavistin"},
        {"Self_Spray_Dt": "14/04/2026", "Self_Sprayed": "Zinc, Boron", "Self_Spray_Frac_Group": None},
        {"Self_Spray_Dt": "20/09/2026", "Self_Sprayed": "Captan", "Self_Spray_Frac_Group": "M4"},
    ]}
    api = FakeZohoApi(contact)
    records = adapter(api).get_history("F001", until=datetime(2026, 6, 1, tzinfo=IST))
    assert [r.active_ingredient for r in records] == ["Carbendazim", "Zinc, Boron"]
    assert records[0].frac_irac_code == "1" and records[1].nutrient is True
    search = next(r for r in api.requests if r.url.path.endswith("/Contacts/search"))
    assert search.url.params["criteria"] == "(Farmer_ID:equals:F001)"


def test_farmer_id_with_special_characters_is_never_sent():
    api = FakeZohoApi()
    zoho = adapter(api)
    assert zoho.get_farmer("F1),(Name:equals:x") is None
    assert zoho.get_history("a b") == []
    assert api.requests == []


def test_unknown_farmer_returns_none_and_empty_history():
    zoho = adapter(FakeZohoApi(contact={}))
    assert zoho.get_farmer("F777") is None
    assert zoho.get_history("F777") == []


def test_get_farmer_maps_the_assumed_fields():
    contact = {"id": "C9", "First_Name": "Asha", "Last_Name": "Devi", "Mobile": "+91 98765 43210", "Mailing_City": "Theog",
               "District": "Shimla", "Primary_Crop": "Apple"}
    farmer = adapter(FakeZohoApi(contact)).get_farmer("F001")
    assert (farmer.name, farmer.phone, farmer.village, farmer.primary_crop, farmer.zoho_contact_id) == (
        "Asha Devi", "+919876543210", "Theog", "Apple", "C9")


def test_write_spray_puts_a_new_subform_row():
    api = FakeZohoApi()
    record = SprayRecord(sprayed_at=datetime(2026, 5, 12, 9, 0, tzinfo=IST), active_ingredient="Captan",
                         frac_irac_code="M04", trade_name="Captaf")
    assert adapter(api).write_spray("F001", record) is True
    put = next(r for r in api.requests if r.method == "PUT")
    assert put.url.path.endswith("/Contacts/C1")
    row = json.loads(put.content)["data"][0]["Advisory"][0]
    assert row == {"Self_Spray_Dt": "12/05/2026", "Self_Sprayed": "Captan", "Self_Spray_Frac_Group": "M04", "Self_Spray_Trade_Name": "Captaf"}


def test_write_diagnosis_posts_a_note():
    api = FakeZohoApi()
    assert adapter(api).write_diagnosis("F001", {"disease_id": "Apple___Apple_scab"}) is True
    post = next(r for r in api.requests if r.method == "POST" and r.url.path.endswith("/Notes"))
    note = json.loads(post.content)["data"][0]
    assert note["Parent_Id"] == {"module": {"api_name": "Contacts"}, "id": "C1"}


def test_failed_writes_return_false_and_failed_reads_raise():
    record = SprayRecord(sprayed_at=datetime(2026, 5, 12, tzinfo=IST))
    broken = FakeZohoApi(api_status=500)
    assert adapter(broken).write_spray("F001", record) is False
    assert adapter(broken).write_diagnosis("F001", {}) is False
    with pytest.raises(ZohoError, match="500"):
        adapter(broken).get_history("F001")
    with pytest.raises(ZohoError, match="token"):
        adapter(FakeZohoApi(token_status=400)).get_history("F001")
