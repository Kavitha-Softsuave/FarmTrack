"""FastAPI application factory.

`create_app` is the single wiring point. Everything a test or the integration step may want to swap is a parameter:
  settings         defaults to get_settings()
  container_factory builds the provider Container at startup (default: services.container.build_container); a test passes a
                   function returning fakes, or sets `app.state.container` before the lifespan runs and the factory is skipped
  sms_sender       OTP delivery (default: LogSmsSender; production needs a real provider, see docs/design-notes/platform.md)
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.alerts.scheduler import start_scheduler, stop_scheduler
from app.api.routes import alerts, ask, auth, devices, field, me, meta, scans, spray, voice
from app.config import Settings, get_settings
from app.db.migrate import ensure_schema
from app.db.seed import seed_if_enabled
from app.db.session import init_db
from app.security.errors import register_exception_handlers
from app.security.logging import configure_logging
from app.security.middleware import (
    AccessLogMiddleware,
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.security.ratelimit import RateLimiters
from app.security.sms import LogSmsSender, SmsSender
from app.security.startup import validate_production_settings
from app.services.container import Container, build_container
from app.services.expert_release import release_advice

logger = logging.getLogger(__name__)

ContainerFactory = Callable[[Settings], Container]


def _warm_up_models_in_background(settings: Settings) -> None:
    """Load the vision models right after start-up so the first farmer's scan is not the one that waits (10-30 s).
    Only when a real model provider is switched on; never under test; a failure is logged and the scan falls back as before."""
    if settings.env == "test" or "model" not in (settings.crop_id_provider, settings.disease_provider):
        return

    def work() -> None:
        try:
            from app.vision.factory import warm_up_models

            warm_up_models(settings)
            logger.info("vision models loaded")
        except Exception:
            logger.exception("vision model warm-up failed (scans will retry on demand)")

    threading.Thread(target=work, name="model-warm-up", daemon=True).start()


def create_app(settings: Settings | None = None, container_factory: ContainerFactory | None = None,
               sms_sender: SmsSender | None = None) -> FastAPI:
    settings = settings or get_settings()
    validate_production_settings(settings)                  # raises InsecureConfigurationError: the process must not start
    configure_logging(settings)
    sender = sms_sender or LogSmsSender()
    if settings.is_prod and settings.otp_login_enabled and isinstance(sender, LogSmsSender):
        logger.warning("ENV=prod with the log SMS sender: nobody can receive a login code until a real SmsSender is wired")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.is_prod:
            ensure_schema(settings)                         # production: Alembic migrations (refuses an out-of-date database)
        else:
            init_db()
        if app.state.container is None:
            app.state.container = (container_factory or build_container)(settings)
        app.state.release_advice = lambda session, task, body: release_advice(app.state.container, session, task, body)
        seed_if_enabled(settings, app.state.container.clock.now())
        start_scheduler(app)
        _warm_up_models_in_background(settings)
        yield
        stop_scheduler()

    hide_docs = settings.is_prod                            # the API description is not published in production
    app = FastAPI(title="FarmTrack API", version=settings.app_version, lifespan=lifespan,
                  docs_url=None if hide_docs else "/docs", redoc_url=None if hide_docs else "/redoc",
                  openapi_url=None if hide_docs else "/openapi.json",
                  description="Voice-guided farmer advisory backend. Contract for the mobile app.")
    app.state.settings = settings
    app.state.container = None
    app.state.sms_sender = sender
    app.state.limiters = RateLimiters.default()

    register_exception_handlers(app)
    # add_middleware puts the LAST added outermost: CORS innermost, SecurityHeaders outermost (see security/middleware.py)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Admin-Key", "X-Request-ID"])
    max_body = (settings.max_photos_per_scan * settings.max_upload_mb + 1) * 1024 * 1024
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_body)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_prod)
    for r in (meta.router, auth.router, me.router, scans.router, spray.router, field.router, alerts.router, devices.router,
              ask.router, voice.router, admin_router):
        app.include_router(r)
    return app


app = create_app()
