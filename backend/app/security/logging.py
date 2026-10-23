"""Structured JSON logging with PII redaction.

Rules for log statements in this code base: log ids, counts, statuses and durations; never a phone number, OTP, token, or the text of a
farmer's question. The redaction below is a safety net for accidents, not a licence to log those values.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REDACTED = "[redacted]"
_SENSITIVE_KEYS = ("phone", "otp", "token", "authorization", "password", "secret", "api_key", "apikey", "question", "x-admin-key")
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"), "[token]"),                  # JWT
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [token]"),
    (re.compile(r"(?i)\b(otp|code|token|secret|password|api[_-]?key|x-admin-key)\b(\s*[=:]\s*)\S+"), rf"\1\2{REDACTED}"),
    (re.compile(r"\+\d[\d\s-]{8,}\d"), "[phone]"),                                                          # +91 00000 00001
    (re.compile(r"(?<!\d)\d{10,13}(?!\d)"), "[phone]"),                                                     # 9000000001
)
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "request_id", "taskName"}


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_value(key: str, value: Any) -> Any:
    if any(s in key.lower() for s in _SENSITIVE_KEYS):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    return value


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RedactingFilter(logging.Filter):
    """Redacts the message and every `extra=` field of a record before any handler formats it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        for key in set(vars(record)) - _STANDARD_ATTRS:
            setattr(record, key, _redact_value(key, getattr(record, key)))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
        }
        for key in set(vars(record)) - _STANDARD_ATTRS:
            payload[key] = _redact_value(key, getattr(record, key))
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))[:4000]
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(settings: Settings) -> None:
    """Attach one JSON stderr handler to the `app` logger namespace (idempotent). The root logger is left alone."""
    logger = logging.getLogger("app")
    for handler in list(logger.handlers):
        if getattr(handler, "_farmtrack", False):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler._farmtrack = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO if settings.is_prod else logging.DEBUG)
