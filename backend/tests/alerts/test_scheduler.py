import logging
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI

from app.alerts import scheduler
from app.clock import IST, get_clock
from app.config import get_settings
from app.db.models import AlertRow, AppSettingRow
from app.db.session import session_scope
from tests.integrations.fakes import FakeRules, FakeZoho, farmer_row, make_container, make_settings, risk


@pytest.fixture
def dev_env(monkeypatch):
    """The root conftest sets ENV=test, which disables the scheduler: pretend to be a dev server."""
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("ALERT_SCHEDULER", raising=False)
    monkeypatch.delenv("ALERT_INTERVAL_MINUTES", raising=False)
    get_settings.cache_clear()
    yield
    scheduler.stop_scheduler()


def make_app(tmp_path, rules=None) -> FastAPI:
    app = FastAPI()
    app.state.container = make_container(tmp_path, rules=rules or FakeRules())
    return app


def seed_farmer(db) -> None:
    db.add(farmer_row("F901"))
    db.commit()


# ------------------------------------------------------------------------------------------------- configuration
def test_disabled_in_the_test_environment():
    assert get_settings().env == "test" and scheduler.scheduler_enabled() is False


def test_enabled_for_dev_and_switchable_with_an_env_var(dev_env, monkeypatch):
    assert scheduler.scheduler_enabled() is True
    for off in ("0", "false", "OFF", " no "):
        monkeypatch.setenv("ALERT_SCHEDULER", off)
        assert scheduler.scheduler_enabled() is False, off
    monkeypatch.setenv("ALERT_SCHEDULER", "1")
    assert scheduler.scheduler_enabled() is True


@pytest.mark.parametrize("raw,expected", [(None, 60), ("15", 15), ("abc", 60), ("0", 1), ("-5", 1), (" 30 ", 30)])
def test_interval_from_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("ALERT_INTERVAL_MINUTES", raising=False)
    else:
        monkeypatch.setenv("ALERT_INTERVAL_MINUTES", raw)
    assert scheduler.interval_minutes() == expected


# ------------------------------------------------------------------------------------------------- start and stop
def test_start_and_stop(dev_env, tmp_path, monkeypatch):
    monkeypatch.setenv("ALERT_INTERVAL_MINUTES", "15")
    app = make_app(tmp_path)
    scheduler.start_scheduler(app)
    running = scheduler._scheduler
    assert running is not None and running.running
    job = running.get_job(scheduler.JOB_ID)
    assert job is not None and job.trigger.interval == timedelta(minutes=15) and job.max_instances == 1
    assert {j.id for j in running.get_jobs()} == {scheduler.JOB_ID, scheduler.SYNC_JOB_ID, scheduler.PHOTO_JOB_ID}
    assert running.get_job(scheduler.SYNC_JOB_ID).trigger.interval == timedelta(minutes=15)
    assert "hour='3'" in str(running.get_job(scheduler.PHOTO_JOB_ID).trigger)
    scheduler.start_scheduler(app)                                          # a second start does not add a second scheduler
    assert scheduler._scheduler is running
    scheduler.stop_scheduler()
    assert scheduler._scheduler is None and not running.running
    scheduler.stop_scheduler()                                              # stopping twice is harmless


def test_default_interval_is_hourly(dev_env, tmp_path):
    scheduler.start_scheduler(make_app(tmp_path))
    assert scheduler._scheduler.get_job(scheduler.JOB_ID).trigger.interval == timedelta(minutes=60)


def test_nothing_starts_in_the_test_environment_or_when_disabled(tmp_path, monkeypatch):
    scheduler.start_scheduler(make_app(tmp_path))
    assert scheduler._scheduler is None
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ALERT_SCHEDULER", "0")
    get_settings.cache_clear()
    scheduler.start_scheduler(make_app(tmp_path))
    assert scheduler._scheduler is None


def test_the_apps_own_settings_decide_whether_the_scheduler_runs(dev_env, tmp_path):
    app = make_app(tmp_path)
    app.state.settings = make_settings(tmp_path, env="test")               # get_settings() says dev, the app says test
    scheduler.start_scheduler(app)
    assert scheduler._scheduler is None
    app.state.settings = make_settings(tmp_path, env="dev")
    scheduler.start_scheduler(app)
    assert scheduler._scheduler is not None


