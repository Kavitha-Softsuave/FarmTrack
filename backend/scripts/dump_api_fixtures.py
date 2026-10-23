"""Records REAL backend answers as JSON fixtures for the Flutter contract test (mobile/test/contract_fixtures_test.dart).

    backend\\.venv\\Scripts\\python backend\\scripts\\dump_api_fixtures.py [--out DIR]

The backend runs IN-PROCESS (FastAPI TestClient): no network, no real provider, no real key, and the repo-root .env is never
read (every setting is given explicitly and `Settings.model_config["env_file"]` is switched off before anything loads settings).
Only the disease result is forced (a hinted StubDiseaseClassifier), exactly like the backend's own smoke tests; rules, composer,
knowledge base, Zoho/weather/IoT mocks, auth, rate limits, error handlers and middleware are the real ones.

One file per scenario: {"request": {...}, "status": int, "response_headers": {...}, "body": <JSON>, "note": "..."}.
Ids are rewritten to deterministic 32-hex values (same real id -> same fixed id, so references between files still match) and
login tokens are replaced by placeholders, so a re-run produces the same files unless the backend's behaviour changed.
Only demo farmers (data/farmers.csv, fabricated numbers) appear in the files.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import sys
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

DEFAULT_OUT = REPO / "mobile" / "test" / "fixtures" / "api"
LEAF_DIR = REPO / "data" / "images" / "testset_v1" / "leaf"
SCAB_PHOTO = LEAF_DIR / "Apple___Apple_scab" / "SCB_09.jpg"
MARSSONINA_PHOTO = LEAF_DIR / "Apple___Marssonina_blotch" / "MAR_01.jpg"
ALTERNARIA_PHOTO = LEAF_DIR / "Apple___Alternaria_leaf_spot" / "ALT_01.jpg"

# Demo clocks (data/demo_scenarios.json). The default one gives a red scab risk for farmer F001 (scenario S1).
CLOCK_S1 = "2026-05-12T16:00:00+05:30"
CLOCK_RAIN_AHEAD = "2026-04-30T08:00:00+05:30"            # 11 mm of rain in the next 12 hours at station ST01
CLOCK_WASHOFF = "2026-03-30T20:00:00+05:30"               # F007: 15 mm of rain within 12 hours of a mancozeb spray (S3)
CLOCK_STALE_SENSOR = "2026-07-13T12:00:00+05:30"          # station ST08 is offline 10-14 Jul 2026
ALERT_CLOCKS = ("2026-03-30T20:00:00+05:30", "2026-05-04T21:00:00+05:30", CLOCK_S1, "2026-07-05T08:00:00+05:30",
                "2026-07-12T08:00:00+05:30", "2026-07-12T09:00:00+05:30")

SCAB = ("Apple___Apple_scab", 0.9)

# Everything explicit, so the process environment and the repo .env can never switch a real provider on.
OFFLINE_ENV = {
    "ENV": "dev", "LLM_PROVIDER": "mock", "OPENAI_API_KEY": "", "TTS_PROVIDER": "null", "GOOGLE_TTS_API_KEY": "",
    "EMBEDDINGS_PROVIDER": "hash", "VECTOR_STORE": "memory", "PUSH_PROVIDER": "log", "ZOHO_PROVIDER": "mock",
    "IOT_PROVIDER": "mock", "WEATHER_PROVIDER": "csv", "CROP_ID_PROVIDER": "stub", "DISEASE_PROVIDER": "stub",
    "FCM_CREDENTIALS_FILE": "", "DEMO_DISEASE_HINTS": "", "ALERT_SCHEDULER": "0", "DEMO_CLOCK": CLOCK_S1,
    "OTP_LOGIN_ENABLED": "1", "DEMO_PASSWORD": "farm1234",   # OTP routes on only so their fixtures can still be recorded
}
DEMO_PASSWORD = OFFLINE_ENV["DEMO_PASSWORD"]

_HEX32 = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])")
_KEPT_RESPONSE_HEADERS = ("idempotent-replayed", "retry-after", "etag", "content-type", "www-authenticate")


class FakeTTS:
    """Offline stand-in for a TTS provider so the scenarios with audio references exist (the bytes are not real mp3)."""

    name = "fake"

    def synthesize(self, text: str, lang: str, speed: float = 0.9) -> bytes | None:
        return b"ID3-fixture-" + hashlib.sha256(f"{lang}|{text}".encode()).digest()


class Dump:
    def __init__(self, client: Any, app: Any) -> None:
        self.client = client
        self.app = app
        self.fixtures: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.failures: list[str] = []

    # ------------------------------------------------------------------------------------------ helpers
    @property
    def container(self) -> Any:
        return self.app.state.container

    def set_clock(self, iso: str) -> None:
        self.container.clock.set(datetime.fromisoformat(iso))

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def call(self, name: str, method: str, path: str, *, token: str | None = None, headers: dict[str, str] | None = None,
             json_body: Any = None, form: dict[str, str] | None = None, files: list[tuple[str, bytes, str]] | None = None,
             file_notes: list[str] | None = None, params: dict[str, Any] | None = None, note: str | None = None,
             record: bool = True, expect: int | None = None) -> tuple[int, Any]:
        """Performs one real request and (when `record`) stores it as fixture `name`. Returns (status, parsed body)."""
        send_headers = dict(headers or {})
        if token:
            send_headers["Authorization"] = f"Bearer {token}"
        kwargs: dict[str, Any] = {"headers": send_headers, "params": params}
        if json_body is not None:
            kwargs["json"] = json_body
        if files is not None:
            kwargs["files"] = [("photos", (filename, data, ctype)) for filename, data, ctype in files]
            kwargs["data"] = form or {}
        response = self.client.request(method, path, **kwargs)
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        if expect is not None and response.status_code != expect:
            self.warn(f"{name}: expected HTTP {expect}, got {response.status_code}")
        if path == "/v1/alerts" and isinstance(body, dict) and isinstance(body.get("items"), list):
            # alerts created at the same demo-clock instant have random ids, so their order would change on every run
            body["items"].sort(key=lambda a: (a.get("created_at", ""), a.get("kind", "")), reverse=True)
        if record:
            request: dict[str, Any] = {"method": method, "path": path, "auth": "bearer" if token else "none"}
            if params:
                request["query"] = params
            kept = {k: v for k, v in (headers or {}).items()}
            if kept:
                request["headers"] = kept
            if json_body is not None:
                request["json"] = json_body
            if files is not None:
                request["form"] = form or {}
                request["files"] = [{"field": "photos", "filename": f, "content_type": c, "source": file_notes[i] if file_notes else f}
                                    for i, (f, _d, c) in enumerate(files)]
            fixture: dict[str, Any] = {"request": request, "status": response.status_code}
            shown = {k: v for k, v in response.headers.items() if k.lower() in _KEPT_RESPONSE_HEADERS}
            if shown:
                fixture["response_headers"] = shown
            fixture["body"] = body
            if note:
                fixture["note"] = note
            self.fixtures.append({"name": name, "data": fixture})
        return response.status_code, body

    def scenario(self, label: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception:                                   # one broken scenario must not hide the others
            self.failures.append(f"{label}: {traceback.format_exc(limit=3)}")

    def login(self, phone: str, name: str | None = None, device_id: str | None = "") -> dict[str, Any]:
        """Password login of a demo farmer (username = farmer id in lower case, password = DEMO_PASSWORD). The farmer is found by
        the demo phone number (+9100000000NN is F0NN, username f0nn). `device_id=None` sends null; "" means a fixture device id."""
        body: dict[str, Any] = {"username": f"f{phone[-3:]}", "password": DEMO_PASSWORD,
                                "device_id": None if device_id is None else (device_id or f"fixture-device-{phone[-4:]}")}
        _status, tokens = self.call(name or "x", "POST", "/v1/auth/login", json_body=body, record=name is not None, expect=200)
        return tokens

    def otp_login(self, phone: str, name: str | None = None, device_id: str | None = "") -> dict[str, Any]:
        """OTP request + verify (the OTP routes are switched on for this recording through OTP_LOGIN_ENABLED).
        `device_id=None` sends none; "" means a fixture device id."""
        _status, request = self.call(f"{name}_request" if name else "x", "POST", "/v1/auth/otp/request", json_body={"phone": phone},
                                     record=name is not None, expect=200)
        body: dict[str, Any] = {"request_id": request["request_id"], "otp": request["dev_otp"]}
        if device_id is not None:
            body["device_id"] = device_id or f"fixture-device-{phone[-4:]}"
        _status, tokens = self.call(f"{name}_verify" if name else "x", "POST", "/v1/auth/otp/verify", json_body=body,
                                    record=name is not None, expect=200)
        return tokens

    def scan(self, name: str, token: str, photos: list[tuple[str, bytes, str]], notes: list[str], hints: dict[str, Any],
             form: dict[str, str] | None = None, headers: dict[str, str] | None = None, expect_status: str | None = None,
             note: str | None = None) -> dict[str, Any]:
        from app.vision.disease import StubDiseaseClassifier

        self.container.disease_classifier = StubDiseaseClassifier(hints=hints)
        code, body = self.call(name, "POST", "/v1/scans", token=token, headers=headers, form=form, files=photos, file_notes=notes,
                               note=note, expect=200)
        if expect_status and isinstance(body, dict) and body.get("status") != expect_status:
            self.warn(f"{name}: expected scan status {expect_status}, got {body.get('status')}")
        return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------------------------- images
def real_photo(path: Path) -> tuple[tuple[str, bytes, str], str]:
    return (path.name, path.read_bytes(), "image/jpeg"), path.relative_to(REPO).as_posix()


def generated_photo(kind: str) -> tuple[tuple[str, bytes, str], str]:
    from PIL import Image, ImageFilter

    if kind == "dark":
        image = Image.new("RGB", (60, 60), (10, 10, 10))
    elif kind == "bright":
        image = Image.new("RGB", (640, 640), (252, 252, 252))
    elif kind == "blurry":
        base = Image.open(SCAB_PHOTO).convert("RGB").resize((640, 480))
        image = base.resize((24, 18)).resize((640, 480)).filter(ImageFilter.GaussianBlur(6))
    else:
        raise ValueError(kind)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return (f"{kind}.jpg", buffer.getvalue(), "image/jpeg"), f"generated: {kind} jpeg ({image.width}x{image.height})"


# ---------------------------------------------------------------------------------------------- scenarios
def run_all(d: Dump) -> None:
    from app.alerts.evaluator import run_once
    from app.db.session import session_scope
    from app.security.ratelimit import RateLimiters
    from app.voice.store import FileAudioStore

    d.set_clock(CLOCK_S1)

    # ---- public
    d.call("health", "GET", "/health", expect=200)
    d.call("meta", "GET", "/v1/meta", expect=200)
    d.call("voice_catalogue_hi", "GET", "/v1/voice/catalogue", params={"lang": "hi"}, expect=200)
    _status, catalogue = d.call("voice_catalogue_en", "GET", "/v1/voice/catalogue", params={"lang": "en"}, expect=200)
    if isinstance(catalogue, dict):
        d.call("voice_catalogue_not_modified", "GET", "/v1/voice/catalogue", params={"lang": "en"},
               headers={"If-None-Match": f'"{catalogue["version"]}-en"'}, expect=304,
               note="Sent with If-None-Match: the app does not do this yet; a 304 has no body.")
    d.call("error_422_voice_lang", "GET", "/v1/voice/catalogue", params={"lang": "xx"}, expect=422)

    # ---- login (farmer F001, Apple, Theog, Hindi)
    d.otp_login("+910000000001", name="otp", device_id=None)        # the OTP login: kept in the code, off by default (OTP_LOGIN_ENABLED)
    tokens = d.login("+910000000001", name="auth_login", device_id=None)   # the MVP login: username + password
    token = tokens["access_token"]
    d.call("auth_login_invalid", "POST", "/v1/auth/login", json_body={"username": "f001", "password": "not-the-password", "device_id": None},
           expect=401, note="Wrong password. An unknown username gives exactly the same 401 invalid_credentials.")
    d.call("me", "GET", "/v1/me", token=token, expect=200)
    d.call("patch_me_language", "PATCH", "/v1/me", token=token, json_body={"language": "en"}, expect=200)
    d.call("patch_me_name_422", "PATCH", "/v1/me", token=token, json_body={"name": "   "}, expect=422)
    d.call("patch_me_restore", "PATCH", "/v1/me", token=token, json_body={"language": "hi"}, record=False)
    d.call("devices_register", "POST", "/v1/devices", token=token,
           json_body={"platform": "android", "push_token": "fixture-push-token-0001", "app_version": "1.0.0+1"}, expect=204)
    d.call("devices_register_422", "POST", "/v1/devices", token=token, json_body={"platform": "windows", "push_token": "x"}, expect=422)

    # ---- scans
    scab_photo, scab_note = real_photo(SCAB_PHOTO)
    form_apple = {"client_crop": "Apple", "client_confidence": "0.9"}
    ok = d.scan("scan_ok_scab", token, [scab_photo], [scab_note], {"Apple": SCAB}, form_apple, expect_status="ok",
                note="Apple scab, hinted 0.9: the only auto-advice route.")
    advice = ok.get("advice") or {}
    d.call("scan_get", "GET", f"/v1/scans/{ok.get('id')}", token=token, expect=200)

    dark, dark_note = generated_photo("dark")
    d.scan("scan_photo_unusable_dark", token, [dark], [dark_note], {}, expect_status="photo_unusable")
    blurry, blurry_note = generated_photo("blurry")
    d.scan("scan_photo_unusable_blurry", token, [blurry], [blurry_note], {}, note="Whatever the quality checker says for a blurred photo.")
    bright, bright_note = generated_photo("bright")
    d.scan("scan_photo_unusable_bright", token, [bright], [bright_note], {}, note="Whatever the quality checker says for a white photo.")

    confirm = d.scan("scan_confirm_crop", token, [scab_photo], [scab_note], {"Apple": SCAB}, expect_status="confirm_crop",
                     note="No client_crop: the farmer's only crop is proposed and must be confirmed.")
    if confirm.get("id"):
        d.call("crop_confirm", "POST", f"/v1/scans/{confirm['id']}/crop", token=token, json_body={"crop_id": "Apple"}, expect=200)
        d.call("error_crop_confirm_unknown_crop", "POST", f"/v1/scans/{confirm['id']}/crop", token=token,
               json_body={"crop_id": "Dragonfruit"}, expect=422)
        d.call("error_crop_confirm_422_body", "POST", f"/v1/scans/{confirm['id']}/crop", token=token, json_body={}, expect=422)

    marssonina_photo, marssonina_note = real_photo(MARSSONINA_PHOTO)
    expert = d.scan("scan_needs_expert_marssonina", token, [marssonina_photo], [marssonina_note],
                    {"Apple": ("Apple___Marssonina_blotch", 0.9)}, form_apple, expect_status="needs_expert")
    alternaria_photo, alternaria_note = real_photo(ALTERNARIA_PHOTO)
    d.scan("scan_needs_expert_alternaria", token, [alternaria_photo], [alternaria_note],
           {"Apple": ("Apple___Alternaria_leaf_spot", 0.9)}, form_apple, expect_status="needs_expert")
    d.scan("scan_needs_expert_low_confidence", token, [scab_photo], [scab_note], {"Apple": ("Apple___Apple_scab", 0.4)}, form_apple,
           expect_status="needs_expert", note="Scab at confidence 0.4: below the advice threshold, so the expert queue.")
    d.scan("scan_needs_expert_no_disease_result", token, [scab_photo], [scab_note], {}, form_apple, expect_status="needs_expert",
           note="The disease model returned nothing.")
    d.scan("scan_not_a_disease", token, [scab_photo], [scab_note], {"Apple": ("Apple___healthy", 0.9)}, form_apple,
           expect_status="not_a_disease")

    pea = d.scan("scan_confirm_crop_pea", token, [scab_photo], [scab_note], {}, {"client_crop": "Pea", "client_confidence": "0.9"},
                 expect_status="confirm_crop", note="A crop the farmer does not grow and no approved data exists for.")
    if pea.get("id"):
        d.call("crop_confirm_no_approved_data", "POST", f"/v1/scans/{pea['id']}/crop", token=token, json_body={"crop_id": "Pea"},
               expect=200)

    if expert.get("id"):
        extra, extra_note = real_photo(MARSSONINA_PHOTO.with_name("MAR_02.jpg"))
        d.call("scan_add_photos", "POST", f"/v1/scans/{expert['id']}/photos", token=token, files=[extra], file_notes=[extra_note],
               form={}, expect=200)

    key_scan = "fixture-scan-key-0001"
    d.scan("scan_idempotent_first", token, [scab_photo], [scab_note], {"Apple": SCAB}, form_apple, headers={"Idempotency-Key": key_scan})
    d.scan("scan_idempotent_replay", token, [scab_photo], [scab_note], {"Apple": SCAB}, form_apple, headers={"Idempotency-Key": key_scan},
           note="Same Idempotency-Key again: a backend with idempotency answers with the first scan's id and "
                "'Idempotent-Replayed: true'; an older one creates a second scan.")

    d.scenario("analysis_unavailable", lambda: _analysis_down(d, token, scab_photo, scab_note))
    d.set_clock(CLOCK_RAIN_AHEAD)
    d.scan("scan_ok_scab_rain_expected", token, [scab_photo], [scab_note], {"Apple": SCAB}, form_apple,
           note="Heavy rain in the next 12 hours: the timing action is not spray_now.")
    d.set_clock(CLOCK_S1)

    d.call("scan_list", "GET", "/v1/scans", token=token, params={"limit": 20}, expect=200)
    _s, page = d.call("scan_list_paged", "GET", "/v1/scans", token=token, params={"limit": 2}, expect=200)
    if isinstance(page, dict) and page.get("next_cursor"):
        d.call("scan_list_page2", "GET", "/v1/scans", token=token, params={"limit": 2, "cursor": page["next_cursor"]}, expect=200)

    # ---- scans with audio references (a fake TTS makes the store return urls)
    plain_audio = d.container.audio
    d.container.audio = FileAudioStore(d.container.settings.storage_dir, FakeTTS(), {"hi": "fixture-hi", "en": "fixture-en"})
    with_audio = d.scan("scan_ok_scab_with_audio", token, [scab_photo], [scab_note], {"Apple": SCAB}, form_apple,
                        note="Same as scan_ok_scab, but the server had a TTS provider (fake, offline): audio refs are filled.")
    for lang, ref in ((with_audio.get("spoken") or {}).get("audio") or {}).items():
        if ref and ref.get("url"):
            d.call("audio_fetch", "GET", ref["url"], expect=200,
                   note=f"The {lang} audio url of scan_ok_scab_with_audio.spoken (binary body is not stored).")
            break
    d.call("error_404_audio", "GET", "/audio/" + "0" * 64 + ".mp3", expect=404)
    d.call("ask_answered_with_audio", "POST", "/v1/ask", token=token,
           json_body={"question": "What should I do if it rains after spraying?", "language": "en", "crop_id": "Apple"}, expect=200)
    d.container.audio = plain_audio

    # ---- spray diary
    product_id = (advice.get("products") or [{}])[0].get("product_id")
    advice_id = advice.get("id")
    if product_id and advice_id:
        d.call("spray_log_product", "POST", "/v1/spray-logs", token=token,
               json_body={"crop_id": "Apple", "advice_id": advice_id, "product_id": product_id, "notes": "Contract fixture"}, expect=200)
    else:
        d.warn("spray_log_product skipped: the scab scan returned no advice product")
    if advice_id:
        d.call("spray_log_advice_only", "POST", "/v1/spray-logs", token=token, json_body={"crop_id": "Apple", "advice_id": advice_id},
               note="The plain 'I sprayed this' tick: only advice_id (an older backend answers 4xx).")
        d.call("error_spray_advice_not_found", "POST", "/v1/spray-logs", token=token,
               json_body={"crop_id": "Apple", "advice_id": "f" * 32, "product_id": product_id or "P001"}, expect=404)
    d.call("spray_log_free_text", "POST", "/v1/spray-logs", token=token, json_body={"crop_id": "Apple", "free_text": "mancozeb"},
           expect=200)
    d.call("spray_log_free_text_unrecognised", "POST", "/v1/spray-logs", token=token,
           json_body={"crop_id": "Apple", "free_text": "my own homemade mix"})
    key_spray = "fixture-spray-key-0001"
    body = {"crop_id": "Apple", "free_text": "mancozeb", "sprayed_at": "2026-05-12T10:00:00+05:30"}
    d.call("spray_log_idempotent_first", "POST", "/v1/spray-logs", token=token, headers={"Idempotency-Key": key_spray}, json_body=body)
    d.call("spray_log_idempotent_replay", "POST", "/v1/spray-logs", token=token, headers={"Idempotency-Key": key_spray}, json_body=body,
           note="Same Idempotency-Key again: the same id and 'Idempotent-Replayed: true' on a backend with idempotency.")
    d.call("spray_logs_list", "GET", "/v1/spray-logs", token=token, params={"limit": 50}, expect=200)
    d.call("error_422_spray_missing_crop", "POST", "/v1/spray-logs", token=token, json_body={"free_text": "mancozeb"}, expect=422)

    # ---- field (normal)
    d.call("field", "GET", "/v1/field", token=token, expect=200)

    # ---- ask and expert
    ask_text = "What should I do if it rains after spraying?"
    d.call("ask_answered", "POST", "/v1/ask", token=token, json_body={"question": ask_text, "language": "en", "crop_id": "Apple"},
           expect=200)
    d.call("ask_answered_hi", "POST", "/v1/ask", token=token,
           json_body={"question": "स्प्रे के बाद बारिश हो जाए तो क्या करूँ?", "language": "hi", "crop_id": "Apple"})
    d.call("ask_refused_pea", "POST", "/v1/ask", token=token, json_body={"question": "Which medicine for my pea crop?", "language": "en"},
           expect=200)
    d.call("ask_refused_nonsense", "POST", "/v1/ask", token=token,
           json_body={"question": "Who will win the lottery?", "language": "en"})
    d.call("error_422_ask_empty", "POST", "/v1/ask", token=token, json_body={"question": "", "language": "en"}, expect=422)
    d.call("error_422_ask_language", "POST", "/v1/ask", token=token, json_body={"question": "hello there", "language": "fr"}, expect=422)
    if expert.get("id"):
        d.call("expert_request_with_scan", "POST", "/v1/expert-requests", token=token,
               json_body={"scan_id": expert["id"], "message": "Please look at these spots."}, expect=200)
    d.call("expert_request_without_scan", "POST", "/v1/expert-requests", token=token,
           json_body={"message": "Leaves of my apple tree are curling."}, expect=200)
    d.call("expert_request_empty", "POST", "/v1/expert-requests", token=token, json_body={}, expect=200,
           note="No scan and no message: the smallest valid body (what the app sends from the result screen has a scan_id).")
    key_expert = "fixture-expert-key-0001"
    d.call("expert_request_idempotent_first", "POST", "/v1/expert-requests", token=token, headers={"Idempotency-Key": key_expert},
           json_body={"message": "Idempotency check."})
    d.call("expert_request_idempotent_replay", "POST", "/v1/expert-requests", token=token, headers={"Idempotency-Key": key_expert},
           json_body={"message": "Idempotency check."})
    d.call("error_expert_request_scan_not_found", "POST", "/v1/expert-requests", token=token, json_body={"scan_id": "e" * 32}, expect=404)

    # ---- other farmers
    d.scenario("scan_needs_expert_crop_unknown", lambda: _unknown_crop(d, scab_photo, scab_note))
    d.scenario("scan_ok_scab_after_washoff", lambda: _washoff_scan(d, scab_photo, scab_note))
    d.scenario("field_stale", lambda: _stale_field(d))
    d.scenario("auth_edge_cases", lambda: _auth_edges(d))

    # ---- errors
    d.call("error_401_no_token", "GET", "/v1/me", expect=401)
    d.call("error_401_bad_token", "GET", "/v1/me", token="not-a-token", expect=401)
    d.call("error_404_scan", "GET", f"/v1/scans/{'a' * 32}", token=token, expect=404)
    d.call("error_404_scan_not_hex", "GET", "/v1/scans/does-not-exist", token=token)
    d.call("error_422_otp_phone", "POST", "/v1/auth/otp/request", json_body={"phone": "abc"}, expect=422)
    d.call("error_422_scan_no_photo", "POST", "/v1/scans", token=token, form={"client_crop": "Apple"}, files=[], expect=422)
    d.call("error_400_bad_image", "POST", "/v1/scans", token=token, files=[("notes.txt", b"this is not an image", "text/plain")],
           form={}, expect=400)
    d.call("error_400_client_crop", "POST", "/v1/scans", token=token, files=[scab_photo], form={"client_crop": "<<bad>>"}, expect=400)
    d.call("error_400_idempotency_key", "POST", "/v1/spray-logs", token=token, headers={"Idempotency-Key": "x"},
           json_body={"crop_id": "Apple", "free_text": "mancozeb"})
    d.call("otp_request_unregistered", "POST", "/v1/auth/otp/request", json_body={"phone": "+910000000999"}, expect=200,
           note="Unregistered number: same 200 answer, dev_otp is null (no account enumeration).")
    _s, req = d.call("x", "POST", "/v1/auth/otp/request", json_body={"phone": "+910000000002"}, record=False)
    d.call("error_otp_wrong_code", "POST", "/v1/auth/otp/verify",
           json_body={"request_id": (req or {}).get("request_id", "x"), "otp": "000000"}, expect=400)
    d.call("error_otp_unknown_request", "POST", "/v1/auth/otp/verify", json_body={"request_id": "nope", "otp": "123456"})
    d.scenario("otp_used_and_exhausted", lambda: _otp_edges(d))
    d.scenario("rate_limit", lambda: _rate_limit(d))

    # ---- alerts: the real evaluator runs on several demo clocks, then the app's endpoints read the result
    def alerts_phase() -> None:
        d.app.state.limiters = RateLimiters.default()
        farmers = {fid: d.login(phone) for fid, phone in (("F001", "+910000000001"), ("F007", "+910000000007"),
                                                       ("F032", "+910000000032"), ("F036", "+910000000036"))}
        for iso in ALERT_CLOCKS:
            d.set_clock(iso)
            with session_scope() as session:
                created = run_once(session, d.container)
            print(f"  alerts at {iso}: {len(created)} new")
        d.set_clock(CLOCK_S1)
        t1 = farmers["F001"]["access_token"]
        _s, listing = d.call("alerts_list", "GET", "/v1/alerts", token=t1, params={"limit": 30}, expect=200,
                             note="Farmer F001 after the evaluator ran on six demo clocks.")
        d.call("alerts_list_washoff_farmer", "GET", "/v1/alerts", token=farmers["F007"]["access_token"], note="F007: rain wash-off, S3.")
        d.call("alerts_list_late_blight_farmer", "GET", "/v1/alerts", token=farmers["F032"]["access_token"], note="F032: S7.")
        d.call("alerts_list_stale_sensor_farmer", "GET", "/v1/alerts", token=farmers["F036"]["access_token"],
               note="F036 at the offline station ST08: S11 (alerts say they use the forecast only).")
        items = (listing or {}).get("items") or []
        if items:
            d.call("alert_mark_read", "POST", f"/v1/alerts/{items[0]['id']}/read", token=t1, expect=200)
            d.call("alerts_list_after_read", "GET", "/v1/alerts", token=t1, expect=200)
        else:
            d.warn("alerts: F001 has no alert (the clocks no longer give a risk?)")
        d.call("error_404_alert", "POST", f"/v1/alerts/{'b' * 32}/read", token=t1, expect=404)

        # A spray logged from a scan's advice shortly before harvest: the waiting-period alert points back at that scan.
        if advice_id:
            d.set_clock("2026-09-01T09:00:00+05:30")
            d.call("x", "POST", "/v1/spray-logs", token=t1, json_body={"crop_id": "Apple", "advice_id": advice_id}, record=False)
            d.set_clock("2026-09-01T09:30:00+05:30")
            with session_scope() as session:
                print(f"  alerts at 2026-09-01T09:30: {len(run_once(session, d.container))} new")
            d.call("alerts_list_waiting_period", "GET", "/v1/alerts", token=t1, params={"limit": 5},
                   note="Waiting-period alert of a spray taken from a scan's advice: scan_id is set.")
            d.set_clock(CLOCK_S1)

    d.scenario("alerts", alerts_phase)


class _BrokenDisease:
    """A disease model that fails: the scan answers 503 analysis_unavailable and stores nothing."""

    def classify(self, images: list[bytes], crop_id: str) -> Any:
        raise RuntimeError("model unavailable (fixture)")


def _analysis_down(d: Dump, token: str, photo: tuple[str, bytes, str], note: str) -> None:
    previous = d.container.disease_classifier
    d.container.disease_classifier = _BrokenDisease()
    try:
        d.call("error_503_analysis_unavailable", "POST", "/v1/scans", token=token, files=[photo], file_notes=[note],
               form={"client_crop": "Apple", "client_confidence": "0.9"}, expect=503)
    finally:
        d.container.disease_classifier = previous


def _unknown_crop(d: Dump, photo: tuple[str, bytes, str], note: str) -> None:
    tokens = d.login("+910000000035")                       # F035 grows Apple and Potato, station ST08
    d.scan("scan_needs_expert_crop_unknown", tokens["access_token"], [photo], [note], {}, expect_status="needs_expert",
           note="Two crops and no guess: crop.unknown is true, candidates list both, and the scan goes to the expert queue.")


def _washoff_scan(d: Dump, photo: tuple[str, bytes, str], note: str) -> None:
    tokens = d.login("+910000000007")                       # F007 sprayed mancozeb the same morning (demo scenario S3)
    d.set_clock(CLOCK_WASHOFF)
    d.scan("scan_ok_scab_after_washoff", tokens["access_token"], [photo], [note], {"Apple": SCAB},
           {"client_crop": "Apple", "client_confidence": "0.9"},
           note="Heavy rain fell soon after the farmer's last spray: the advice says to repeat it.")
    d.set_clock(CLOCK_S1)


def _stale_field(d: Dump) -> None:
    tokens = d.login("+910000000036")                       # F036, Apple, station ST08 (sensor offline in July)
    d.set_clock(CLOCK_STALE_SENSOR)
    d.call("field_stale", "GET", "/v1/field", token=tokens["access_token"], expect=200, note="Station ST08 is offline on this clock.")
    d.set_clock(CLOCK_S1)


def _auth_edges(d: Dump) -> None:
    tokens = d.login("+910000000003")
    old_refresh = tokens["refresh_token"]
    d.call("auth_refresh", "POST", "/v1/auth/refresh", json_body={"refresh_token": old_refresh}, expect=200)
    d.call("error_refresh_replayed", "POST", "/v1/auth/refresh", json_body={"refresh_token": old_refresh}, expect=401,
           note="A rotated token used again: the device's sessions are revoked.")
    d.call("error_refresh_garbage", "POST", "/v1/auth/refresh", json_body={"refresh_token": "garbage"}, expect=401)
    again = d.login("+910000000004")
    d.call("auth_logout", "POST", "/v1/auth/logout", json_body={"refresh_token": again["refresh_token"]}, expect=204)


def _otp_edges(d: Dump) -> None:
    _s, req = d.call("x", "POST", "/v1/auth/otp/request", json_body={"phone": "+910000000005"}, record=False)
    good = {"request_id": req["request_id"], "otp": req["dev_otp"]}
    d.call("x", "POST", "/v1/auth/otp/verify", json_body=good, record=False, expect=200)
    d.call("error_otp_already_used", "POST", "/v1/auth/otp/verify", json_body=good, expect=400)
    _s, req = d.call("x", "POST", "/v1/auth/otp/request", json_body={"phone": "+910000000006"}, record=False)
    wrong = {"request_id": req["request_id"], "otp": "000000"}
    for i in range(6):
        d.call("error_otp_attempts_exceeded" if i == 5 else "x", "POST", "/v1/auth/otp/verify", json_body=wrong, record=(i == 5))


def _rate_limit(d: Dump) -> None:
    for i in range(4):
        d.call(f"otp_rate_limit_{i}", "POST", "/v1/auth/otp/request", json_body={"phone": "+910000000010"},
               record=(i == 3), expect=429 if i == 3 else 200)
    d.fixtures[-1]["name"] = "error_429_otp_rate_limit"


# ---------------------------------------------------------------------------------------------- output
def stabilise(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic ids (32-hex stays 32-hex, same id -> same value) and no token-looking strings."""
    text = json.dumps([f["data"] for f in fixtures], ensure_ascii=False)
    mapping: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        real = match.group(0)
        if real not in mapping:
            mapping[real] = hashlib.sha256(f"farmtrack-fixture-id-{len(mapping)}".encode()).hexdigest()[:32]
        return mapping[real]

    text = _HEX32.sub(replace, text)
    data = json.loads(text)
    for item in data:
        body = item.get("body")
        if isinstance(body, dict):
            if isinstance(body.get("access_token"), str):
                body["access_token"] = "FIXTURE-ACCESS-TOKEN"
            if isinstance(body.get("refresh_token"), str):
                body["refresh_token"] = "FIXTURE-REFRESH-TOKEN"
        request = item.get("request", {})
        payload = request.get("json")
        if isinstance(payload, dict) and isinstance(payload.get("refresh_token"), str):
            payload["refresh_token"] = "FIXTURE-REFRESH-TOKEN"
    return [{"name": f["name"], "data": item} for f, item in zip(fixtures, data, strict=True)]


