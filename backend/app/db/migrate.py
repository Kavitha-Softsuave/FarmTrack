"""Schema migrations at startup (production). Development and tests create tables with init_db() instead.

Production applies the Alembic migrations. `ensure_schema` refuses to run against an out-of-date database with a clear message;
with AUTO_MIGRATE=1 it upgrades the database itself (fine for one worker; with several replicas run `alembic upgrade head` once
from the deploy pipeline instead).
"""
from __future__ import annotations

import logging
import os

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

from app.config import BACKEND_ROOT, Settings
from app.db.session import get_engine

logger = logging.getLogger(__name__)


class SchemaOutOfDateError(RuntimeError):
    pass


def alembic_config(url: str | None = None) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.attributes["configure_logger"] = False           # keep the application's logging; do not let alembic.ini replace it
    if url:
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def schema_is_current(engine: Engine) -> bool:
    return current_revision(engine) == head_revision()


def upgrade_to_head(url: str) -> None:
    command.upgrade(alembic_config(url), "head")


def ensure_schema(settings: Settings) -> None:
    engine = get_engine()
    if schema_is_current(engine):
        return
    if os.environ.get("AUTO_MIGRATE") == "1":
        logger.info("database schema is not current: applying migrations (AUTO_MIGRATE=1)")
        upgrade_to_head(settings.database_url)
        return
    raise SchemaOutOfDateError("The database schema is missing or out of date. Run `python -m alembic upgrade head` "
                               "(or start with AUTO_MIGRATE=1 for a single-worker deployment).")
