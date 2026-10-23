"""init_db() upgrades a development database that an earlier create_all made (it would fail with 'no such column' otherwise)."""
import sqlite3

from sqlalchemy import inspect

from app.config import get_settings
from app.db.models import Base
from app.db.session import add_missing_columns, get_engine, init_db


def make_old_database(path: str) -> None:
    """A scans/spray_logs/expert_requests schema from before client_request_id, crop_id and the resolution columns existed."""
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE farmers (id VARCHAR(32) PRIMARY KEY, name VARCHAR(120) NOT NULL, phone VARCHAR(20) NOT NULL, "
                     "language VARCHAR(2) NOT NULL, crops JSON NOT NULL, created_at DATETIME NOT NULL)")
        conn.execute("CREATE TABLE expert_requests (id VARCHAR(32) PRIMARY KEY, farmer_id VARCHAR(32) NOT NULL, scan_id VARCHAR(32), "
                     "message VARCHAR(500), status VARCHAR(10) NOT NULL, created_at DATETIME NOT NULL)")
        conn.execute("INSERT INTO expert_requests (id, farmer_id, status, created_at) VALUES ('e1', 'F1', 'open', '2026-05-12 08:00:00')")


def test_missing_nullable_columns_and_indexes_are_added_without_touching_data():
    path = get_settings().database_url.removeprefix("sqlite:///")
    make_old_database(path)
    init_db()
    inspector = inspect(get_engine())
    columns = {c["name"] for c in inspector.get_columns("expert_requests")}
    assert {"client_request_id", "crop_id", "resolved_at", "resolution"} <= columns
    assert "uq_expert_requests_farmer_request" in {i["name"] for i in inspector.get_indexes("expert_requests")}
    assert {t.name for t in Base.metadata.sorted_tables} <= set(inspector.get_table_names())          # the other tables were created
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id, status, client_request_id FROM expert_requests").fetchall() == [("e1", "open", None)]


def test_the_login_columns_and_the_unique_username_index_are_added_to_an_older_farmers_table():
    path = get_settings().database_url.removeprefix("sqlite:///")
    make_old_database(path)                                     # a farmers table without username and password_hash
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO farmers (id, name, phone, language, crops, created_at) VALUES "
                     "('F1', 'Old', '+911', 'hi', '[]', '2026-05-12 08:00:00')")
    init_db()
    inspector = inspect(get_engine())
    assert {"username", "password_hash"} <= {c["name"] for c in inspector.get_columns("farmers")}
    index = next(i for i in inspector.get_indexes("farmers") if i["name"] == "ix_farmers_username")
    assert index["unique"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT id, username, password_hash FROM farmers").fetchall() == [("F1", None, None)]


def test_running_it_again_changes_nothing():
    init_db()
    assert add_missing_columns(get_engine()) == []
    init_db()
