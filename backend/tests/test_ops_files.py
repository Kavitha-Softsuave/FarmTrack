"""The shipped ops files stay consistent with the code: .env.example lists every setting, the image migrates before it serves.

Nothing here reads the repo-root .env (it holds real secrets); only the committed .env.example is parsed.
"""
import re
import tomllib
from pathlib import Path

import pytest

from app.config import BACKEND_ROOT, REPO_ROOT, Settings
from app.security.startup import InsecureConfigurationError, validate_production_settings

EXAMPLE = REPO_ROOT / ".env.example"
LINE = re.compile(r"^(#\s*)?([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|ENV)=(.*)$")
# Read straight from the environment (not Settings fields) or by docker-compose; each must be in .env.example too.
OUTSIDE_SETTINGS = {"ALERT_INTERVAL_MINUTES", "ALERT_SCHEDULER", "AUTO_MIGRATE", "SEED_DEMO", "POSTGRES_USER",
                    "POSTGRES_PASSWORD", "POSTGRES_DB"}
NOT_A_SETTING = {"HF_HUB_DISABLE_SYMLINKS_WARNING"}               # set by the code for a library, never read from the operator


def example_entries() -> dict[str, tuple[bool, str]]:
    """name -> (active, value) for every `NAME=value` and `# NAME=value` line of .env.example."""
    found: dict[str, tuple[bool, str]] = {}
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = LINE.match(line.strip())
        if match:
            found[match.group(2)] = (match.group(1) is None, match.group(3).strip())
    return found


def test_every_settings_field_is_in_the_example():
    names = {name.upper() for name in Settings.model_fields}
    missing = sorted(names - set(example_entries()))
    assert missing == [], f".env.example lacks: {missing}"


def test_every_variable_the_code_reads_from_the_environment_is_in_the_example():
    read: set[str] = set()
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"environ|env\.get|env\[|ENV_VAR|getenv", line):
                read.update(re.findall(r'"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"', line))
    read -= NOT_A_SETTING
    assert OUTSIDE_SETTINGS <= read | {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"}, "the list above is out of date"
    assert sorted(read - set(example_entries()) - {n.upper() for n in Settings.model_fields}) == []
    assert sorted(OUTSIDE_SETTINGS - set(example_entries())) == []


def test_docker_compose_variables_are_in_the_example():
    compose = (BACKEND_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    used = set(re.findall(r"\$\{([A-Z][A-Z0-9_]+)", compose))
    assert {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"} <= used
    assert sorted(used - set(example_entries())) == []


def test_the_example_parses_as_settings_and_matches_the_defaults():
    entries = example_entries()
    settings = Settings(_env_file=EXAMPLE)
    defaults = Settings(_env_file=None)
    placeholders = {"secret_key", "admin_api_key", "openai_api_key", "google_tts_api_key"}
    for name, (active, _value) in entries.items():
        field = name.lower()
        if active and field in Settings.model_fields and field not in placeholders:
            assert getattr(settings, field) == getattr(defaults, field), f"{name} in .env.example differs from the code's default"


def test_the_example_holds_placeholders_only_and_prod_refuses_them():
    entries = example_entries()
    assert entries["OPENAI_API_KEY"][1].startswith("your-") and entries["GOOGLE_TTS_API_KEY"][1].startswith("your-")
    assert not any(re.search(r"sk-[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_-]{20,}", value) for _, value in entries.values())
    secret, admin = entries["SECRET_KEY"][1], entries["ADMIN_API_KEY"][1]
    with pytest.raises(InsecureConfigurationError) as caught:                               # copied unchanged into production: refused
        validate_production_settings(Settings(_env_file=None, env="prod", secret_key=secret, admin_api_key=admin,
                                              cors_origins=["https://farm.example"]))
    assert "SECRET_KEY" in str(caught.value) and "ADMIN_API_KEY" in str(caught.value)


def test_the_demo_hint_format_is_documented_in_the_example():
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "DEMO_DISEASE_HINTS=Apple=Apple___Apple_scab" in text and "ENV=prod" in text


# ------------------------------------------------------------------------------------------------ packaging and the image
def test_the_fcm_extra_matches_what_the_push_provider_imports():
    project = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert any(d.startswith("cryptography") for d in project["optional-dependencies"]["fcm"])
    push = (BACKEND_ROOT / "app" / "integrations" / "push.py").read_text(encoding="utf-8")
    assert "cryptography" in push and "import firebase_admin" not in push and "from firebase_admin" not in push


def test_the_entrypoint_migrates_then_starts_the_server():
    script = (BACKEND_ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/bin/sh") and "\r" not in script
    assert "python -m alembic upgrade head" in script and 'AUTO_MIGRATE:-1' in script and script.rstrip().endswith('exec "$@"')
    assert script.index("alembic upgrade head") < script.index('exec "$@"')


def test_the_dockerfile_uses_the_entrypoint_and_keeps_the_server_as_cmd():
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY --chown=farmtrack:farmtrack docker-entrypoint.sh" in dockerfile
    assert 'ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]' in dockerfile and 'CMD ["uvicorn", "app.main:app"' in dockerfile
    assert "AUTO_MIGRATE=1" in dockerfile and "COPY --chown=farmtrack:farmtrack alembic.ini" in dockerfile
    assert 'ARG EXTRAS="pg fcm"' in dockerfile
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert "docker-entrypoint.sh" not in dockerignore and "migrations" not in dockerignore       # both must reach the build context


def test_alembic_is_configured_the_way_the_entrypoint_runs_it():
    ini = (BACKEND_ROOT / "alembic.ini").read_text(encoding="utf-8")
    assert re.search(r"^script_location = migrations$", ini, re.MULTILINE)                       # relative to the image's WORKDIR /app
    assert (Path(BACKEND_ROOT) / "migrations" / "env.py").is_file()
