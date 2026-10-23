"""Demo clock. It is October, but the demo season is Mar-Oct 2026, so the app runs on a configurable 'now'.

Weather and sensor data after the clock are served from the archive as a 'perfect forecast'.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class Clock:
    def __init__(self, fixed: datetime | None = None) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed if self._fixed else datetime.now(IST)

    def set(self, value: datetime | None) -> None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=IST)
        self._fixed = value

    @property
    def is_fixed(self) -> bool:
        return self._fixed is not None


_clock: Clock | None = None


def get_clock() -> Clock:
    """Process-wide clock, initialised from settings.demo_clock on first use."""
    global _clock
    if _clock is None:
        from app.config import get_settings

        raw = get_settings().demo_clock
        _clock = Clock(datetime.fromisoformat(raw) if raw else None)
    return _clock


def reset_clock() -> None:
    global _clock
    _clock = None
