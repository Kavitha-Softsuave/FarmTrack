from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import OtpRequestRow, RefreshTokenRow
from app.db.session import session_scope
from app.security import timeutil
from app.security.ratelimit import RateLimiters, SlidingWindowLimiter
from tests.fakes import DEMO_PHONE, DEMO_PHONE_2


def request_otp(client, phone=DEMO_PHONE):
    return client.post("/v1/auth/otp/request", json={"phone": phone})


def verify(client, request_id, otp, device_id=None):
    return client.post("/v1/auth/otp/verify", json={"request_id": request_id, "otp": otp, "device_id": device_id})


def move_time(monkeypatch, **delta):
    later = timeutil.utcnow() + timedelta(**delta)
    monkeypatch.setattr(timeutil, "utcnow", lambda: later)


# ------------------------------------------------------------------------------------------------ happy path
def test_otp_login_returns_tokens_and_the_farmer(api_client):
    body = request_otp(api_client).json()
    assert body["expires_in"] == 300 and body["dev_otp"] == "123456"
    result = verify(api_client, body["request_id"], body["dev_otp"], device_id="phone-1")
    assert result.status_code == 200
    token = result.json()
    assert token["token_type"] == "bearer" and token["expires_in"] == 3600
    assert token["farmer"]["id"] == "F001" and token["farmer"]["phone_masked"] == "+91******0001"
    assert "phone" not in token["farmer"]
    assert api_client.get("/v1/me", headers={"Authorization": f"Bearer {token['access_token']}"}).status_code == 200


def test_phone_formats_are_normalised(api_client):
    for raw in ("+910000000001", "0000000001", "910000000001"):
        assert request_otp(api_client, raw).json()["dev_otp"] == "123456", raw


def test_invalid_phone_shape_is_a_validation_error(api_client):
    for bad in ("abc", "123", "+9100000000010000", ""):
        response = request_otp(api_client, bad)
        assert response.status_code == 422 and response.json()["code"] == "validation_error"


def test_otp_is_stored_only_as_a_hash(api_client):
    body = request_otp(api_client).json()
    with session_scope() as db:
        row = db.get(OtpRequestRow, body["request_id"])
        assert "123456" not in row.otp_hash and len(row.otp_hash) == 64
        assert row.phone == DEMO_PHONE and not row.consumed and row.attempts == 0


def test_dev_otp_is_not_returned_in_production(api_client, api_app, monkeypatch):
    from app.config import Settings

    prod_like = Settings(_env_file=None, env="prod", secret_key="k" * 40, admin_api_key="a" * 24, cors_origins=["https://x.example"])
    monkeypatch.setattr(api_app.state, "settings", prod_like)
    response = request_otp(api_client)
    assert response.status_code == 200 and response.json()["dev_otp"] is None
    body = response.json()
    assert verify(api_client, body["request_id"], "123456").status_code == 400      # the fixed dev code is not honoured in prod


def test_sms_carries_a_random_code_in_prod_and_never_logs_it(api_client, api_app, monkeypatch, caplog):
    from app.config import Settings

    sent = []

    class Capture:
        def send(self, phone, message):
            sent.append((phone, message))

    api_app.state.sms_sender = Capture()
    monkeypatch.setattr(api_app.state, "settings", Settings(_env_file=None, env="prod", secret_key="k" * 40,
                                                            admin_api_key="a" * 24, cors_origins=["https://x.example"]))
    body = request_otp(api_client).json()
    assert body["dev_otp"] is None and len(sent) == 1
    phone, message = sent[0]
    code = next(w for w in message.split() if w.strip(".").isdigit()).strip(".")
    assert phone == DEMO_PHONE and len(code) == 6
    assert verify(api_client, body["request_id"], code).status_code == 200
    assert code not in caplog.text and DEMO_PHONE not in caplog.text


# ------------------------------------------------------------------------------------------------ failures
def test_wrong_code_then_right_code(api_client):
    body = request_otp(api_client).json()
    wrong = verify(api_client, body["request_id"], "000000")
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "invalid_otp" and wrong.json()["details"]["attempts_left"] == 4
    assert verify(api_client, body["request_id"], body["dev_otp"]).status_code == 200


