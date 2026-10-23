"""Access tokens (JWT, HS256) and opaque refresh tokens.

Signing and hashing keys are derived from settings.secret_key per purpose (HMAC), so a leak of one derived value does not give the
others and the HS256 key is always 32 bytes. Expiry is checked against REAL time (security.timeutil), never the demo clock.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

import jwt

from app.config import Settings
from app.security import timeutil
from app.security.errors import ApiError

ALGORITHM = "HS256"
ACCESS_TYPE = "access"


def derive_key(secret_key: str, purpose: str) -> bytes:
    return hmac.new(secret_key.encode("utf-8"), f"farmtrack:{purpose}".encode(), hashlib.sha256).digest()


def create_access_token(settings: Settings, farmer_id: str) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    now = timeutil.utcnow()
    expires = now + timedelta(minutes=settings.access_token_minutes)
    claims = {"sub": farmer_id, "typ": ACCESS_TYPE, "iat": int(now.timestamp()), "exp": int(expires.timestamp())}
    token = jwt.encode(claims, derive_key(settings.secret_key, "jwt"), algorithm=ALGORITHM)
    return token, settings.access_token_minutes * 60


def decode_access_token(settings: Settings, token: str) -> str:
    """Return the farmer id or raise ApiError(401). Only HS256 is accepted (no alg=none, no algorithm confusion)."""
    try:
        claims = jwt.decode(token, derive_key(settings.secret_key, "jwt"), algorithms=[ALGORITHM],
                            options={"require": ["exp", "sub", "iat"], "verify_exp": False})
    except jwt.PyJWTError as exc:
        raise _unauthorized("invalid_token", "Your session is not valid. Please log in again.") from exc
    if claims.get("typ") != ACCESS_TYPE or not isinstance(claims.get("sub"), str):
        raise _unauthorized("invalid_token", "Your session is not valid. Please log in again.")
    if timeutil.utcnow().timestamp() >= float(claims["exp"]):
        raise _unauthorized("token_expired", "Your session has expired.")
    return claims["sub"]


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(settings: Settings, token: str) -> str:
    return hmac.new(derive_key(settings.secret_key, "refresh"), token.encode(), hashlib.sha256).hexdigest()


def _unauthorized(code: str, message: str) -> ApiError:
    return ApiError(401, code, message, headers={"WWW-Authenticate": "Bearer"})
