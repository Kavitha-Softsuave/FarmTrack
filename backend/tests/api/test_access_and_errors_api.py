"""401 vs 403 vs 404, admin key, error format, security headers, request ids."""
from datetime import timedelta

import jwt
import pytest

from app.api.deps import get_db
from app.security import timeutil
from app.security.tokens import ALGORITHM, create_access_token, derive_key

AUTHENTICATED = [
    ("GET", "/v1/me", {}), ("PATCH", "/v1/me", {"json": {"language": "en"}}),
    ("POST", "/v1/scans", {}), ("GET", "/v1/scans", {}), ("GET", "/v1/scans/abc", {}),
    ("POST", "/v1/scans/abc/photos", {}), ("POST", "/v1/scans/abc/crop", {"json": {"crop_id": "Apple"}}),
    ("POST", "/v1/spray-logs", {"json": {"crop_id": "Apple", "free_text": "x"}}), ("GET", "/v1/spray-logs", {}),
    ("GET", "/v1/field", {}), ("GET", "/v1/alerts", {}), ("POST", "/v1/alerts/abc/read", {}),
    ("POST", "/v1/devices", {"json": {"platform": "android", "push_token": "t"}}),
    ("POST", "/v1/ask", {"json": {"question": "how to spray?"}}), ("POST", "/v1/expert-requests", {"json": {}}),
]
PUBLIC = [("GET", "/health"), ("GET", "/v1/meta"), ("GET", "/audio/" + "0" * 64 + ".mp3")]


def call(client, method, path, headers=None, **kwargs):
    return client.request(method, path, headers=headers, **kwargs)


@pytest.mark.parametrize("method,path,kwargs", AUTHENTICATED)
def test_every_private_endpoint_requires_a_token(api_client, method, path, kwargs):
    response = call(api_client, method, path, **kwargs)
    assert response.status_code == 401, (method, path)
    assert response.json()["code"] == "not_authenticated" and response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("method,path,kwargs", AUTHENTICATED)
def test_every_private_endpoint_rejects_a_garbage_token(api_client, method, path, kwargs):
    response = call(api_client, method, path, headers={"Authorization": "Bearer not.a.token"}, **kwargs)
    assert response.status_code == 401 and response.json()["code"] == "invalid_token"


@pytest.mark.parametrize("method,path", PUBLIC)
def test_public_endpoints_need_no_token(api_client, method, path):
    assert call(api_client, method, path).status_code in (200, 404)         # 404 only for the audio file that does not exist


def test_expired_token_is_401_token_expired(api_client, auth, monkeypatch):
    later = timeutil.utcnow() + timedelta(minutes=61)
    monkeypatch.setattr(timeutil, "utcnow", lambda: later)
    response = api_client.get("/v1/me", headers=auth)
    assert response.status_code == 401 and response.json()["code"] == "token_expired"


def test_token_signed_with_another_key_is_rejected(api_client, api_settings):
    forged = jwt.encode({"sub": "F001", "typ": "access", "iat": 1, "exp": 4102444800}, "wrong-key" * 5, algorithm=ALGORITHM)
    assert api_client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_valid_token_for_a_removed_farmer_is_401(api_client, api_settings):
    token, _ = create_access_token(api_settings, "F999")
    assert api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_other_authorization_schemes_are_rejected(api_client, auth):
    token = auth["Authorization"].split()[1]
    for header in (f"Basic {token}", token, "Bearer"):
        assert api_client.get("/v1/me", headers={"Authorization": header}).status_code == 401, header


def test_admin_key_missing_wrong_and_right(api_client, api_settings):
    url = "/admin/api/v1/farmers"
    missing = api_client.get(url)
    assert missing.status_code == 401 and missing.json()["code"] == "admin_key_required"
    wrong = api_client.get(url, headers={"X-Admin-Key": "nope"})
    assert wrong.status_code == 403 and wrong.json()["code"] == "invalid_admin_key"
    ok = api_client.get(url, headers={"X-Admin-Key": api_settings.admin_api_key})
    assert ok.status_code == 200 and len(ok.json()) > 0


def test_a_farmer_token_is_not_an_admin_key(api_client, auth):
    token = auth["Authorization"].split()[1]
    assert api_client.get("/admin/api/v1/farmers", headers={"X-Admin-Key": token}).status_code == 403
    assert api_client.get("/admin/api/v1/farmers", headers=auth).status_code == 401


def test_a_near_miss_admin_key_is_refused(api_client, api_settings):
    key = api_settings.admin_api_key
    for guess in (key[:-1], key + "x", key.upper(), " " + key):
        assert api_client.get("/admin/api/v1/farmers", headers={"X-Admin-Key": guess}).status_code == 403


def test_wrong_admin_keys_are_rate_limited(api_client):
    codes = [api_client.get("/admin/api/v1/farmers", headers={"X-Admin-Key": f"guess{i}"}).status_code for i in range(12)]
    assert codes[:10] == [403] * 10 and codes[10:] == [429, 429]


def test_admin_key_comparison_is_constant_time(monkeypatch, api_client, api_settings):
    import hmac

    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append((a, b)) or real(a, b))
    api_client.get("/admin/api/v1/farmers", headers={"X-Admin-Key": "x"})
    assert calls and calls[0][1] == api_settings.admin_api_key.encode()


# ------------------------------------------------------------------------------------------------ error format
def assert_error_shape(body, code=None):
    assert set(body) >= {"code", "message", "details"}
    assert isinstance(body["code"], str) and isinstance(body["message"], str)
    if code:
        assert body["code"] == code


