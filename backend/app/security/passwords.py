"""Username and password handling for the farmer login (stdlib only, no extra dependency).

Passwords are never stored: only `pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>` (PBKDF2-HMAC-SHA256, random 16-byte salt per
password). The iteration count is part of the stored string, so it can be raised later without invalidating old hashes.
Verification uses hmac.compare_digest. An unknown user is checked against a throw-away hash of the same cost, so a wrong username
and a wrong password take about the same time.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from functools import lru_cache

ALGORITHM = "pbkdf2_sha256"
PRODUCTION_ITERATIONS = 210_000                    # >= 150k as the owner asked; tests lower DEFAULT_ITERATIONS for speed
DEFAULT_ITERATIONS = PRODUCTION_ITERATIONS
MAX_ITERATIONS = 5_000_000                         # a corrupt or hostile row must not make one login burn minutes of CPU
SALT_BYTES = 16
KEY_BYTES = 32

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{3,40}$")
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128                          # only a guard against absurd input; there are no composition rules


def normalize_username(raw: str) -> str | None:
    """Lower-case, trimmed username when it is valid (3-40 characters of a-z 0-9 . _ -), else None."""
    name = raw.strip().lower()
    return name if USERNAME_PATTERN.fullmatch(name) else None


def password_problem(password: str) -> str | None:
    """Why the password is not acceptable, or None. The only rule is the length."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"The password must have at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"The password must have at most {MAX_PASSWORD_LENGTH} characters."
    return None


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=KEY_BYTES)


def hash_password(password: str, iterations: int | None = None) -> str:
    rounds = iterations or DEFAULT_ITERATIONS
    salt = secrets.token_bytes(SALT_BYTES)
    return f"{ALGORITHM}${rounds}${salt.hex()}${_derive(password, salt, rounds).hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """True when `password` matches the stored hash. A missing or malformed hash never matches (and never raises)."""
    if not stored:
        return False
    try:
        algorithm, rounds_text, salt_hex, hash_hex = stored.split("$")
        rounds = int(rounds_text)
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(hash_hex)
    except ValueError:
        return False
    if algorithm != ALGORITHM or not 1 <= rounds <= MAX_ITERATIONS or not expected:
        return False
    return hmac.compare_digest(_derive(password, salt, rounds), expected)


@lru_cache(maxsize=4)
def _decoy_hash(iterations: int) -> str:
    return hash_password(secrets.token_urlsafe(16), iterations)


def burn_password_check(password: str) -> None:
    """Spend the time of one verification (used when there is no real hash to compare, to keep the timing alike)."""
    verify_password(password, _decoy_hash(DEFAULT_ITERATIONS))
