# FarmTrack

A voice-guided advisory app for farmers in Himachal Pradesh. The farmer takes (or picks) a photo of a leaf; the app finds the
crop and the disease, speaks the answer in Hindi or English, and, for crops that have approved data, names the medicine, dose,
timing and waiting period from the approved list only. The farmer's spray diary, the field weather and alerts are part of it.

Built for FarmTrack AgTech by Soft Suave Technologies. Status: **working MVP, Android first** (iOS not yet looked at).
Read [`docs/open-questions.md`](docs/open-questions.md) first: it lists the decisions taken, what is untested and what needs
an expert (agronomist, native Hindi speaker).

## Repository layout

| Folder | What is in it |
|---|---|
| [`backend/`](backend/README.md) | Python API (FastAPI, SQLAlchemy, Alembic): rules engine, vision, advice, ask, voice, diary, alerts, admin site |
| [`mobile/`](mobile/README.md) | Flutter app (Android first): login, scan, advice, diary, field, alerts, ask, settings, offline queue |
| `contracts/` | `openapi.json`: the API contract the app is built against (changes stay additive) |
| `data/` | Reference data (products, diseases, rules, stages, glossary), demo farmers, weather, sensors, scripts that build them, model test kits. **No photos** (see below) |
| `voice/` | Spoken prompts (`prompts.json`, Hindi and English) and their validator |
| `docs/` | `requirements.md`, `mvp-plan.md`, `open-questions.md`, `research/` (models, agronomy), `design-notes/` (per-component notes) |
| `scripts/` | Helper scripts, e.g. `start_backend_for_phone.ps1` (backend for a phone on the same network) |
| `.github/workflows/` | CI: backend (ruff, pytest) and mobile (analyze, format, test) |

[`CLAUDE.md`](CLAUDE.md) is the project memory for Claude Code sessions (decisions, rules, easy-to-get-wrong list).

## Quick start

Backend (Python 3.11+; everything runs offline by default with mock providers):
```
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"      # Unix: .venv/bin/python
.venv/Scripts/python -m pytest                    # about 3000 tests, a few minutes
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```
Demo login: user name `f001`, password `farm1234` (demo farmers `f001` to `f050`, development only).

Mobile (Flutter 3.47):
```
cd mobile
flutter pub get
flutter run --dart-define=USE_MOCK_API=true       # demo without a backend
flutter analyze && flutter test
```
Trying it on an Android phone against your own machine (build the APK, start the backend, set the server address inside the
app): see [`mobile/README.md`](mobile/README.md), section "Try it on an Android phone".

## What is not in this repository, on purpose
A new developer needs a few things that are not committed: see [`docs/dev-setup.md`](docs/dev-setup.md) for the full list and how to get each.

- **`.env` and any key.** Copy [`.env.example`](.env.example) to `.env` and fill in your own values. Never commit it.
- **Leaf photos** (`data/images/**`): the test photos are web images of unknown licence and photos collected from users; only
  their label files and notes are kept (`data/images/README.md`). Put your own photos there to run the accuracy scripts and the
  live check.
- **Model weights** (about 300 MB): downloaded on first use into `backend/storage/models` (pinned revisions, see
  `backend/app/vision/`) when `CROP_ID_PROVIDER=model` and `DISEASE_PROVIDER=model` are set.
- **Built apps** (`dist/`, `*.apk`), databases, virtual environments and build folders.

## Before real farmers use it

Not verified on this project's machines: a release build on several real phones, Docker image, PostgreSQL/pgvector, and the real
OpenAI, text-to-speech, Zoho, push and SMS services. All Hindi text is a draft for a native speaker. Details and the full list
of decisions are in [`docs/open-questions.md`](docs/open-questions.md).