def test_unknown_route_is_a_json_error(api_client):
    response = api_client.get("/v1/does-not-exist")
    assert response.status_code == 404 and response.headers["content-type"].startswith("application/json")
    assert_error_shape(response.json(), "not_found")


def test_wrong_method_is_a_json_error(api_client):
    response = api_client.post("/health")
    assert response.status_code == 405
    assert_error_shape(response.json(), "method_not_allowed")


def test_validation_errors_use_the_error_shape_and_do_not_echo_the_input(api_client):
    response = api_client.post("/v1/auth/otp/request", json={"phone": "+91SECRETPHONE"})
    assert response.status_code == 422
    body = response.json()
    assert_error_shape(body, "validation_error")
    assert body["details"]["errors"][0]["loc"] == ["body", "phone"]
    assert body["detail"][0]["loc"] == ["body", "phone"]                     # FastAPI's own shape stays available
    assert "SECRETPHONE" not in response.text and "input" not in body["details"]["errors"][0]


def test_malformed_json_is_a_validation_error(api_client):
    response = api_client.post("/v1/auth/otp/request", content=b"{bad json", headers={"content-type": "application/json"})
    assert response.status_code == 422 and response.json()["code"] == "validation_error"


def test_unhandled_errors_are_a_clean_500_without_details(api_client, fake_container):
    def boom():
        raise RuntimeError("secret internal detail +910000000001")

    fake_container.rules.supported_crops = boom
    response = api_client.get("/v1/meta")
    assert response.status_code == 500
    body = response.json()
    assert_error_shape(body, "internal_error")
    assert "secret internal detail" not in response.text and "Traceback" not in response.text
    assert body["details"]["request_id"] == response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"          # the last-resort 500 is also hardened


def test_every_documented_error_body_parses_as_error_out(api_client, auth):
    from app.api.schemas import ErrorOut

    for response in (api_client.get("/v1/me"), api_client.get("/v1/scans/" + "0" * 32, headers=auth),
                     api_client.post("/v1/auth/refresh", json={"refresh_token": "x"})):
        assert response.status_code >= 400
        ErrorOut.model_validate(response.json())


# ------------------------------------------------------------------------------------------------ headers and request ids
def test_security_headers_on_api_responses(api_client):
    headers = api_client.get("/v1/meta").headers
    assert headers["x-content-type-options"] == "nosniff" and headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer" and headers["cache-control"] == "no-store"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert "strict-transport-security" not in headers                        # only in production


def test_security_headers_also_on_errors(api_client):
    headers = api_client.get("/nope").headers
    assert headers["x-content-type-options"] == "nosniff" and headers["x-request-id"]


def test_api_docs_keep_working_outside_production(api_client):
    page = api_client.get("/docs")
    assert page.status_code == 200 and "content-security-policy" not in page.headers


def test_request_id_is_generated_and_a_valid_incoming_one_is_kept(api_client):
    generated = api_client.get("/health").headers["x-request-id"]
    assert len(generated) == 32
    assert api_client.get("/health", headers={"X-Request-ID": "client-req-12345"}).headers["x-request-id"] == "client-req-12345"
    assert api_client.get("/health", headers={"X-Request-ID": "x"}).headers["x-request-id"] != "x"
    hostile = "a b<script>" * 5
    assert api_client.get("/health", headers={"X-Request-ID": hostile}).headers["x-request-id"] != hostile


def test_hsts_is_sent_in_production():
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.fakes import plain_settings

    settings = plain_settings(env="prod", secret_key="k" * 40, admin_api_key="a" * 24, cors_origins=["https://farm.example"])
    headers = TestClient(create_app(settings), raise_server_exceptions=False).get("/nope").headers
    assert headers["strict-transport-security"].startswith("max-age=")


def test_logs_never_contain_the_phone_or_the_token(api_client, caplog, login):
    caplog.set_level("DEBUG", logger="app")
    headers = login()
    api_client.get("/v1/me", headers=headers)
    api_client.post("/v1/ask", json={"question": "my secret orchard question text"}, headers=headers)
    text = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
    assert "0000000001" not in text and headers["Authorization"].split()[1] not in text
    assert "secret orchard question" not in text


# ------------------------------------------------------------------------------------------------ health
def test_health_reports_a_database_outage_as_503(api_app, api_client):
    class Broken:
        def execute(self, *_a, **_k):
            raise RuntimeError("db gone")

    api_app.dependency_overrides[get_db] = lambda: iter([Broken()])
    response = api_client.get("/health")
    assert response.status_code == 503 and response.json() == {"status": "degraded", "db": False}
    api_app.dependency_overrides.clear()
    assert api_client.get("/health").json() == {"status": "ok", "db": True}


def test_derive_key_separates_purposes():
    assert derive_key("secret", "jwt") != derive_key("secret", "otp-pepper") != derive_key("secret", "refresh")
    assert len(derive_key("secret", "jwt")) == 32


def test_requests_before_the_container_exists_get_a_503_not_a_crash(api_app):
    from fastapi.testclient import TestClient

    api_app.state.container = None
    with TestClient(api_app, raise_server_exceptions=False) as client:          # lifespan would build one; skip it for this call
        api_app.state.container = None
        response = client.get("/v1/meta")
    assert response.status_code == 503 and response.json()["code"] == "service_unavailable"