def write_fixtures(fixtures: list[dict[str, Any]], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    seen: set[str] = set()
    for fixture in stabilise(fixtures):
        name = fixture["name"]
        if name in seen:
            raise SystemExit(f"duplicate fixture name {name}")
        seen.add(name)
        (out / f"{name}.json").write_text(json.dumps(fixture["data"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def check_contract_file(app: Any, dump: Dump) -> None:
    """The mobile app reads contracts/openapi.json: warn when it no longer matches the schema of this backend."""
    contract = REPO / "contracts" / "openapi.json"
    try:
        stored = json.loads(contract.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dump.warn("contracts/openapi.json cannot be read")
        return
    if json.dumps(stored, sort_keys=True) != json.dumps(app.openapi(), sort_keys=True):
        dump.warn("contracts/openapi.json is out of date: run  python -m app.export_openapi ../contracts/openapi.json  in backend/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="directory for the *.json files (default: mobile/test/fixtures/api)")
    parser.add_argument("--verbose", action="store_true", help="show the backend's own log lines (silent by default)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="farmtrack-fixtures-", ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        os.environ.update(OFFLINE_ENV)
        os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'fixtures.db').as_posix()}"
        os.environ["STORAGE_DIR"] = str(tmp_path / "storage")

        from app.config import Settings, get_settings

        Settings.model_config["env_file"] = None            # the repo-root .env (real secrets) is never read
        get_settings.cache_clear()
        from app.clock import reset_clock
        from app.db.session import reset_engine

        reset_clock()
        reset_engine()
        settings = get_settings()
        if settings.openai_configured or settings.google_tts_configured or settings.llm_provider != "mock":
            raise SystemExit("refusing to run: a real provider is configured")

        from fastapi.testclient import TestClient

        from app.main import create_app

        app = create_app(settings)
        if not args.verbose:
            logging.getLogger("app").setLevel(logging.CRITICAL)   # the 503 scenario logs a deliberate error
        with TestClient(app, raise_server_exceptions=False) as client:
            dump = Dump(client, app)
            run_all(dump)
        check_contract_file(app, dump)
        reset_engine()

    write_fixtures(dump.fixtures, args.out)
    print(f"wrote {len(dump.fixtures)} fixtures to {args.out}")
    for message in dump.warnings:
        print(f"WARN {message}")
    for message in dump.failures:
        print(f"FAILED scenario {message}")
    return 1 if dump.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