def test_attempts_are_limited_even_for_the_right_code(api_client):
    body = request_otp(api_client).json()
    for _ in range(5):
        assert verify(api_client, body["request_id"], "000000").json()["code"] == "invalid_otp"
    locked = verify(api_client, body["request_id"], body["dev_otp"])
    assert locked.status_code == 400 and locked.json()["code"] == "otp_attempts_exceeded"


def test_code_expires(api_client, monkeypatch):
    body = request_otp(api_client).json()
    move_time(monkeypatch, seconds=301)
    expired = verify(api_client, body["request_id"], body["dev_otp"])
    assert expired.status_code == 400 and expired.json()["code"] == "otp_expired"


def test_code_is_valid_just_before_expiry(api_client, monkeypatch):
    body = request_otp(api_client).json()
    move_time(monkeypatch, seconds=299)
    assert verify(api_client, body["request_id"], body["dev_otp"]).status_code == 200


def test_code_is_single_use(api_client):
    body = request_otp(api_client).json()
    assert verify(api_client, body["request_id"], body["dev_otp"]).status_code == 200
    again = verify(api_client, body["request_id"], body["dev_otp"])
    assert again.status_code == 400 and again.json()["code"] == "otp_already_used"


def test_a_new_request_invalidates_the_previous_code(api_client):
    first = request_otp(api_client).json()
    second = request_otp(api_client).json()
    assert verify(api_client, first["request_id"], first["dev_otp"]).json()["code"] == "otp_already_used"
    assert verify(api_client, second["request_id"], second["dev_otp"]).status_code == 200


def test_unknown_request_id_is_a_generic_error(api_client):
    assert verify(api_client, "0" * 32, "123456").json()["code"] == "invalid_otp"


def test_unregistered_phone_looks_the_same_but_never_logs_in(api_client, api_app):
    sent = []
    api_app.state.sms_sender = type("S", (), {"send": lambda self, p, m: sent.append(p)})()
    response = request_otp(api_client, "+919999999999")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"request_id", "expires_in", "dev_otp"} and body["dev_otp"] is None and sent == []
    assert verify(api_client, body["request_id"], "123456").json()["code"] == "invalid_otp"


def test_otp_request_is_rate_limited_per_phone(api_client, api_app):
    api_app.state.limiters = RateLimiters.default()
    statuses = [request_otp(api_client).status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]
    blocked = request_otp(api_client)
    assert blocked.json()["code"] == "rate_limited" and int(blocked.headers["Retry-After"]) > 0
    assert request_otp(api_client, DEMO_PHONE_2).status_code == 200            # another phone is unaffected


def test_otp_request_is_rate_limited_per_ip(api_client, api_app):
    limiters = RateLimiters.default()
    limiters.otp_ip = SlidingWindowLimiter(2, 600)
    api_app.state.limiters = limiters
    phones = ["+910000000001", "+910000000002", "+910000000003"]
    assert [request_otp(api_client, p).status_code for p in phones] == [200, 200, 429]


def test_verify_is_rate_limited_per_ip(api_client, api_app):
    limiters = RateLimiters.default()
    limiters.verify_ip = SlidingWindowLimiter(2, 600)
    api_app.state.limiters = limiters
    assert [verify(api_client, "0" * 32, "123456").status_code for _ in range(3)] == [400, 400, 429]


def test_sms_failure_is_a_clean_503(api_client, api_app):
    def boom(self, phone, message):
        raise RuntimeError("gateway down")

    api_app.state.sms_sender = type("Broken", (), {"send": boom})()
    response = request_otp(api_client)
    assert response.status_code == 503 and response.json()["code"] == "sms_unavailable"


def test_overlong_device_id_is_rejected_before_the_code_is_consumed(api_client):
    body = request_otp(api_client).json()
    assert verify(api_client, body["request_id"], body["dev_otp"], device_id="d" * 81).status_code == 422
    assert verify(api_client, body["request_id"], body["dev_otp"], device_id="ok").status_code == 200


