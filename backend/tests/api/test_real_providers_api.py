"""Wiring check: the API on the REAL rules, vision (stub models), advice composer (mock LLM), KB, Zoho/IoT/weather mocks.

Everything here is offline and deterministic (no model downloads, no network, no OpenAI). It proves the pieces fit together; the
per-component behaviour is tested in the components' own test folders.
"""
import io
import json
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.integrations.reference import load_product_master
from app.main import create_app
from app.services.container import build_container
from app.vision.factory import build_disease_classifier
from tests.imaging import make_jpeg


def textured_leaf() -> bytes:
    """Green noise: sharp, bright enough, plant-coloured, so the real quality gate lets it through."""
    noise = np.random.default_rng(7).integers(-45, 45, size=(480, 640, 3))
    pixels = np.clip(np.array([50, 140, 50]) + noise, 0, 255).astype("uint8")
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


@pytest.fixture
def real_settings() -> Settings:
    """The repo's own data/ and voice/ (the conftest already points the database and storage at temp files)."""
    return Settings(_env_file=None)


@pytest.fixture
def real(real_settings):
    """(client, headers, container): the demo farmer F001 logged in on the real providers; the stub disease model is told 'scab'."""
    container = build_container(real_settings)
    container.disease_classifier = build_disease_classifier(real_settings, stub_hints={"Apple": "Apple___Apple_scab"})
    app = create_app(real_settings, container_factory=lambda _s: container)
    with TestClient(app, raise_server_exceptions=False) as client:
        body = client.post("/v1/auth/otp/request", json={"phone": "+910000000001"}).json()
        token = client.post("/v1/auth/otp/verify", json={"request_id": body["request_id"], "otp": body["dev_otp"]}).json()
        yield client, {"Authorization": f"Bearer {token['access_token']}"}, container


def scan(client, headers, jpeg, **data):
    return client.post("/v1/scans", files=[("photos", ("leaf.jpg", jpeg, "image/jpeg"))], data=data, headers=headers)


def test_confident_scab_scan_gives_approved_advice(real, real_settings):
    client, headers, _container = real
    response = scan(client, headers, textured_leaf(), client_crop="Apple", client_confidence="0.95")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["crop"]["crop_id"] == "Apple" and body["disease"]["disease_id"] == "Apple___Apple_scab"
    advice = body["advice"]
    master = load_product_master(real_settings.data_dir)
    assert advice["products"] and advice["validated"] is True
    for product in advice["products"]:
        row = master[product["product_id"]]                                          # every medicine is in the approved list
        assert row.crop == "Apple" and "Apple___Apple_scab" in row.targets and row.ban_status != "banned"
        assert product["dose_text"]["en"] and product["dose_unit"] == row.dose_unit
    assert advice["sources"] and advice["timing"]["action"] in ("spray_now", "wait", "repeat_within_days")
    assert not re.search(r"\d", advice["spoken"]["text"]["en"]) and advice["spoken"]["text"]["hi"]      # numbers are words when spoken
    assert [s["action"] for s in body["next_steps"]] == ["mark_sprayed", "done"]
    assert client.get(f"/v1/scans/{body['id']}", headers=headers).json() == body


def test_the_unsure_apple_leaf_goes_to_the_expert_with_no_medicine(real):
    client, headers, _container = real
    first = scan(client, headers, textured_leaf()).json()                              # no on-device guess: the profile prior asks
    assert first["status"] == "confirm_crop" and first["disease"] is None and first["advice"] is None
    assert first["spoken"]["text"]["en"].endswith("Is this the right crop?")
    confirmed = client.post(f"/v1/scans/{first['id']}/crop", json={"crop_id": "Apple"}, headers=headers).json()
    assert confirmed["status"] == "ok" and confirmed["crop"]["source"] == "farmer_confirmed"


def test_unclear_disease_is_an_expert_case_without_products(real_settings):
    container = build_container(real_settings)                                       # the stub disease model says nothing
    app = create_app(real_settings, container_factory=lambda _s: container)
    with TestClient(app, raise_server_exceptions=False) as client:
        body = client.post("/v1/auth/otp/request", json={"phone": "+910000000001"}).json()
        token = client.post("/v1/auth/otp/verify", json={"request_id": body["request_id"], "otp": body["dev_otp"]}).json()
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        result = scan(client, headers, textured_leaf(), client_crop="Apple", client_confidence="0.95").json()
        assert result["status"] == "needs_expert" and result["review_task_id"]
        assert result["advice"]["products"] == [] and result["advice"]["timing"] is None
        assert "expert" in result["spoken"]["text"]["en"].lower()
        tasks = client.get("/admin/api/v1/review-tasks", headers={"X-Admin-Key": real_settings.admin_api_key}).json()
        assert [t["id"] for t in tasks] == [result["review_task_id"]] and tasks[0]["farmer_id"] == "F001"
        assert tasks[0]["photo_urls"]


