"""Regression tests for the security review (docs/open-questions.md). Each test pins one confirmed finding."""
import json
import logging
import threading
import time
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.admin.auth import MAX_TRACKED_ADDRESSES, LoginThrottle
from app.config import Settings
from app.domain.types import LocalizedText
from app.integrations.errors import WeatherUnavailable
from app.integrations.weather_openmeteo import MAX_CACHED_PLACES, OpenMeteoAdapter
from app.security import uploads
from app.security.errors import ApiError
from app.security.logging import JsonFormatter, RedactingFilter
from app.security.ratelimit import SlidingWindowLimiter, enforce_open
from app.security.startup import InsecureConfigurationError, validate_production_settings
from app.services.speech import without_typed_text
from tests.imaging import make_jpeg

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


# ------------------------------------------------------------------------------------------------ ENV must mean what it says
@pytest.mark.parametrize("raw", ["production", "Production", " PROD ", "prod"])
def test_production_spellings_all_mean_prod(raw):
    assert Settings(_env_file=None, env=raw).is_prod


@pytest.mark.parametrize("raw", ["live", "", "prod-eu", "0"])
def test_an_unknown_env_refuses_to_load_instead_of_running_the_development_defaults(raw):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, env=raw)


def test_env_production_with_development_secrets_is_refused_at_start_up():
    """Before the fix 'production' was treated as dev: fixed login code, dev admin key, open CORS, API docs on."""
    with pytest.raises(InsecureConfigurationError):
        validate_production_settings(Settings(_env_file=None, env="production"))


def test_the_docker_image_defaults_to_prod_so_a_forgotten_env_fails_closed():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    runtime = dockerfile.split("FROM python:3.13-slim\n", 2)[-1]
    assert "ENV=prod" in runtime
    assert "--no-server-header" in dockerfile


# ------------------------------------------------------------------------------------------------ limiters
def test_peek_records_nothing_and_a_full_window_refuses_even_a_good_caller():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 60, clock=lambda: now[0])
    for _ in range(5):
        assert limiter.peek("k").allowed
    assert limiter.hit("k").allowed and limiter.hit("k").allowed
    assert not limiter.peek("k").allowed
    with pytest.raises(ApiError) as caught:
        enforce_open(limiter, "k")
    assert caught.value.status_code == 429 and caught.value.headers and "Retry-After" in caught.value.headers
    now[0] = 61.0
    assert limiter.peek("k").allowed


def test_admin_login_throttle_memory_is_bounded_when_many_addresses_fail():
    throttle = LoginThrottle()
    for n in range(MAX_TRACKED_ADDRESSES + 500):
        throttle.fail(f"2001:db8::{n:x}")
    assert len(throttle._failures) <= MAX_TRACKED_ADDRESSES
    assert throttle.blocked("2001:db8::0") is False             # a single failure never blocks


# ------------------------------------------------------------------------------------------------ spoken text carries nothing typed
def test_typed_text_is_replaced_in_both_languages_and_keeps_the_sentence_readable():
    typed = "Dicofol Ramesh Kumar 9876543210"
    text = LocalizedText(en=f"{typed} is banned. Do not use {typed} again.", hi=f"{typed} पर रोक है।")
    spoken = without_typed_text(text, [typed, None, "  "])
    assert spoken.en == "This medicine is banned. Do not use this medicine again."
    assert spoken.hi == "यह दवा पर रोक है।"
    assert "Ramesh" not in spoken.en + spoken.hi and "9876543210" not in spoken.en + spoken.hi


def test_typed_text_is_matched_without_regard_to_case_and_never_inside_longer_words():
    text = LocalizedText(en="This is a banned thing. THIS IS banned.", hi="")
    assert without_typed_text(text, ["is"]).en == "This this medicine a banned thing. THIS this medicine banned."
    assert without_typed_text(text, []).en == text.en
    assert without_typed_text(LocalizedText(en="DICOFOL is banned.", hi=""), ["dicofol"]).en == "This medicine is banned."


# ------------------------------------------------------------------------------------------------ logs
def test_a_newline_in_a_logged_value_cannot_forge_a_second_log_line():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "path=%s", ("/a\n{\"level\": \"CRITICAL\", \"msg\": \"forged\"}",), None)
    RedactingFilter().filter(record)
    line = JsonFormatter().format(record)
    assert "\n" not in line and "\r" not in line
    assert json.loads(line)["level"] == "INFO"


# ------------------------------------------------------------------------------------------------ decoding is bounded
def test_only_a_few_images_are_decoded_at_the_same_time(monkeypatch):
    running = [0]
    peak = [0]
    guard = threading.Lock()

    def slow_decode(raw: bytes):
        with guard:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with guard:
            running[0] -= 1
        return uploads.CleanImage(raw, 1, 1)

    monkeypatch.setattr(uploads, "_sanitize_image", slow_decode)
    threads = [threading.Thread(target=uploads.sanitize_image, args=(b"x",)) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert 1 <= peak[0] <= uploads.MAX_PARALLEL_DECODES


def test_the_single_copy_path_still_produces_the_same_clean_jpeg():
    for fmt in ("JPEG", "PNG"):
        clean = uploads.sanitize_image(make_jpeg(size=(4000, 3000), exif=(fmt == "JPEG"), fmt=fmt))
        assert max(clean.width, clean.height) == uploads.MAX_LONG_EDGE
        assert clean.data.startswith(b"\xff\xd8") and b"Exif" not in clean.data[:200]


# ------------------------------------------------------------------------------------------------ weather: client coordinates
def _forecast_response() -> httpx.Response:
    times = [f"2026-10-{day:02d}T{hour:02d}:00" for day in (18, 19) for hour in range(24)]
    return httpx.Response(200, json={"hourly": {"time": times, "temperature_2m": [10.0] * len(times),
                                                "relative_humidity_2m": [70.0] * len(times), "precipitation": [0.0] * len(times)}})


def test_open_meteo_cache_is_bounded_and_outbound_calls_are_budgeted():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _forecast_response()

    clock = [0.0]
    adapter = OpenMeteoAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)), monotonic=lambda: clock[0])
    for n in range(MAX_CACHED_PLACES + 40):                       # every request is a place nobody asked for before
        adapter._fetch(30.0 + n * 0.01, 77.0)
        clock[0] += 0.001
    assert len(adapter._cache) <= MAX_CACHED_PLACES
    with pytest.raises(WeatherUnavailable):                       # the hourly budget (600) is used up
        for n in range(700):
            adapter._fetch(10.0 + n * 0.01, 70.0)
    assert len(calls) <= 600
    clock[0] += 3601.0                                            # a new hour
    assert adapter._fetch(55.0, 5.0) is not None
