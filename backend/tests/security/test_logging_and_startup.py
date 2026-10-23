import json
import logging

import pytest

from app.main import create_app
from app.security.logging import (
    JsonFormatter,
    RedactingFilter,
    configure_logging,
    redact_text,
    request_id_var,
)
from app.security.startup import InsecureConfigurationError, validate_production_settings
from tests.fakes import plain_settings

GOOD_PROD = dict(env="prod", secret_key="k" * 40, admin_api_key="a" * 24, cors_origins=["https://farm.example"])


# ------------------------------------------------------------------------------------------------ redaction
@pytest.mark.parametrize("text,secret", [
    ("login for +91 00000 00001 ok", "00000 00001"),
    ("login for +910000000001 ok", "910000000001"),
    ("phone 9000000001 requested", "9000000001"),
    ("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJGMDAxIn0.abc123def456 used", "eyJhbGci"),
    ("Authorization: Bearer abc.DEF-123_xyz", "abc.DEF-123_xyz"),
    ("otp=123456 wrong", "123456"),
    ("code: 654321", "654321"),
    ("x-admin-key=supersecretvalue", "supersecretvalue"),
])
def test_redact_text_removes_sensitive_values(text, secret):
    assert secret not in redact_text(text)


def test_redact_text_keeps_ordinary_numbers_and_dates():
    text = "scan=0194f3 status=ok photos=3 at 2026-05-12 08:00 duration_ms=12.5"
    assert redact_text(text) == text


def make_record(msg, *args, **extra):
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, msg, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_filter_redacts_message_args_and_extra_fields():
    record = make_record("sent to %s", "+910000000001", phone="+910000000001", refresh_token="abc", note="call 9000000001", status=200)
    assert RedactingFilter().filter(record)
    assert "910000000001" not in record.getMessage()
    assert record.phone == "[redacted]" and record.refresh_token == "[redacted]"
    assert "9000000001" not in record.note and record.status == 200


def test_json_formatter_output_is_valid_json_with_request_id_and_no_pii():
    token = request_id_var.set("req-12345678")
    try:
        record = make_record("farmer %s asked", "+910000000001", question="how to spray apple?")
        line = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)
    data = json.loads(line)
    assert data["request_id"] == "req-12345678" and data["level"] == "INFO"
    assert data["question"] == "[redacted]"
    assert "910000000001" not in line


def test_exception_text_is_redacted():
    try:
        raise RuntimeError("failed for +910000000001")
    except RuntimeError:
        import sys

        record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "boom", (), sys.exc_info())
    assert "910000000001" not in JsonFormatter().format(record)


def test_configure_logging_is_idempotent_and_leaves_root_alone():
    root_handlers = list(logging.getLogger().handlers)
    configure_logging(plain_settings())
    configure_logging(plain_settings())
    handlers = [h for h in logging.getLogger("app").handlers if getattr(h, "_farmtrack", False)]
    assert len(handlers) == 1
    assert list(logging.getLogger().handlers) == root_handlers


# ------------------------------------------------------------------------------------------------ production guard
def test_guard_is_a_no_op_outside_prod():
    for env in ("dev", "test"):
        validate_production_settings(plain_settings(env=env))


def test_guard_accepts_a_proper_production_configuration():
    validate_production_settings(plain_settings(**GOOD_PROD))


@pytest.mark.parametrize("override,fragment", [
    ({"secret_key": "dev-only-change-me"}, "SECRET_KEY"),
    ({"secret_key": "short"}, "SECRET_KEY"),
    ({"admin_api_key": "dev-admin-key"}, "ADMIN_API_KEY"),
    ({"admin_api_key": "tiny"}, "ADMIN_API_KEY"),
    ({"cors_origins": ["*"]}, "CORS_ORIGINS"),
    ({"cors_origins": ["https://farm.example", "*"]}, "CORS_ORIGINS"),
    ({"demo_disease_hints": "Apple=Apple___Apple_scab:0.9"}, "DEMO_DISEASE_HINTS"),
    ({"demo_disease_hints": "not even a valid entry"}, "DEMO_DISEASE_HINTS"),
])
def test_guard_refuses_each_unsafe_setting(override, fragment):
    with pytest.raises(InsecureConfigurationError) as caught:
        validate_production_settings(plain_settings(**{**GOOD_PROD, **override}))
    assert fragment in str(caught.value)


def test_demo_disease_hints_are_fine_outside_production_and_blank_in_production():
    validate_production_settings(plain_settings(env="dev", demo_disease_hints="Apple=Apple___Apple_scab"))
    validate_production_settings(plain_settings(**GOOD_PROD, demo_disease_hints="   "))
    validate_production_settings(plain_settings(**GOOD_PROD, demo_disease_hints=None))


def test_create_app_refuses_to_start_in_production_with_demo_hints():
    with pytest.raises(InsecureConfigurationError, match="DEMO_DISEASE_HINTS"):
        create_app(plain_settings(**GOOD_PROD, demo_disease_hints="Apple=Apple___Apple_scab"))


def test_guard_lists_every_problem_at_once():
    with pytest.raises(InsecureConfigurationError) as caught:
        validate_production_settings(plain_settings(env="prod"))                 # all three defaults
    message = str(caught.value)
    assert "SECRET_KEY" in message and "ADMIN_API_KEY" in message and "CORS_ORIGINS" in message


def test_create_app_refuses_to_start_with_unsafe_prod_settings():
    with pytest.raises(InsecureConfigurationError):
        create_app(plain_settings(env="prod"))
    assert create_app(plain_settings(**GOOD_PROD)).title == "FarmTrack API"


def test_prod_app_hides_the_api_docs():
    from fastapi.testclient import TestClient

    client = TestClient(create_app(plain_settings(**GOOD_PROD)), raise_server_exceptions=False)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
