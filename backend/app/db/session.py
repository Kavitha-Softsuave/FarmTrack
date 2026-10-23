"""Database engine and session factory. SQLite for dev/tests, PostgreSQL in production (same models)."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for background jobs and scripts (API handlers use the get_db dependency)."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def add_missing_columns(engine: Engine) -> list[str]:
    """Development convenience: bring a database made by an earlier `create_all` up to the current models.

    `create_all` never alters an existing table, so a dev database created before a column was added would fail with
    "no such column". This adds the missing NULLABLE columns and the missing indexes (never drops or changes anything) and returns
    what it added. Production does not use this: it runs the Alembic migrations.
    """
    added: list[str] = []
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                if not column.nullable:
                    logger.warning("dev database lacks required column %s.%s; delete the database file to recreate it",
                                   table.name, column.name)
                    continue
                quote = engine.dialect.identifier_preparer.quote
                connection.exec_driver_sql(f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(column.name)} "
                                           f"{column.type.compile(dialect=engine.dialect)}")
                added.append(f"{table.name}.{column.name}")
            for index in table.indexes:
                index.create(bind=connection, checkfirst=True)
    return added


def init_db() -> None:
    """Create tables (dev/tests). Production uses Alembic migrations."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    added = add_missing_columns(engine)
    if added:
        logger.info("dev database upgraded in place: added %s", ", ".join(added))


def reset_engine() -> None:
    """For tests: drop the cached engine/factory so a new DATABASE_URL takes effect."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None
