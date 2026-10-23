from datetime import timedelta

import jwt
import pytest

from app.security import timeutil
from app.security.errors import ApiError
from app.security.tokens import (
    create_access_token,
    decode_access_token,
    derive_key,
    hash_refresh_token,
    new_refresh_token,
)
from tests.fakes import plain_settings as Settings  # noqa: N813

SETTINGS = Settings(secret_key="s" * 40, access_token_minutes=10)


def test_round_trip_returns_the_farmer_id():
    token, expires_in = create_access_token(SETTINGS, "F001")
    assert expires_in == 600
    assert decode_access_token(SETTINGS, token) == "F001"


def test_expired_token_is_rejected_using_real_time(monkeypatch):
    token, _ = create_access_token(SETTINGS, "F001")
    later = timeutil.utcnow() + timedelta(minutes=11)
    monkeypatch.setattr(timeutil, "utcnow", lambda: later)
    with pytest.raises(ApiError) as caught:
        decode_access_token(SETTINGS, token)
    assert caught.value.status_code == 401 and caught.value.code == "token_expired"


def test_tampered_and_foreign_tokens_are_rejected():
    token, _ = create_access_token(SETTINGS, "F001")
    other = Settings(secret_key="o" * 40)
    for bad in (token[:-3] + "abc", create_access_token(other, "F001")[0], "not-a-jwt", ""):
        with pytest.raises(ApiError) as caught:
            decode_access_token(SETTINGS, bad)
        assert caught.value.status_code == 401


@pytest.mark.filterwarnings("ignore:The HMAC key")
def test_alg_none_and_wrong_algorithm_are_rejected():
    now = int(timeutil.utcnow().timestamp())
    claims = {"sub": "F001", "typ": "access", "iat": now, "exp": now + 600}
    unsigned = jwt.encode(claims, key="", algorithm="none")
    hs512 = jwt.encode(claims, derive_key(SETTINGS.secret_key, "jwt"), algorithm="HS512")
    for bad in (unsigned, hs512):
        with pytest.raises(ApiError):
            decode_access_token(SETTINGS, bad)


def test_token_without_required_claims_or_wrong_type_is_rejected():
    key = derive_key(SETTINGS.secret_key, "jwt")
    now = int(timeutil.utcnow().timestamp())
    for claims in ({"sub": "F001", "iat": now}, {"typ": "access", "iat": now, "exp": now + 60},
                   {"sub": "F001", "typ": "refresh", "iat": now, "exp": now + 60}):
        with pytest.raises(ApiError):
            decode_access_token(SETTINGS, jwt.encode(claims, key, algorithm="HS256"))


def test_secret_is_not_used_directly_as_the_signing_key():
    token, _ = create_access_token(SETTINGS, "F001")
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, SETTINGS.secret_key, algorithms=["HS256"])


def test_refresh_tokens_are_random_and_stored_as_keyed_hashes():
    a, b = new_refresh_token(), new_refresh_token()
    assert a != b and len(a) >= 60
    digest = hash_refresh_token(SETTINGS, a)
    assert a not in digest and digest == hash_refresh_token(SETTINGS, a)
    assert digest != hash_refresh_token(Settings(secret_key="x" * 40), a)
