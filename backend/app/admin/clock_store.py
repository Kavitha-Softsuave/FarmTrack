"""Persistence of the admin-set demo clock (AppSettingRow 'demo_clock') and its application to app.clock."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.clock import IST, Clock, get_clock
from app.db.models import AppSettingRow
from app.db.session import session_scope

log = logging.getLogger(__name__)

KEY = "demo_clock"


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=IST) if value.tzinfo is None else value


def save_demo_clock(session: Session, value: datetime | None) -> None:
    """value=None stores 'use the real clock', which also overrides the DEMO_CLOCK default on the next start."""
    payload = {"now": _aware(value).isoformat() if value is not None else None}
    row = session.get(AppSettingRow, KEY)
    if row is None:
        session.add(AppSettingRow(key=KEY, value=payload))
    else:
        row.value = payload


def load_demo_clock(session: Session) -> tuple[bool, datetime | None]:
    """(has_override, value). has_override is False when the admin never touched the clock."""
    row = session.get(AppSettingRow, KEY)
    if row is None:
        return False, None
    raw = (row.value or {}).get("now")
    return True, (_aware(datetime.fromisoformat(raw)) if raw else None)


def apply_demo_clock(clock: Clock, value: datetime | None) -> None:
    clock.set(value)


def restore_demo_clock(allow_fixed: bool = True) -> bool:
    """Apply the stored override to the process-wide clock at start-up. Never raises: a missing table or database is only logged.

    `allow_fixed` False (production): a stored FIXED date is ignored, so a demo date saved earlier cannot freeze the real service.
    """
    try:
        with session_scope() as session:
            has_override, value = load_demo_clock(session)
        if has_override and value is not None and not allow_fixed:
            log.warning("a stored demo clock is ignored in production (ALLOW_DEMO_CLOCK_IN_PROD=1 would apply it)")
            return False
        if has_override:
            apply_demo_clock(get_clock(), value)
        return has_override
    except Exception as exc:
        log.warning("demo clock not restored from the database: %s", type(exc).__name__)
        return False
