import pytest

from app.db.session import get_session_factory, init_db


@pytest.fixture
def db():
    """A session on the per-test SQLite database (the root conftest isolates DATABASE_URL and the engine cache)."""
    init_db()
    session = get_session_factory()()
    yield session
    session.close()
