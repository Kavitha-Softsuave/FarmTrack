"""Alembic environment. The schema source of truth is app.db.models.Base.metadata."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.config import get_settings
from app.db.models import Base
from app.db.session import make_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True,
                      render_as_batch=url.startswith("sqlite"), dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    engine = make_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                          render_as_batch=url.startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