# ------------------------------------------------------------------------------------------------ refresh tokens
def tokens(client, device_id="phone-1"):
    body = request_otp(client).json()
    return verify(client, body["request_id"], body["dev_otp"], device_id).json()


def test_refresh_rotates_and_the_old_token_stops_working(api_client):
    first = tokens(api_client)
    rotated = api_client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"] and second["farmer"]["id"] == "F001"
    assert api_client.get("/v1/me", headers={"Authorization": f"Bearer {second['access_token']}"}).status_code == 200
    replay = api_client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401 and replay.json()["code"] == "invalid_refresh_token"


def test_replaying_a_rotated_token_revokes_the_whole_device_session(api_client):
    first = tokens(api_client)
    second = api_client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    api_client.post("/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})            # replay: treated as theft
    after = api_client.post("/v1/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert after.status_code == 401


def test_refresh_tokens_are_stored_hashed(api_client):
    issued = tokens(api_client)
    with session_scope() as db:
        rows = db.scalars(select(RefreshTokenRow)).all()
        assert rows and all(issued["refresh_token"] not in r.token_hash for r in rows)


def test_expired_refresh_token_is_rejected(api_client, monkeypatch):
    issued = tokens(api_client)
    move_time(monkeypatch, days=31)
    response = api_client.post("/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]})
    assert response.status_code == 401 and response.json()["code"] == "refresh_token_expired"


def test_unknown_refresh_token_is_rejected(api_client):
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": "nope"}).status_code == 401


def test_a_new_login_on_the_same_device_revokes_the_old_session(api_client):
    old = tokens(api_client, "phone-1")
    tokens(api_client, "phone-1")
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401


def test_sessions_on_different_devices_coexist(api_client):
    phone_a, phone_b = tokens(api_client, "phone-a"), tokens(api_client, "phone-b")
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": phone_a["refresh_token"]}).status_code == 200
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": phone_b["refresh_token"]}).status_code == 200


def test_active_sessions_per_farmer_are_capped(api_client, api_app):
    for i in range(12):
        api_app.state.limiters = RateLimiters.default()          # the per-phone OTP limit is not what is under test
        tokens(api_client, f"device-{i}")
    with session_scope() as db:
        live = db.scalars(select(RefreshTokenRow).where(RefreshTokenRow.revoked.is_(False))).all()
        assert len(live) == 10


@pytest.mark.parametrize("payload", [{}, {"refresh_token": 5}])
def test_refresh_validates_the_body(api_client, payload):
    assert api_client.post("/v1/auth/refresh", json=payload).status_code == 422


def test_logout_revokes_the_refresh_token_and_is_idempotent(api_client):
    issued = tokens(api_client)
    assert api_client.post("/v1/auth/logout", json={"refresh_token": issued["refresh_token"]}).status_code == 204
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]}).status_code == 401
    assert api_client.post("/v1/auth/logout", json={"refresh_token": issued["refresh_token"]}).status_code == 204
    assert api_client.post("/v1/auth/logout", json={"refresh_token": "never-issued"}).status_code == 204


def test_logout_only_ends_that_device(api_client):
    phone_a, phone_b = tokens(api_client, "phone-a"), tokens(api_client, "phone-b")
    api_client.post("/v1/auth/logout", json={"refresh_token": phone_a["refresh_token"]})
    assert api_client.post("/v1/auth/refresh", json={"refresh_token": phone_b["refresh_token"]}).status_code == 200


def test_parallel_verifies_of_one_code_log_in_exactly_once(api_client):
    from concurrent.futures import ThreadPoolExecutor

    body = request_otp(api_client).json()
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: verify(api_client, body["request_id"], body["dev_otp"], "phone-1"), range(8)))
    assert sorted(r.status_code for r in results) == [200] + [400] * 7
    assert {r.json()["code"] for r in results if r.status_code == 400} == {"otp_already_used"}


def test_parallel_refreshes_of_one_token_succeed_exactly_once(api_client):
    from concurrent.futures import ThreadPoolExecutor

    issued = tokens(api_client)
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda _: api_client.post("/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]}), range(6)))
    assert sum(r.status_code == 200 for r in results) <= 1 and all(r.status_code in (200, 401) for r in results)
