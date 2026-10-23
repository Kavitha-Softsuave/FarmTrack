from __future__ import annotations

import pytest

from app.rules.data import ReferenceData, load_reference
from app.rules.policy import ENV_VAR

from .helpers import DATA_DIR, make_engine, world


@pytest.fixture(autouse=True)
def _default_policy(monkeypatch):
    """Every test starts from the NARROW auto-advice policy (apple scab only). The product default is '*' (owner decision), so
    the narrow one is pinned with an empty value: the setting and the variable then add nothing."""
    monkeypatch.setenv(ENV_VAR, "")


@pytest.fixture(scope="session")
def ref() -> ReferenceData:
    return load_reference(DATA_DIR)


@pytest.fixture(scope="session", autouse=True)
def _warm_world():
    """Parse the demo CSVs once per session so no single test pays for it."""
    world()


@pytest.fixture
def engine():
    return make_engine()


@pytest.fixture
def widen_policy(monkeypatch):
    """Extend auto-advice to every catalogue disease with chemical control (policy tests and exclusion tests on other diseases)."""

    def _set(value: str = "*") -> None:
        monkeypatch.setenv(ENV_VAR, value)

    return _set
