"""API-level regression tests for the security review (docs/open-questions.md)."""
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db.models import DeviceRow, OtpRequestRow, SprayLogRow
from app.db.session import session_scope
from app.main import create_app
from app.rules.engine import build_rules_engine
from app.security.ratelimit import RateLimiters, SlidingWindowLimiter

PHONE = "+910000000001"


def _request_code(client, phone: str = PHONE) -> dict:
    response = client.post("/v1/auth/otp/request", json={"phone": phone})
    assert response.status_code == 200, response.text
    return response.json()


def _verify(client, request_id: str, otp: str):
    return client.post("/v1/auth/otp/verify", json={"request_id": request_id, "otp": otp})


# ------------------------------------------------------------------------------------------------ OTP guessing
def test_parallel_guesses_never_get_more_than_the_attempt_cap(api_client, api_app):
    """Read-compare-increment let a burst of parallel guesses through (8 comparisons for a cap of 5 in the review run)."""
    api_app.state.limiters = RateLimiters.default()
    api_app.state.limiters.verify_ip = SlidingWindowLimiter(1000, 900)
    request_id = _request_code(api_client)["request_id"]
    cap = api_app.state.settings.otp_max_attempts

    def guess(n: int) -> str:
        response = _verify(api_client, request_id, f"{n + 1:06d}")             # none of these is the dev code 123456
        return response.json()["code"]

    with ThreadPoolExecutor(60) as pool:
        outcomes = Counter(pool.map(guess, [n for n in range(100000, 100060)]))
    assert outcomes["invalid_otp"] <= cap
    assert outcomes["invalid_otp"] + outcomes["otp_attempts_exceeded"] == 60
    with session_scope() as db:
        assert db.get(OtpRequestRow, request_id).attempts == cap


def test_the_right_code_is_refused_after_the_attempt_cap(api_client):
    first = _request_code(api_client)
    for _ in range(5):
        assert _verify(api_client, first["request_id"], "000001").json()["code"] == "invalid_otp"
    assert _verify(api_client, first["request_id"], first["dev_otp"]).json()["code"] == "otp_attempts_exceeded"


def test_wrong_codes_are_limited_per_phone_over_all_of_its_code_requests(api_client, api_app):
    """5 guesses per code and 3 codes per 15 minutes meant ~1,400 guesses a day per number for ever."""
    api_app.state.limiters = RateLimiters.default()
    api_app.state.limiters.verify_ip = SlidingWindowLimiter(1000, 900)
    for _ in range(2):
        code = _request_code(api_client)
        for _ in range(5):
            assert _verify(api_client, code["request_id"], "000001").json()["code"] == "invalid_otp"
    third = _request_code(api_client)
    refused = _verify(api_client, third["request_id"], third["dev_otp"])         # even the RIGHT code: no out-guessing the limit
    assert refused.status_code == 429 and refused.json()["code"] == "rate_limited"
    assert refused.headers["Retry-After"].isdigit()
    other = _request_code(api_client, "+910000000002")                          # another farmer is not affected
    assert _verify(api_client, other["request_id"], other["dev_otp"]).status_code == 200


def test_a_legitimate_typo_still_logs_in(api_client):
    code = _request_code(api_client)
    wrong = _verify(api_client, code["request_id"], "000001")
    assert wrong.status_code == 400 and wrong.json()["details"] == {"attempts_left": 4}
    assert _verify(api_client, code["request_id"], code["dev_otp"]).status_code == 200


# ------------------------------------------------------------------------------------------------ admin key
def test_the_admin_key_cannot_be_out_guessed_the_limit_applies_before_the_comparison(api_client, api_app):
    key = api_app.state.settings.admin_api_key
    url = "/admin/api/v1/farmers"
    assert api_client.get(url, headers={"X-Admin-Key": key}).status_code == 200
    statuses = [api_client.get(url, headers={"X-Admin-Key": "wrong-key-" + str(n)}).status_code for n in range(12)]
    assert statuses[:10] == [403] * 10 and statuses[10:] == [429, 429]
    refused = api_client.get(url, headers={"X-Admin-Key": key})                  # the correct key, from the blocked address
    assert refused.status_code == 429 and refused.json()["code"] == "rate_limited"
    assert "Retry-After" in refused.headers


def test_a_missing_admin_key_is_not_counted_as_a_failure(api_client, api_app):
    for _ in range(15):
        assert api_client.get("/admin/api/v1/farmers").status_code == 401
    key = api_app.state.settings.admin_api_key
    assert api_client.get("/admin/api/v1/farmers", headers={"X-Admin-Key": key}).status_code == 200


# ------------------------------------------------------------------------------------------------ ENV
def _prod_settings(**overrides) -> Settings:
    base = dict(_env_file=None, env="production", secret_key="k" * 40, admin_api_key="a" * 24, cors_origins=["https://example.org"],
                demo_clock=None, seed_demo=False) if "seed_demo" in Settings.model_fields else dict(
        _env_file=None, env="production", secret_key="k" * 40, admin_api_key="a" * 24, cors_origins=["https://example.org"])
    return Settings(**{**base, **overrides})


