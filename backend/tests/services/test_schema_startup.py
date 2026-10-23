"""Production start-up: the database schema must be current (Alembic), never silently created or stale."""
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.db.migrate import (
    SchemaOutOfDateError,
    alembic_config,
    current_revision,
    ensure_schema,
    head_revision,
    schema_is_current,
    upgrade_to_head,
)
from app.db.session import get_engine
from app.main import create_app
from tests.fakes import make_container

PROD = dict(env="prod", secret_key="k" * 40, admin_api_key="a" * 24, cors_origins=["https://farm.example"], demo_clock=None)


@pytest.fixture
def prod_settings(api_settings):
    return api_settings.model_copy(update=PROD)


def start(settings):
    container = make_container(settings)
    with TestClient(create_app(settings, container_factory=lambda _s: container), raise_server_exceptions=False) as client:
        return client.get("/health").json()


def test_an_empty_database_is_refused_with_a_clear_message(prod_settings, monkeypatch):
    monkeypatch.delenv("AUTO_MIGRATE", raising=False)
    with pytest.raises(SchemaOutOfDateError) as caught:
        start(prod_settings)
    assert "alembic upgrade head" in str(caught.value)
    assert "farmers" not in inspect(get_engine()).get_table_names()           # nothing was created behind our back


def test_a_migrated_database_starts(prod_settings, monkeypatch):
    monkeypatch.delenv("AUTO_MIGRATE", raising=False)
    upgrade_to_head(prod_settings.database_url)
    assert start(prod_settings) == {"status": "ok", "db": True}


def test_auto_migrate_upgrades_an_empty_database(prod_settings, monkeypatch):
    monkeypatch.setenv("AUTO_MIGRATE", "1")
    assert start(prod_settings) == {"status": "ok", "db": True}
    assert schema_is_current(get_engine())


def test_auto_migrate_must_be_exactly_one(prod_settings, monkeypatch):
    monkeypatch.setenv("AUTO_MIGRATE", "yes")
    with pytest.raises(SchemaOutOfDateError):
        start(prod_settings)


def test_a_database_stamped_at_base_is_out_of_date(prod_settings, monkeypatch):
    monkeypatch.delenv("AUTO_MIGRATE", raising=False)
    upgrade_to_head(prod_settings.database_url)
    command.stamp(alembic_config(prod_settings.database_url), "base")
    assert current_revision(get_engine()) is None and not schema_is_current(get_engine())
    with pytest.raises(SchemaOutOfDateError):
        ensure_schema(prod_settings)


def test_ensure_schema_does_nothing_when_current(prod_settings):
    upgrade_to_head(prod_settings.database_url)
    ensure_schema(prod_settings)
    assert current_revision(get_engine()) == head_revision() == "0001"


def test_development_still_creates_the_tables_itself(api_client):
    assert "farmers" in inspect(create_engine(api_client.app.state.settings.database_url)).get_table_names()
    assert not schema_is_current(get_engine())                                  # no alembic_version: dev uses create_all


def test_migrating_in_process_keeps_the_applications_logging(prod_settings):
    import logging

    before = list(logging.getLogger().handlers)
    upgrade_to_head(prod_settings.database_url)
    assert list(logging.getLogger().handlers) == before