def test_a_flat_photo_is_rejected_by_the_real_quality_gate(real):
    client, headers, _container = real
    body = scan(client, headers, make_jpeg(size=(640, 480))).json()
    assert body["status"] == "photo_unusable" and body["quality"]["issues"] == ["blurry"]
    assert body["next_steps"] == [{"action": "retake", "prompt_id": "scan_retake_blurry"}]
    assert body["spoken"]["text"]["hi"]


def test_real_field_ask_diary_and_catalogue(real, real_settings):
    client, headers, _container = real
    field = client.get("/v1/field", headers=headers).json()
    assert field["stale"] is False and field["readings"]["temp_c"] is not None and len(field["forecast"]) == 7
    assert all(r["level"] in ("green", "yellow", "red") for r in field["risks"]) and field["spoken"]["text"]["en"]
    answer = client.post("/v1/ask", json={"question": "How to control apple scab?", "language": "en"}, headers=headers).json()
    assert answer["answer"] and answer["refused"] is False and answer["citations"]
    refused = client.post("/v1/ask", json={"question": "Who won the cricket match?", "language": "en"}, headers=headers).json()
    assert refused["refused"] is True
    logged = client.post("/v1/spray-logs", json={"crop_id": "Apple", "product_id": "P012"}, headers=headers).json()
    assert logged["product_name"] == "Myclobutanil" and logged["synced_to_zoho"] is True
    lines = [json.loads(line) for path in (real_settings.storage_dir / "zoho_mock").glob("*.jsonl") for line in path.read_text("utf-8").splitlines()]
    assert lines                                                                     # the mock Zoho recorded the write
    catalogue = client.get("/v1/voice/catalogue?lang=hi").json()
    assert len(catalogue["prompts"]) > 50 and catalogue["version"] != "missing"
    meta = client.get("/v1/meta").json()
    assert "Apple" in meta["supported_crops"] and meta["providers"]["zoho"] == "mock"


# ------------------------------------------------------------------------------------------------ demo steering and the stub crop gate
def login_headers(client) -> dict[str, str]:
    body = client.post("/v1/auth/otp/request", json={"phone": "+910000000001"}).json()
    token = client.post("/v1/auth/otp/verify", json={"request_id": body["request_id"], "otp": body["dev_otp"]}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


def test_demo_disease_hints_from_the_settings_steer_the_whole_pipeline():
    """DEMO_DISEASE_HINTS alone (no code) makes the offline demo show the scab advice path."""
    settings = Settings(_env_file=None, demo_disease_hints="Apple=Apple___Apple_scab:0.9")
    container = build_container(settings)
    with TestClient(create_app(settings, container_factory=lambda _s: container), raise_server_exceptions=False) as client:
        body = scan(client, login_headers(client), textured_leaf(), client_crop="Apple", client_confidence="0.95").json()
    assert body["status"] == "ok" and body["disease"]["disease_id"] == "Apple___Apple_scab" and body["advice"]["products"]
    assert body["disease"]["confidence"] == 0.9


def test_a_hint_for_another_disease_sends_the_scan_to_the_expert_queue():
    settings = Settings(_env_file=None, demo_disease_hints="Apple=Apple___Alternaria_leaf_spot:0.9")
    container = build_container(settings)
    with TestClient(create_app(settings, container_factory=lambda _s: container), raise_server_exceptions=False) as client:
        body = scan(client, login_headers(client), textured_leaf(), client_crop="Apple", client_confidence="0.95").json()
    assert body["status"] == "needs_expert" and body["advice"]["products"] == [] and body["review_task_id"]


def test_the_stub_crop_identifier_honours_the_crop_the_app_sends(real):
    client, headers, _container = real                                                  # farmer F001 grows apple
    sure = scan(client, headers, textured_leaf(), client_crop="Apple", client_confidence="0.95").json()["crop"]
    assert (sure["crop_id"], sure["needs_confirmation"], sure["source"]) == ("Apple", False, "on_device")
    other = scan(client, headers, textured_leaf(), client_crop="Tomato", client_confidence="0.95").json()
    assert other["status"] == "confirm_crop" and other["crop"]["crop_id"] == "Tomato"       # the guess leads, the farmer is asked
    assert other["crop"]["needs_confirmation"] is True and other["advice"] is None
    unsure = scan(client, headers, textured_leaf(), client_crop="apple").json()["crop"]    # no confidence: still the app's crop
    assert unsure["crop_id"] == "Apple"
