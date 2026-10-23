"""Review findings: an unknown ENV name must not switch production safety off, and production must never run on the frozen demo date."""
from datetime import datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.admin import service
from app.admin.clock_store import restore_demo_clock, save_demo_clock
from app.clock import IST, Clock, get_clock
from app.config import Settings
from app.db.session import get_session_factory, init_db
from app.security.otp import dev_fixed_code
from app.security.startup import InsecureConfigurationError, validate_production_settings

GOOD = dict(secret_key="s" * 40, admin_api_key="a" * 24, cors_origins=["https://farm.example"])


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


# ------------------------------------------------------------------------------------------------ ENV names
@pytest.mark.parametrize("name", ["prod", "PROD", " Prod ", "production", "Production", "staging", "preprod", "uat"])
def test_every_spelling_of_production_is_production(name):
    s = settings(env=name)
    assert s.env == "prod" and s.is_prod
    assert dev_fixed_code(s) is None                                  # the fixed development login code is never honoured


@pytest.mark.parametrize("name,expected", [("dev", "dev"), ("DEV", "dev"), ("development", "dev"), ("test", "test"), ("local", "dev")])
def test_development_names_stay_development(name, expected):
    assert settings(env=name).env == expected


@pytest.mark.parametrize("name", ["", "prodd", "live", "qa", "none"])
def test_an_unknown_environment_name_is_refused_not_treated_as_development(name):
    with pytest.raises(ValueError, match="ENV must be one of: dev, test, prod"):
        settings(env=name)


def test_the_environment_variable_goes_through_the_same_check(monkeypatch):
    monkeypatch.setenv("ENV", "Production")
    assert Settings(_env_file=None).is_prod  # type: ignore[call-arg]
    monkeypatch.setenv("ENV", "live")
    with pytest.raises(ValueError, match="ENV must be one of: dev, test, prod"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_a_misspelled_production_cannot_log_in_with_the_development_code():
    from tests.fakes import plain_settings

    s = plain_settings(env="Production", dev_fixed_otp="123456")
    assert dev_fixed_code(s) is None
    with pytest.raises(InsecureConfigurationError):
        validate_production_settings(s)                                # and the start-up guards run for it


# ------------------------------------------------------------------------------------------------ the clock in production
def test_production_without_a_demo_clock_uses_the_real_clock():
    assert settings(env="prod").demo_clock is None                      # the built-in default (the demo day) never applies in prod
    assert settings(env="dev").demo_clock == "2026-05-12T08:00:00+05:30"


def test_production_refuses_a_fixed_demo_clock_unless_explicitly_allowed():
    with pytest.raises(InsecureConfigurationError, match="DEMO_CLOCK"):
        validate_production_settings(settings(env="prod", demo_clock="2026-05-12T08:00:00+05:30", **GOOD))
    validate_production_settings(settings(env="prod", demo_clock="2026-05-12T08:00:00+05:30", allow_demo_clock_in_prod=True, **GOOD))
    validate_production_settings(settings(env="prod", demo_clock="", **GOOD))                      # DEMO_CLOCK= (empty) is the real clock
    validate_production_settings(settings(env="prod", **GOOD))


def test_the_clock_in_a_production_app_is_the_real_one(monkeypatch):
    from app.clock import reset_clock
    from app.config import get_settings

    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()
    reset_clock()
    assert get_clock().is_fixed is False


def test_the_admin_cannot_fix_the_clock_in_production_but_can_clear_it():
    init_db()
    db = get_session_factory()()
    clock = Clock()
    with pytest.raises(HTTPException) as caught:
        service.set_demo_clock(db, clock, datetime(2026, 5, 12, 8, 0, tzinfo=IST), allow_fixed=False)
    assert caught.value.status_code == 409 and clock.is_fixed is False
    assert service.set_demo_clock(db, clock, None, allow_fixed=False).fixed is False
    assert service.set_demo_clock(db, clock, datetime(2026, 5, 12, 8, 0, tzinfo=IST)).fixed is True      # dev: still allowed
    db.close()


def test_the_admin_endpoints_apply_the_production_rule():
    from fastapi import FastAPI

    from app.admin.router import router
    from app.api.deps import get_db, require_admin

    init_db()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: None

    def session_per_request():
        session = get_session_factory()()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = session_per_request
    app.state.settings = settings(env="prod")
    with TestClient(app) as client:
        refused = client.put("/admin/api/v1/settings/demo-clock", json={"now": "2026-05-12T08:00:00+05:30"})
        assert refused.status_code == 409 and "production" in refused.text
        assert client.put("/admin/api/v1/settings/demo-clock", json={"now": None}).status_code == 200
        app.state.settings = settings(env="prod", allow_demo_clock_in_prod=True)
        assert client.put("/admin/api/v1/settings/demo-clock", json={"now": "2026-05-12T08:00:00+05:30"}).status_code == 200


def test_a_stored_fixed_clock_is_not_restored_in_production():
    init_db()
    with get_session_factory()() as db:
        save_demo_clock(db, datetime(2026, 7, 1, 9, 0, tzinfo=IST))
        db.commit()
    get_clock().set(None)
    assert restore_demo_clock(allow_fixed=False) is False and get_clock().is_fixed is False
    assert restore_demo_clock(allow_fixed=True) is True and get_clock().now() == datetime(2026, 7, 1, 9, 0, tzinfo=IST)
