"""Global test isolation: tests never read the repo-root .env (it holds the user's real secrets) and never touch the network."""
from __future__ import annotations

import os

# Must be set before app.config is imported anywhere.
os.environ["ENV"] = "test"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "null"
os.environ["EMBEDDINGS_PROVIDER"] = "hash"
os.environ["VECTOR_STORE"] = "memory"
os.environ["PUSH_PROVIDER"] = "log"
os.environ["OPENAI_API_KEY"] = ""
os.environ["RULES_SEASON_CHECK"] = "true"            # the rule tests assert the production (seasonal) behaviour
os.environ["RULES_AUTO_ADVICE_DISEASES"] = ""        # the product default is '*'; the rule tests pin the narrow policy (scab only)
os.environ["GOOGLE_TTS_API_KEY"] = ""
os.environ["OTP_LOGIN_ENABLED"] = "true"        # the OTP login is off by default (password login only); its own tests need it on

import pytest  # noqa: E402

from app.config import Settings, get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    """Every test gets a private database, storage dir and a fresh settings/clock/engine cache."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("WEATHER_ENABLED", "true")       # the product default is off; most tests exercise the weather paths
    monkeypatch.setattr("app.security.passwords.DEFAULT_ITERATIONS", 1_000)     # fast hashing; the stored format carries the count
    get_settings.cache_clear()
    from app.clock import reset_clock
    from app.db.session import reset_engine

    reset_clock()
    reset_engine()
    yield
    reset_engine()
    reset_clock()
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


# SQLite ignores VARCHAR(n); PostgreSQL rejects a longer value with "value too long" (an HTTP 500 for the farmer). Every test
# therefore runs with a guard that records any insert or update that would not fit its column, and fails the test at the end.
_OVERFLOWS: list[str] = []


def _record_overflow(_mapper, _connection, target) -> None:  # noqa: ANN001
    from sqlalchemy import String

    for column in target.__table__.columns:
        value = getattr(target, column.key, None)
        length = getattr(column.type, "length", None)
        if isinstance(column.type, String) and length and isinstance(value, str) and len(value) > length:
            _OVERFLOWS.append(f"{target.__table__.name}.{column.name}: {len(value)} characters in a column of {length}")


def _install_overflow_guard() -> None:
    from sqlalchemy import event

    from app.db.models import Base

    for name in ("before_insert", "before_update"):
        event.listen(Base, name, _record_overflow, propagate=True)


_install_overflow_guard()


@pytest.fixture(autouse=True)
def _postgres_column_lengths():
    _OVERFLOWS.clear()
    yield
    assert not _OVERFLOWS, "PostgreSQL would reject: " + "; ".join(_OVERFLOWS)


# ------------------------------------------------------------------------------------------------------------ API test fixtures
# (PLATFORM) a fully faked application: SQLite temp DB, demo farmers seeded at startup, fake providers, no network.
import json  # noqa: E402
from collections.abc import Callable  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

PROMPTS = {
    "crop_is_apple": ("This looks like apple.", "यह सेब की फसल लगती है।"),
    "crop_is_unknown": ("I could not tell the crop.", "फसल पहचान में नहीं आई।"),
    "crop_confirm_prompt": ("Is this the right crop?", "क्या यह सही फसल है?"),
    "result_expert": ("A farm expert needs to see this.", "इसे खेती के जानकार को दिखाना ज़रूरी है।"),
    "result_no_data": ("We do not have advice for this crop yet.", "इस फसल की सलाह अभी हमारे पास नहीं है।"),
    "result_not_disease": ("We could not see a disease in this photo.", "इस फोटो में हमें कोई बीमारी नहीं दिखी।"),
    "scan_retake_blurry": ("The photo is not clear.", "फोटो साफ़ नहीं आई।"),
    "scan_retake_dark": ("The light was not right.", "रोशनी ठीक नहीं थी।"),
    "diary_saved": ("Done. It is saved in your diary.", "हो गया।"),
    "diary_warning": ("There is a warning.", "एक चेतावनी है।"),
    "field_stale": ("This information is old.", "यह जानकारी पुरानी है।"),
    "field_no_data": ("There is no information yet.", "जानकारी अभी नहीं है।"),
}


@pytest.fixture
def voice_dir(monkeypatch, tmp_path):
    """A private voice/ directory with the few prompts the platform layer reads, so tests do not depend on voice/prompts.json."""
    folder = tmp_path / "voice"
    folder.mkdir()
    prompts = [{"id": k, "en": en, "hi": hi} for k, (en, hi) in PROMPTS.items()]
    (folder / "prompts.json").write_text(json.dumps({"version": "test", "prompts": prompts}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("VOICE_DIR", str(folder))
    get_settings.cache_clear()
    return folder


@pytest.fixture
def api_settings(voice_dir) -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def fake_container(api_settings):
    from tests import fakes

    return fakes.make_container(api_settings)


@pytest.fixture
def api_app(fake_container):
    from app.main import create_app

    application = create_app(fake_container.settings, container_factory=lambda _s: fake_container)
    application.state.container = fake_container
    return application


@pytest.fixture
def api_client(api_app):
    with TestClient(api_app, raise_server_exceptions=False) as client:
        yield client


DEMO_PASSWORD = "farm1234"                      # Settings.demo_password default: the password of every seeded demo farmer


def credentials_for(phone: str) -> tuple[str, str]:
    """(username, password) of the farmer with this phone. A test farmer without a login is given the demo login on the spot."""
    from app.db.repo import get_farmer_by_phone
    from app.db.session import get_session_factory
    from app.security.passwords import hash_password

    with get_session_factory()() as session:
        farmer = get_farmer_by_phone(session, phone)
        assert farmer is not None, f"no farmer with phone {phone}"
        if not farmer.password_hash:
            farmer.username = farmer.username or farmer.id.lower()
            farmer.password_hash = hash_password(DEMO_PASSWORD)
            session.commit()
        assert farmer.username is not None
        return farmer.username, DEMO_PASSWORD


@pytest.fixture
def login(api_client) -> Callable[..., dict[str, str]]:
    """login(phone, device_id) logs the farmer with that phone in through POST /v1/auth/login (demo credentials) and returns the
    Authorization header."""

    def _login(phone: str = "+910000000001", device_id: str | None = None) -> dict[str, str]:
        username, password = credentials_for(phone)
        response = api_client.post("/v1/auth/login", json={"username": username, "password": password, "device_id": device_id})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture
def auth(login) -> dict[str, str]:
    return login()
