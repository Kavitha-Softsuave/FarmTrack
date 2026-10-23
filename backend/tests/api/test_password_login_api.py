"""POST /v1/auth/login (username + password): the MVP login. The OTP routes stay in the code but are off by default."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db.models import FarmerRow, RefreshTokenRow
from app.db.session import session_scope
from app.main import create_app
from app.security.passwords import hash_password
from app.security.ratelimit import SlidingWindowLimiter
from tests import fakes

LOGIN = "/v1/auth/login"
OK = {"username": "f001", "password": "farm1234"}


def sign_in(client, username="f001", password="farm1234", device_id=None):
    return client.post(LOGIN, json={"username": username, "password": password, "device_id": device_id})


def live_sessions(farmer_id="F001") -> list[str | None]:
    with session_scope() as db:
        rows = db.scalars(select(RefreshTokenRow).where(RefreshTokenRow.farmer_id == farmer_id, RefreshTokenRow.revoked.is_(False)))
        return [r.device_id for r in rows]


# ------------------------------------------------------------------------------------------------------ success
def test_login_returns_the_same_token_shape_as_the_otp_login(api_client):
    response = sign_in(api_client, device_id="phone-1")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in", "farmer"}
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600
    assert body["farmer"]["id"] == "F001" and body["farmer"]["name"] == "Dinesh Sharma"
    assert body["farmer"]["phone_masked"] == "+91******0001"
    otp = api_client.post("/v1/auth/otp/request", json={"phone": "+910000000001"}).json()
    verified = api_client.post("/v1/auth/otp/verify", json={"request_id": otp["request_id"], "otp": otp["dev_otp"]}).json()
    assert set(verified) == set(body) and set(verified["farmer"]) == set(body["farmer"])


def test_the_access_token_opens_the_api(api_client):
    token = sign_in(api_client).json()["access_token"]
    me = api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["id"] == "F001"


@pytest.mark.parametrize("name", ["F001", "f001", "  f001  ", "F001 "])
def test_the_username_is_not_case_sensitive(api_client, name):
    assert sign_in(api_client, name).status_code == 200


def test_the_password_is_case_sensitive(api_client):
    assert sign_in(api_client, password="FARM1234").status_code == 401


def test_login_also_works_for_another_demo_farmer(api_client):
    response = sign_in(api_client, "f050")
    assert response.status_code == 200 and response.json()["farmer"]["id"] == "F050"


# ------------------------------------------------------------------------------------------------------ failures
def test_wrong_password_is_a_401_invalid_credentials(api_client):
    response = sign_in(api_client, password="not-the-password")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials" and "access_token" not in response.text


def test_unknown_user_and_wrong_password_get_the_identical_answer(api_client):
    wrong_password = sign_in(api_client, "f001", "not-the-password")
    unknown_user = sign_in(api_client, "nobody.here", "not-the-password")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert set(wrong_password.headers) - {"x-request-id"} == set(unknown_user.headers) - {"x-request-id"}


def test_an_unknown_user_still_costs_a_password_check(api_client, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.auth_service.burn_password_check", lambda password: calls.append(password))
    sign_in(api_client, "nobody.here", "whatever1")
    assert calls == ["whatever1"]
    calls.clear()
    sign_in(api_client, "f001", "whatever1")                                   # a real user: the real hash is checked instead
    assert calls == []


@pytest.mark.parametrize("name", ["", "ab", "has space", "x" * 99, "f001'--"])
def test_a_username_of_the_wrong_shape_is_just_a_401(api_client, name):
    assert sign_in(api_client, name).status_code == 401


def test_an_empty_password_is_a_401(api_client):
    assert sign_in(api_client, password="").status_code == 401


def test_a_farmer_without_a_password_cannot_log_in(api_client):
    with session_scope() as db:
        farmer = db.get(FarmerRow, "F002")
        farmer.password_hash = None
        db.commit()
    assert sign_in(api_client, "f002").status_code == 401


def test_a_farmer_without_a_username_cannot_be_reached(api_client):
    with session_scope() as db:
        db.get(FarmerRow, "F002").username = None
        db.commit()
    assert sign_in(api_client, "f002").status_code == 401


def test_the_phone_number_is_no_longer_a_login(api_client):
    assert sign_in(api_client, "+910000000001").status_code == 401


@pytest.mark.parametrize("payload", [{}, {"username": "f001"}, {"password": "farm1234"}, {"username": 1, "password": "x"},
                                     {"username": "f" * 101, "password": "x"}, {"username": "f001", "password": "x" * 201}])
def test_a_malformed_body_is_a_422(api_client, payload):
    assert api_client.post(LOGIN, json=payload).status_code == 422


def test_login_is_open_without_a_token(api_client):
    assert api_client.post(LOGIN, json=OK).status_code == 200


# ------------------------------------------------------------------------------------------------------ rate limits
def test_wrong_passwords_are_limited_per_username(api_client):
    codes = [sign_in(api_client, "f003", "wrong-password").status_code for _ in range(9)]
    assert codes == [401] * 8 + [429]
    blocked = sign_in(api_client, "f003", "farm1234")                         # even the RIGHT password: no out-guessing the limit
    assert blocked.status_code == 429 and blocked.json()["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) >= 1
    assert sign_in(api_client, "F003", "farm1234").status_code == 429          # the name is counted in lower case
    assert sign_in(api_client, "f004", "farm1234").status_code == 200          # another user is unaffected


def test_unknown_usernames_are_limited_too(api_client):
    codes = [sign_in(api_client, "nobody.here", "wrong-password").status_code for _ in range(9)]
    assert codes == [401] * 8 + [429]


def test_good_logins_do_not_use_up_the_username_budget(api_client, api_app):
    api_app.state.limiters.login_ip = SlidingWindowLimiter(1000, 600.0)
    assert [sign_in(api_client).status_code for _ in range(12)] == [200] * 12


def test_attempts_are_limited_per_ip(api_client, api_app):
    api_app.state.limiters.login_ip = SlidingWindowLimiter(3, 600.0)
    assert [sign_in(api_client, f"nobody{i}").status_code for i in range(4)] == [401, 401, 401, 429]
    limited = sign_in(api_client)
    assert limited.status_code == 429 and limited.json()["code"] == "rate_limited" and "Retry-After" in limited.headers


def test_the_default_limits_are_light_but_real(api_app):
    limiters = api_app.state.limiters
    assert (limiters.login_ip.limit, limiters.login_ip.window) == (20, 600.0)
    assert (limiters.login_user_fail.limit, limiters.login_user_fail.window) == (8, 600.0)


# ------------------------------------------------------------------------------------------------------ sessions and devices
def test_refresh_works_after_a_password_login(api_client):
    first = sign_in(api_client, device_id="phone-1").json()
    rotated = api_client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200 and rotated.json()["refresh_token"] != first["refresh_token"]
    assert api_client.get("/v1/me", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"}).status_code == 200
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401   # rotated away


def test_logout_ends_a_password_session(api_client):
    issued = sign_in(api_client, device_id="phone-1").json()
    assert api_client.post("/v1/auth/logout", json={"refresh_token": issued["refresh_token"]}).status_code == 204
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]}).status_code == 401


def test_a_new_login_on_the_same_device_replaces_the_old_session(api_client):
    old = sign_in(api_client, device_id="phone-1").json()
    sign_in(api_client, device_id="phone-1")
    assert live_sessions() == ["phone-1"]                                       # one live session per device
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401


def test_sessions_on_different_devices_coexist(api_client):
    a, b = sign_in(api_client, device_id="phone-a").json(), sign_in(api_client, device_id="phone-b").json()
    assert sorted(live_sessions()) == ["phone-a", "phone-b"]
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": a["refresh_token"]}).status_code == 200
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": b["refresh_token"]}).status_code == 200


def test_logins_without_a_device_id_do_not_replace_each_other(api_client):
    sign_in(api_client)
    sign_in(api_client)
    assert live_sessions() == [None, None]


def test_an_overlong_device_id_is_a_422_and_creates_no_session(api_client):
    response = sign_in(api_client, device_id="d" * 81)
    assert response.status_code == 422 and response.json()["code"] == "invalid_device_id"
    assert live_sessions() == []


def test_a_failed_login_creates_no_session(api_client):
    sign_in(api_client, password="wrong-password", device_id="phone-1")
    assert live_sessions() == []


def test_active_sessions_are_capped_for_password_logins_too(api_client, api_app):
    api_app.state.limiters.login_ip = SlidingWindowLimiter(1000, 600.0)
    for i in range(12):
        assert sign_in(api_client, device_id=f"device-{i}").status_code == 200
    assert len(live_sessions()) == 10


def test_the_password_never_appears_in_the_logs(api_client, caplog):
    with caplog.at_level("DEBUG"):
        sign_in(api_client, "f001", "very-secret-pass-77")
        sign_in(api_client, "f001", "farm1234")
    assert "very-secret-pass-77" not in caplog.text and "farm1234" not in caplog.text


# ------------------------------------------------------------------------------------------------------ admin-made logins work
def test_a_farmer_created_by_the_admin_can_log_in_and_a_reset_ends_the_old_session(api_client, api_app):
    key = {"X-Admin-Key": api_app.state.settings.admin_api_key}
    created = api_client.post("/admin/api/v1/farmers", headers=key, json={
        "name": "New Farmer", "phone": "+919876543210", "language": "en", "primary_crop": "Apple", "username": "New.Farmer",
        "password": "first-pass"})
    assert created.status_code == 201, created.text
    first = sign_in(api_client, "new.farmer", "first-pass", device_id="phone-1")
    assert first.status_code == 200 and first.json()["farmer"]["name"] == "New Farmer"
    reset = api_client.post(f"/admin/api/v1/farmers/{created.json()['id']}/login", headers=key,
                            json={"username": "new.farmer", "password": "second-pass"})
    assert reset.status_code == 200
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}).status_code == 401
    assert sign_in(api_client, "new.farmer", "first-pass").status_code == 401
    assert sign_in(api_client, "new.farmer", "second-pass").status_code == 200


# ------------------------------------------------------------------------------------------------------ the OTP login is off by default
@pytest.fixture
def otp_off_client(monkeypatch, voice_dir):
    monkeypatch.delenv("OTP_LOGIN_ENABLED")
    settings = Settings(_env_file=None)
    assert settings.otp_login_enabled is False                                   # the default of the setting itself
    container = fakes.make_container(settings)
    app = create_app(settings, container_factory=lambda _s: container)
    app.state.container = container
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_otp_routes_answer_404_by_default(otp_off_client):
    request = otp_off_client.post("/v1/auth/otp/request", json={"phone": "+910000000001"})
    verify = otp_off_client.post("/v1/auth/otp/verify", json={"request_id": "x" * 32, "otp": "123456"})
    for response in (request, verify):
        assert response.status_code == 404 and response.json()["code"] == "not_found"
    assert "dev_otp" not in request.text


def test_otp_routes_answer_404_even_for_a_bad_body(otp_off_client):
    assert otp_off_client.post("/v1/auth/otp/request", json={"phone": "abc"}).status_code == 404
    assert otp_off_client.post("/v1/auth/otp/verify", content=b"{bad").status_code == 404


def test_password_login_works_while_otp_is_off(otp_off_client):
    response = otp_off_client.post(LOGIN, json=OK)
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert otp_off_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_otp_routes_work_when_the_setting_is_on(api_client):
    assert Settings(_env_file=None).otp_login_enabled is True                    # the test environment turns it on
    otp = api_client.post("/v1/auth/otp/request", json={"phone": "+910000000001"})
    assert otp.status_code == 200 and otp.json()["dev_otp"] == "123456"
    verified = api_client.post("/v1/auth/otp/verify", json={"request_id": otp.json()["request_id"], "otp": "123456"})
    assert verified.status_code == 200


def test_the_otp_setting_reads_the_environment_variable(monkeypatch):
    monkeypatch.setenv("OTP_LOGIN_ENABLED", "false")
    assert Settings(_env_file=None).otp_login_enabled is False
    monkeypatch.setenv("OTP_LOGIN_ENABLED", "1")
    assert Settings(_env_file=None).otp_login_enabled is True


def test_the_demo_password_setting_has_its_default(monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    assert Settings(_env_file=None).demo_password == "farm1234"
    monkeypatch.setenv("DEMO_PASSWORD", "another-demo-pass")
    assert Settings(_env_file=None).demo_password == "another-demo-pass"


def test_a_hash_is_stored_never_the_password(api_client):
    with session_scope() as db:
        farmer = db.get(FarmerRow, "F001")
        assert farmer.username == "f001" and farmer.password_hash.startswith("pbkdf2_sha256$")
        assert "farm1234" not in farmer.password_hash and farmer.password_hash != hash_password("farm1234")   # salted