def test_a_scheduler_that_cannot_start_never_crashes_the_app(dev_env, tmp_path, monkeypatch, caplog):
    def refuse(self):
        raise RuntimeError("no threads")

    monkeypatch.setattr(scheduler.BackgroundScheduler, "start", refuse)
    with caplog.at_level(logging.ERROR, logger="app.alerts.scheduler"):
        scheduler.start_scheduler(make_app(tmp_path))
    assert scheduler._scheduler is None and "could not be started" in caplog.text


def test_start_without_an_app_is_a_no_op(dev_env):
    scheduler.start_scheduler(None)
    assert scheduler._scheduler is None


def test_lifespan_hooks_start_and_stop_the_scheduler(dev_env, tmp_path):
    """Same wiring as app.main: start_scheduler(app) on start-up, stop_scheduler() on shutdown."""
    from contextlib import asynccontextmanager

    from fastapi.testclient import TestClient

    @asynccontextmanager
    async def lifespan(app):
        scheduler.start_scheduler(app)
        yield
        scheduler.stop_scheduler()

    app = FastAPI(lifespan=lifespan)
    app.state.container = make_container(tmp_path)
    with TestClient(app):
        assert scheduler._scheduler is not None and scheduler._scheduler.running
    assert scheduler._scheduler is None


# ------------------------------------------------------------------------------------------------- the job
def test_run_now_evaluates_with_its_own_session(db, tmp_path):
    seed_farmer(db)
    app = make_app(tmp_path, FakeRules([risk("scab_infection_risk", episode="2026-05-04")]))
    assert scheduler.run_now(app) == 1
    assert scheduler.run_now(app) == 0                                      # idempotent
    with session_scope() as session:
        assert session.query(AlertRow).count() == 1


def test_zoho_retry_and_photo_retention_jobs_run_through_the_same_guard(db, tmp_path, caplog):
    from datetime import timedelta

    from tests.integrations.fakes import NOW, spray_log_row

    seed_farmer(db)
    db.add(spray_log_row("F901", NOW - timedelta(days=1), product_id="P001", synced_to_zoho=False))
    db.commit()
    app = make_app(tmp_path)
    app.state.container.zoho = FakeZoho()
    assert scheduler.run_zoho_sync(app) == 1
    assert scheduler.run_zoho_sync(app) == 0
    assert scheduler.run_photo_retention(app) == 0
    with caplog.at_level(logging.WARNING, logger="app.alerts.scheduler"):
        assert scheduler.run_zoho_sync(FastAPI()) == 0 and scheduler.run_photo_retention(FastAPI()) == 0
    assert caplog.text.count("container is not set") == 2


def test_run_now_without_a_container_is_skipped(caplog):
    with caplog.at_level(logging.WARNING, logger="app.alerts.scheduler"):
        assert scheduler.run_now(FastAPI()) == 0
    assert "container" in caplog.text


def test_a_failing_run_is_logged_and_never_raises(db, tmp_path, monkeypatch, caplog):
    seed_farmer(db)

    def explode(session, container, now=None):
        raise RuntimeError("database gone")

    monkeypatch.setattr(scheduler, "run_once", explode)
    with caplog.at_level(logging.ERROR, logger="app.alerts.scheduler"):
        assert scheduler.run_now(make_app(tmp_path)) == 0
    assert "alert run failed" in caplog.text


# ------------------------------------------------------------------------------------------------- demo clock restore
def test_start_restores_the_persisted_demo_clock(db, tmp_path):
    db.add(AppSettingRow(key="demo_clock", value={"now": "2026-07-12T09:00:00+05:30"}))
    db.commit()
    scheduler.start_scheduler(make_app(tmp_path))                           # disabled in tests, but the clock is still restored
    assert get_clock().now() == datetime(2026, 7, 12, 9, 0, tzinfo=IST)


def test_a_stored_real_clock_overrides_the_default_demo_clock(db, tmp_path):
    assert get_clock().is_fixed is True                                    # DEMO_CLOCK default from settings
    db.add(AppSettingRow(key="demo_clock", value={"now": None}))
    db.commit()
    scheduler.start_scheduler(make_app(tmp_path))
    assert get_clock().is_fixed is False


def test_start_without_a_database_table_does_not_crash(tmp_path):
    scheduler.start_scheduler(make_app(tmp_path))                           # no init_db(): the table is missing
    assert get_clock().is_fixed is True
