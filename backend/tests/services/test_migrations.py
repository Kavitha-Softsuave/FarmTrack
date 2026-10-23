"""`alembic upgrade head` must produce exactly the schema of the ORM models."""
import sqlite3

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.config import BACKEND_ROOT
from app.db.models import Base


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


@pytest.fixture
def migrated_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    return url


def test_there_is_a_single_head():
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


def test_upgrade_head_equals_the_orm_metadata(migrated_url):
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata)
    engine.dispose()
    assert diff == []


def test_upgrade_creates_every_table_column_and_index(migrated_url, tmp_path):
    reference = create_engine(f"sqlite:///{(tmp_path / 'orm.db').as_posix()}")
    Base.metadata.create_all(reference)
    migrated = create_engine(migrated_url)
    ref, mig = inspect(reference), inspect(migrated)
    assert set(mig.get_table_names()) == set(ref.get_table_names()) | {"alembic_version"}
    for table in ref.get_table_names():
        assert [(c["name"], c["nullable"]) for c in mig.get_columns(table)] == [(c["name"], c["nullable"]) for c in ref.get_columns(table)]
        assert {i["name"] for i in mig.get_indexes(table)} == {i["name"] for i in ref.get_indexes(table)}
        assert {tuple(f["constrained_columns"]) for f in mig.get_foreign_keys(table)} == {
            tuple(f["constrained_columns"]) for f in ref.get_foreign_keys(table)}
    assert {tuple(u["column_names"]) for u in mig.get_unique_constraints("alerts")} == {("farmer_id", "dedupe_key")}
    reference.dispose()
    migrated.dispose()


def test_unique_phone_survives_the_migration(migrated_url):
    with sqlite3.connect(migrated_url.removeprefix("sqlite:///")) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        row = ("F1", "Name", "+911", "hi", "[]", "2026-05-12 08:00:00")
        sql = "INSERT INTO farmers (id, name, phone, language, crops, created_at) VALUES (?,?,?,?,?,?)"
        conn.execute(sql, row)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, ("F2", *row[1:]))


def test_downgrade_removes_everything(migrated_url):
    command.downgrade(alembic_config(migrated_url), "base")
    engine = create_engine(migrated_url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()


def test_env_reads_the_url_from_the_settings(tmp_path):
    """Without an explicit url, migrations/env.py uses settings.database_url (the conftest points it at a temp file)."""
    from app.config import get_settings

    command.upgrade(alembic_config(), "head")
    path = get_settings().database_url.removeprefix("sqlite:///")
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"farmers", "scans", "advice", "otp_requests", "alembic_version"} <= tables


def test_upgrading_twice_is_a_no_op(migrated_url):
    command.upgrade(alembic_config(migrated_url), "head")
    engine = create_engine(migrated_url)
    assert "farmers" in inspect(engine).get_table_names()
    engine.dispose()


# ------------------------------------------------------------------------------------------------- idempotency columns
ROWS = {
    "scans": ("id, farmer_id, created_at, status, crop_confirmed, quality, result, photo_paths, client_request_id",
              "?, ?, '2026-05-12 08:00:00', 'ok', 0, '{}', '{}', '[]', ?"),
    "spray_logs": ("id, farmer_id, crop_id, sprayed_at, synced_to_zoho, warnings, created_at, client_request_id",
                   "?, ?, 'Apple', '2026-05-12 08:00:00', 0, '[]', '2026-05-12 08:00:00', ?"),
    "expert_requests": ("id, farmer_id, status, created_at, client_request_id", "?, ?, 'open', '2026-05-12 08:00:00', ?"),
}


@pytest.mark.parametrize("table", sorted(ROWS))
def test_a_client_request_id_is_unique_per_farmer_but_free_for_everyone_else(migrated_url, table):
    columns, values = ROWS[table]
    sql = f"INSERT INTO {table} ({columns}) VALUES ({values})"                                  # noqa: S608  (fixed test strings)
    with sqlite3.connect(migrated_url.removeprefix("sqlite:///")) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for farmer in ("F1", "F2"):
            conn.execute("INSERT INTO farmers (id, name, phone, language, crops, created_at) VALUES (?,?,?,?,?,?)",
                         (farmer, "Name", f"+91{farmer}", "hi", "[]", "2026-05-12 08:00:00"))
        conn.execute(sql, ("r1", "F1", "key-1"))
        conn.execute(sql, ("r2", "F2", "key-1"))                                                # another farmer: no collision
        conn.execute(sql, ("r3", "F1", "key-2"))                                                # another key: fine
        conn.execute(sql, ("r4", "F1", None))
        conn.execute(sql, ("r5", "F1", None))                                                   # no key at all: any number of rows
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, ("r6", "F1", "key-1"))


def test_the_new_columns_and_indexes_come_from_the_migration(migrated_url):
    engine = create_engine(migrated_url)
    inspector = inspect(engine)
    for table, index in (("scans", "uq_scans_farmer_request"), ("spray_logs", "uq_spray_logs_farmer_request"),
                         ("expert_requests", "uq_expert_requests_farmer_request")):
        assert "client_request_id" in {c["name"] for c in inspector.get_columns(table)}
        found = next(i for i in inspector.get_indexes(table) if i["name"] == index)
        assert found["unique"] and found["column_names"] == ["farmer_id", "client_request_id"]
    assert {"resolved_at", "resolution", "crop_id"} <= {c["name"] for c in inspector.get_columns("expert_requests")}
    engine.dispose()


# ------------------------------------------------------------------------------------------------- username + password
def test_the_login_columns_come_from_the_migration(migrated_url):
    engine = create_engine(migrated_url)
    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("farmers")}
    assert columns["username"]["nullable"] and columns["password_hash"]["nullable"]
    assert columns["username"]["type"].length == 40 and columns["password_hash"]["type"].length == 255
    index = next(i for i in inspector.get_indexes("farmers") if i["name"] == "ix_farmers_username")
    assert index["unique"] and index["column_names"] == ["username"]
    engine.dispose()


def test_a_username_is_unique_but_many_farmers_may_have_none(migrated_url):
    sql = "INSERT INTO farmers (id, name, phone, language, crops, created_at, username) VALUES (?,?,?,?,?,?,?)"
    with sqlite3.connect(migrated_url.removeprefix("sqlite:///")) as conn:
        conn.execute(sql, ("F1", "Name", "+911", "hi", "[]", "2026-05-12 08:00:00", "same.name"))
        conn.execute(sql, ("F2", "Name", "+912", "hi", "[]", "2026-05-12 08:00:00", None))
        conn.execute(sql, ("F3", "Name", "+913", "hi", "[]", "2026-05-12 08:00:00", None))          # NULLs never collide
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, ("F4", "Name", "+914", "hi", "[]", "2026-05-12 08:00:00", "same.name"))
