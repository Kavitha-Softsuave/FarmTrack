# FarmTrack backend. Run from ./backend. Works with the Windows (.venv/Scripts) and Unix (.venv/bin) virtualenv layouts.
PY = $(firstword $(wildcard .venv/Scripts/python.exe .venv/bin/python) python)
ENV_FILE ?= ../.env
IMAGE ?= farmtrack-api:dev

.PHONY: help venv install test lint fix run export-openapi docker-build docker-up docker-down docker-logs clean

help:
	@echo "install | test | lint | fix | run | export-openapi | docker-build | docker-up | docker-down | docker-logs | clean"

venv:
	@test -d .venv || python -m venv .venv

install: venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check app tests

fix:
	$(PY) -m ruff check --fix app tests

run:
	$(PY) -m uvicorn app.main:app --reload --port 8000

export-openapi:
	$(PY) -m app.export_openapi ../contracts/openapi.json

# The image takes the shared data and voice folders as named build contexts (the build context itself is ./backend).
docker-build:
	docker build -t $(IMAGE) --build-context data=../data --build-context voice=../voice .

docker-up:
	docker compose --env-file $(ENV_FILE) up -d --build

docker-down:
	docker compose --env-file $(ENV_FILE) down

docker-logs:
	docker compose --env-file $(ENV_FILE) logs -f api

clean:
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('**/__pycache__')]; [shutil.rmtree(d, ignore_errors=True) for d in ('.pytest_cache', '.ruff_cache', '.mypy_cache')]"
