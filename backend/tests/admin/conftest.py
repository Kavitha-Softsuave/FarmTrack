import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin import auth
from app.admin.router import router
from app.api.deps import get_db, require_admin
from app.config import get_settings
from app.db.models import FarmerRow, ReviewTaskRow, ScanRow
from app.db.session import get_session_factory, init_db
from tests.integrations.fakes import NOW, FakeRules, farmer_row, make_container

ADMIN_KEY = "test-admin-key-5f3a"
SECRET = "test-secret-key-91bc"


@pytest.fixture(autouse=True)
def admin_settings(monkeypatch):
    """Known admin key and signing secret; an empty login-throttle state for every test."""
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("SECRET_KEY", SECRET)
    get_settings.cache_clear()
    auth.login_throttle.reset()
    yield
    auth.login_throttle.reset()


@pytest.fixture
def db():
    init_db()
    session = get_session_factory()()
    yield session
    session.close()


@pytest.fixture
def container(tmp_path):
    return make_container(tmp_path, rules=FakeRules())


@pytest.fixture
def app(db, container) -> FastAPI:
    """The admin router on its own app. The platform's require_admin and get_db are replaced here, as the brief prescribes."""

    def session_per_request():
        session = get_session_factory()()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_db] = session_per_request
    app.state.container = container
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def seed(db, *rows) -> None:
    for row in rows:
        db.add(row)
        db.flush()
    db.commit()


def seed_review(db, task_id="t1", scan_id="scan1", farmer_id="F901", **scan_kw):
    """A farmer, a scan with two candidates (one malformed) and one stored photo, and an open review task."""
    if db.get(FarmerRow, farmer_id) is None:
        seed(db, farmer_row(farmer_id))
    scan_values = {
        "id": scan_id, "farmer_id": farmer_id, "created_at": NOW, "status": "needs_expert", "crop_id": "Apple",
        "photo_paths": [f"photos/{farmer_id}/{scan_id}_0.jpg"],
        "result": {"disease": {"candidates": [
            {"disease_id": "Apple___Apple_scab", "name": {"en": "Apple scab", "hi": "सेब का स्कैब"}, "confidence": 0.61},
            {"unexpected": "shape"}]}},
    }
    scan_values.update(scan_kw)
    seed(db, ScanRow(**scan_values), ReviewTaskRow(id=task_id, scan_id=scan_id, farmer_id=farmer_id, status="open",
                                                   reason="Alternaria or Marssonina", created_at=NOW))
