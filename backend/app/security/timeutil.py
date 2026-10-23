"""Real wall-clock time for security decisions.

OTP expiry, refresh-token expiry and rate limits must use REAL time. The demo clock (app.clock) is frozen on purpose, so using it
here would make an OTP valid forever. Tests monkeypatch `timeutil.utcnow` to move time.
"""
from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo: security tables store UTC, so a naive value read back is UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
