"""Background jobs (APScheduler): the alert evaluator on the demo clock, Zoho write retries, daily photo retention.

Environment (read here, not in Settings):
  ALERT_INTERVAL_MINUTES  default 60
  ALERT_SCHEDULER         set to 0/false/off to disable everything (it is always disabled when ENV=test)
Jobs read `app.state.container` at run time (the platform sets it), use their own database session, and never let an exception
escape: a failed run is logged and the next one tries again. Run ONE uvicorn worker, otherwise every worker would run the jobs.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped,unused-ignore]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped,unused-ignore]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped,unused-ignore]
from sqlalchemy.orm import Session

from app.admin.clock_store import restore_demo_clock
from app.alerts.evaluator import run_once
from app.alerts.maintenance import purge_expired_photos, sync_unsynced_sprays
from app.clock import IST
from app.config import Settings, get_settings
from app.db.session import session_scope

log = logging.getLogger(__name__)

JOB_ID = "alert_evaluator"
SYNC_JOB_ID = "zoho_sync_retry"
PHOTO_JOB_ID = "photo_retention"
DEFAULT_INTERVAL_MINUTES = 60
SYNC_INTERVAL_MINUTES = 15
FIRST_RUN_DELAY_SECONDS = 30
PHOTO_PURGE_HOUR_IST = 3
_OFF = {"0", "false", "no", "off"}

_scheduler: BackgroundScheduler | None = None


def interval_minutes() -> int:
    try:
        return max(int(os.environ.get("ALERT_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES)), 1)
    except ValueError:
        return DEFAULT_INTERVAL_MINUTES


def scheduler_enabled(settings: Settings | None = None) -> bool:
    env = (settings or get_settings()).env
    return env != "test" and os.environ.get("ALERT_SCHEDULER", "1").strip().lower() not in _OFF


def _run_job(app: Any, name: str, job: Callable[[Session, Any], int]) -> int:
    container = getattr(app.state, "container", None)
    if container is None:
        log.warning("%s skipped: app.state.container is not set", name)
        return 0
    try:
        with session_scope() as session:
            count = job(session, container)
    except Exception:
        log.exception("%s failed", name)
        return 0
    log.info("%s finished: %d", name, count)
    return count


def run_now(app) -> int:  # noqa: ANN001
    """One alert evaluation pass; returns the number of new alerts. Used by the hourly job."""
    return _run_job(app, "alert run", lambda session, container: len(run_once(session, container)))


def run_zoho_sync(app) -> int:  # noqa: ANN001
    return _run_job(app, "zoho sync retry", sync_unsynced_sprays)


def run_photo_retention(app) -> int:  # noqa: ANN001
    return _run_job(app, "photo retention", purge_expired_photos)


def start_scheduler(app=None) -> None:  # noqa: ANN001
    """Restore the persisted demo clock, then start the jobs unless the scheduler is disabled. Never raises."""
    global _scheduler
    settings = (getattr(app.state, "settings", None) if app is not None else None) or get_settings()
    restore_demo_clock(allow_fixed=not settings.is_prod or settings.allow_demo_clock_in_prod)
    if app is None or _scheduler is not None or not scheduler_enabled(settings):
        return
    scheduler = BackgroundScheduler(timezone=IST)
    common: dict[str, Any] = {"args": [app], "max_instances": 1, "coalesce": True, "misfire_grace_time": 300}
    try:
        scheduler.add_job(run_now, IntervalTrigger(minutes=interval_minutes(), timezone=IST), id=JOB_ID,
                          next_run_time=datetime.now(IST) + timedelta(seconds=FIRST_RUN_DELAY_SECONDS), **common)
        scheduler.add_job(run_zoho_sync, IntervalTrigger(minutes=SYNC_INTERVAL_MINUTES, timezone=IST), id=SYNC_JOB_ID, **common)
        scheduler.add_job(run_photo_retention, CronTrigger(hour=PHOTO_PURGE_HOUR_IST, minute=30, timezone=IST), id=PHOTO_JOB_ID,
                          **common)
        scheduler.start()
    except Exception:
        log.exception("the scheduler could not be started: no automatic alerts until the next restart")
        return
    _scheduler = scheduler
    log.info("scheduler started: alerts every %d minutes, zoho retry every %d, photo retention daily", interval_minutes(),
             SYNC_INTERVAL_MINUTES)


def stop_scheduler() -> None:
    global _scheduler
    scheduler, _scheduler = _scheduler, None
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("scheduler stopped")
