"""SMS delivery behind an interface.

TODO(production): implement a real provider (an Indian gateway with a TRAI DLT-registered OTP template) and pass it to
create_app(sms_sender=...). LogSmsSender only records that a message was queued: it never logs the phone number or the code.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class SmsSender(Protocol):
    def send(self, phone: str, message: str) -> None:
        """Deliver `message` to `phone` (normalised '+91...'). Raise on failure."""
        ...


class LogSmsSender:
    """Development sender: no network, no PII in the log. The dev OTP is returned in the API response instead."""

    def send(self, phone: str, message: str) -> None:
        logger.info("sms queued (log sender, nothing delivered) length=%d", len(message))
