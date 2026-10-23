"""One-time password primitives. Only a peppered SHA-256 hash is ever stored; the code itself exists only in the SMS."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from app.config import Settings
from app.security.tokens import derive_key

OTP_DIGITS = 6
_DIGITS_RE = re.compile(r"^[0-9]{4,8}$")


def generate_code() -> str:
    return f"{secrets.randbelow(10**OTP_DIGITS):0{OTP_DIGITS}d}"


def dev_fixed_code(settings: Settings) -> str | None:
    """The fixed development code, only outside production and only when it is a valid OTP shape."""
    code = settings.dev_fixed_otp
    if settings.is_prod or not code or not _DIGITS_RE.match(code):
        return None
    return code


def hash_otp(settings: Settings, request_id: str, code: str) -> str:
    pepper = derive_key(settings.secret_key, "otp-pepper").hex()
    return hashlib.sha256(f"{pepper}:{request_id}:{code}".encode()).hexdigest()


def otp_matches(settings: Settings, request_id: str, code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(settings, request_id, code), stored_hash)