def test_env_production_behaves_as_prod_docs_hidden_and_no_development_login_code(fake_container, monkeypatch):
    from fastapi.testclient import TestClient

    from app.security.sms import SmsSender

    sent: list[str] = []

    class Capture(SmsSender):
        def send(self, phone: str, message: str) -> None:
            sent.append(message)

    settings = _prod_settings(database_url=fake_container.settings.database_url, voice_dir=fake_container.settings.voice_dir,
                              storage_dir=fake_container.settings.storage_dir)
    assert settings.is_prod and settings.env == "prod"
    monkeypatch.setenv("SEED_DEMO", "1")
    from app.db.session import init_db

    # This test is about docs, login codes and headers; the Alembic schema check has its own tests.
    monkeypatch.setattr("app.main.ensure_schema", lambda _s: init_db())
    app = create_app(settings, container_factory=lambda _s: fake_container, sms_sender=Capture())
    app.state.container = fake_container
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404
        body = client.post("/v1/auth/otp/request", json={"phone": PHONE}).json()
        assert body["dev_otp"] is None
        assert sent and "123456" not in sent[0]
        assert client.post("/v1/auth/otp/verify", json={"request_id": body["request_id"], "otp": "123456"}).status_code == 400
        assert client.get("/health").headers["strict-transport-security"].startswith("max-age=")


# ------------------------------------------------------------------------------------------------ spoken text (public audio)
@pytest.fixture
def real_rules(fake_container, api_settings):
    fake_container.rules = build_rules_engine(api_settings)
    return fake_container


def _spoken_texts(container) -> str:
    return " | ".join(text for _lang, text in container.audio.requests)


def test_what_a_farmer_types_into_the_medicine_field_is_never_spoken_or_published(api_client, auth, real_rules):
    """'<banned active> <anything>' used to come back in the warning and from there into the audio text that is synthesised once
    and served to everyone at /audio/<sha256>.mp3 (a name or phone number would be published, and the voice would read any
    sentence a farmer chose)."""
    typed = "Dicofol sent by Ramesh Kumar of Manali phone 9876543210"
    response = api_client.post("/v1/spray-logs", json={"crop_id": "Apple", "free_text": typed}, headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert "BANNED_PRODUCT" in [w["code"] for w in body["warnings"]]
    assert any(typed in w["text"]["en"] for w in body["warnings"])               # the written warning still names it (the contract)
    spoken = _spoken_texts(real_rules)
    assert "Ramesh" not in spoken and "9876543210" not in spoken and "Manali" not in spoken and "Dicofol" not in spoken
    assert "This medicine is banned" in spoken                                  # the meaning is kept
    assert "Ramesh" not in body["spoken"]["text"]["en"] and "Ramesh" not in body["spoken"]["text"]["hi"]


def test_the_replay_of_that_entry_is_clean_too(api_client, auth, real_rules):
    headers = {**auth, "Idempotency-Key": "typed-text-replay-0001"}
    typed = "Monocrotophos 36% SL by Ramesh Kumar"
    api_client.post("/v1/spray-logs", json={"crop_id": "Apple", "free_text": typed}, headers=headers)
    real_rules.audio.requests.clear()
    replay = api_client.post("/v1/spray-logs", json={"crop_id": "Apple", "free_text": typed}, headers=headers)
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert "Ramesh" not in _spoken_texts(real_rules) and "Ramesh" not in replay.json()["spoken"]["text"]["en"]


def test_a_long_typed_name_is_stored_within_the_column_width(api_client, auth, real_rules):
    typed = "Dicofol " + "x" * 190
    response = api_client.post("/v1/spray-logs", json={"crop_id": "Apple", "free_text": typed}, headers=auth)
    assert response.status_code == 200 and len(response.json()["product_name"]) <= 120
    with session_scope() as db:
        row = db.scalars(select(SprayLogRow)).one()
        assert len(row.product_name) <= 120 and len(row.free_text) == len(typed)


# ------------------------------------------------------------------------------------------------ inputs
def test_a_long_app_version_is_cut_to_the_column_width(api_client, auth):
    response = api_client.post("/v1/devices", json={"platform": "android", "push_token": "tok-123456", "app_version": "1." * 60},
                               headers=auth)
    assert response.status_code == 204
    with session_scope() as db:
        assert len(db.scalars(select(DeviceRow)).one().app_version) <= 20


@pytest.mark.parametrize("name", ["a" * 64 + ".mp3%0A", ("a" * 64 + ".mp3").replace("a", "A", 1), "../" + "a" * 64 + ".mp3"])
def test_audio_names_with_a_trailing_newline_or_other_shapes_are_404(api_client, name):
    assert api_client.get(f"/audio/{name}").status_code == 404


def test_prompt_audio_name_with_a_trailing_newline_is_404(api_client):
    assert api_client.get("/audio-prompts/en/crop_is_apple.mp3%0A").status_code == 404


def test_error_bodies_never_echo_what_was_sent(api_client, auth):
    secret_like = "9876543210-" + "Z" * 30
    bodies = [
        api_client.post("/v1/auth/otp/request", json={"phone": secret_like}),
        api_client.post("/v1/auth/otp/verify", json={"request_id": "x", "otp": secret_like}),
        api_client.post("/v1/ask", json={"question": 12345, "crop_id": secret_like}, headers=auth),
        api_client.post("/v1/spray-logs", json={"crop_id": secret_like}, headers=auth),
    ]
    for response in bodies:
        assert response.status_code in (400, 422), response.text
        assert secret_like not in response.text and "9876543210" not in response.text


def test_threads_do_not_leak_between_tests():
    assert threading.active_count() < 200
