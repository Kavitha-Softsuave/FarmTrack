"""The voice package end to end without a key: Google TTS over a mock transport -> generate command -> catalogue -> package -> app download.

Nothing here calls Google. The first test pins the exact request shape the real service will receive once a key exists; whether
the default Hindi voice really exists can only be known by a real call (`generate_prompt_audio.py --list-voices`).
"""
import base64
import io
import json
import logging
import sys
import zipfile

import httpx
import pytest

from app.config import get_settings
from app.voice.package import build_package, package_status
from app.voice.prompt_audio import generate_prompt_audio
from app.voice.store import FileAudioStore
from app.voice.tts import GOOGLE_TTS_VOICES_URL, GoogleCloudTTS
from tests.voice.helpers import make_settings
from tests.voice.test_prompt_audio import VOICES, FakeTTS, load_script, write_prompts

KEY = "AIza-mock-key-0987654321"
PROMPTS = [{"id": "welcome", "en": "Welcome.", "hi": "स्वागत है।"}, {"id": "ask_phone", "en": "Type your number.", "hi": "नंबर लिखिए।"}]


class FakeGoogle:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/voices"):
            code = request.url.params["languageCode"]
            names = {"hi-IN": ["hi-IN-Neural2-A", "hi-IN-Wavenet-B"], "en-IN": ["en-IN-Neural2-A"]}.get(code, [])
            return httpx.Response(200, json={"voices": [{"name": n, "languageCodes": [code]} for n in names]})
        text = json.loads(request.content)["input"]["text"]
        return httpx.Response(200, json={"audioContent": base64.b64encode(b"ID3" + text.encode()).decode()})


def google(server: FakeGoogle) -> GoogleCloudTTS:
    return GoogleCloudTTS(KEY, VOICES, client=httpx.Client(transport=httpx.MockTransport(server)), sleep=lambda _s: None)


@pytest.fixture
def prompts_dir(api_settings):
    write_prompts(api_settings.voice_dir, PROMPTS)
    return api_settings.voice_dir


# ------------------------------------------------------------------------------------------------ the Google request
def test_google_requests_have_the_shape_the_real_service_expects(prompts_dir):
    server = FakeGoogle()
    summary = generate_prompt_audio(prompts_dir, google(server), VOICES, speed=0.85)
    assert len(summary.generated) == 4 and not summary.failed
    hindi = next(r for r in server.requests if b"hi-IN" in r.content)
    body = json.loads(hindi.content)
    assert body["voice"] == {"languageCode": "hi-IN", "name": "hi-IN-Neural2-A"}
    assert body["audioConfig"] == {"audioEncoding": "MP3", "speakingRate": 0.85}
    assert body["input"] == {"text": body["input"]["text"]} and body["input"]["text"]
    english = [json.loads(r.content) for r in server.requests if b"en-IN" in r.content]
    assert english and english[0]["voice"]["languageCode"] == "en-IN"
    for request in server.requests:
        assert request.method == "POST" and str(request.url) == "https://texttospeech.googleapis.com/v1/text:synthesize"
        assert request.headers["x-goog-api-key"] == KEY and KEY not in str(request.url)


def test_the_response_is_decoded_into_the_mp3_file(prompts_dir):
    generate_prompt_audio(prompts_dir, google(FakeGoogle()), VOICES)
    assert (prompts_dir / "audio" / "en" / "welcome.mp3").read_bytes() == b"ID3Welcome."
    assert (prompts_dir / "audio" / "hi" / "welcome.mp3").read_bytes().startswith(b"ID3")


def test_the_key_never_appears_in_repr_logs_or_the_manifest(prompts_dir, caplog):
    caplog.set_level(logging.DEBUG)
    tts = google(FakeGoogle())
    generate_prompt_audio(prompts_dir, tts, VOICES)
    failing = GoogleCloudTTS(KEY, VOICES, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}}))))
    assert failing.synthesize("x", "hi") is None
    assert KEY not in repr(tts) and KEY not in str(tts.__dict__.get("_url")) and KEY not in caplog.text
    assert "PERMISSION_DENIED" in caplog.text
    for file in prompts_dir.rglob("*"):
        if file.is_file():
            assert KEY.encode() not in file.read_bytes()


def test_voice_listing_reports_availability_and_failure():
    server = FakeGoogle()
    tts = google(server)
    assert tts.list_voices("hi-IN") == ["hi-IN-Neural2-A", "hi-IN-Wavenet-B"]
    assert str(server.requests[0].url).startswith(GOOGLE_TTS_VOICES_URL) and server.requests[0].headers["x-goog-api-key"] == KEY
    assert KEY not in str(server.requests[0].url)
    denied = GoogleCloudTTS(KEY, VOICES, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={}))))
    assert denied.list_voices("hi-IN") is None
    broken = GoogleCloudTTS(KEY, VOICES, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>"))))
    assert broken.list_voices("hi-IN") is None


# ------------------------------------------------------------------------------------------------ cache and /audio
def test_advice_audio_is_synthesised_once_cached_and_served(api_client, api_settings):
    server = FakeGoogle()
    store = FileAudioStore(api_settings.storage_dir, google(server), VOICES)
    url, sha = store.get_or_create("Spray in the evening.", "en")
    again = store.get_or_create("Spray in the evening.", "en")
    assert again == (url, sha) and len(server.requests) == 1                    # second call from the cache
    served = api_client.get(url)
    assert served.status_code == 200 and served.content == b"ID3Spray in the evening." and served.headers["content-type"] == "audio/mpeg"
    assert "immutable" in served.headers["cache-control"]


def test_a_changed_voice_gets_new_audio_not_the_old_file(api_settings):
    server = FakeGoogle()
    old = FileAudioStore(api_settings.storage_dir, google(server), VOICES)
    new = FileAudioStore(api_settings.storage_dir, google(server), {**VOICES, "en": "en-IN-Wavenet-A"})
    assert old.get_or_create("Hello.", "en")[0] != new.get_or_create("Hello.", "en")[0]


# ------------------------------------------------------------------------------------------------ the package the app downloads
def test_generated_prompts_appear_in_the_catalogue_and_are_downloadable(api_client, prompts_dir):
    before = api_client.get("/v1/voice/catalogue?lang=hi").json()
    assert before["version"].startswith("1+") and all(p["audio"] is None for p in before["prompts"])
    generate_prompt_audio(prompts_dir, FakeTTS(), VOICES)
    after = api_client.get("/v1/voice/catalogue?lang=hi").json()
    assert after["version"] != before["version"]                                # the app notices there is something new
    ref = {p["id"]: p["audio"] for p in after["prompts"]}["welcome"]
    assert ref["url"] == "/audio-prompts/hi/welcome.mp3"
    download = api_client.get(ref["url"])
    assert download.status_code == 200 and download.content.startswith(b"MP3:hi:")
    import hashlib

    assert hashlib.sha256(download.content).hexdigest() == ref["sha256"]


def test_the_package_zip_has_a_manifest_and_every_file(api_client, prompts_dir):
    generate_prompt_audio(prompts_dir, FakeTTS(), VOICES)
    response = api_client.get("/v1/voice/package?lang=en")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == ["ask_phone.mp3", "manifest.json", "welcome.mp3"]
        manifest = json.loads(archive.read("manifest.json"))
        assert archive.read("welcome.mp3") == b"MP3:en:Welcome."
    catalogue = api_client.get("/v1/voice/catalogue?lang=en").json()
    assert manifest["version"] == catalogue["version"] and manifest["language"] == "en"
    assert {p["id"]: p["sha256"] for p in manifest["prompts"]} == {p["id"]: p["audio"]["sha256"] for p in catalogue["prompts"]}


def test_the_package_is_a_304_when_the_app_is_current_and_404_when_empty(api_client, prompts_dir):
    empty = api_client.get("/v1/voice/package?lang=hi")
    assert empty.status_code == 404 and empty.json()["code"] == "voice_package_empty"
    generate_prompt_audio(prompts_dir, FakeTTS(), VOICES)
    first = api_client.get("/v1/voice/package?lang=hi")
    again = api_client.get("/v1/voice/package?lang=hi", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and not again.content
    assert api_client.get("/v1/voice/package?lang=fr").status_code == 422


def test_a_half_generated_package_lists_only_what_exists(api_client, prompts_dir):
    generate_prompt_audio(prompts_dir, FakeTTS(fail={"Type your number."}), VOICES, langs=("en",))
    status = {row.lang: row for row in package_status(get_settings())}
    assert (status["en"].prompts, status["en"].with_audio, status["en"].missing) == (2, 1, ["ask_phone"])
    assert (status["hi"].with_audio, status["hi"].missing) == (0, ["welcome", "ask_phone"])
    path = build_package(get_settings(), "en")
    assert path is not None
    with zipfile.ZipFile(path) as archive:
        assert sorted(archive.namelist()) == ["manifest.json", "welcome.mp3"]
    path.unlink()
    assert build_package(get_settings(), "hi") is None


def test_a_regenerated_file_changes_the_version_even_within_one_clock_tick(api_client, prompts_dir):
    """The bug behind the old failing catalogue test: same-size audio rewritten at once must not keep the old hash."""
    generate_prompt_audio(prompts_dir, FakeTTS(), VOICES)
    v1 = api_client.get("/v1/voice/catalogue?lang=en").json()["version"]
    (prompts_dir / "audio" / "en" / "welcome.mp3").write_bytes(b"MP3:en:Welcomf.")        # same length, new content
    assert api_client.get("/v1/voice/catalogue?lang=en").json()["version"] != v1


# ------------------------------------------------------------------------------------------------ the command line
def test_script_status_needs_no_key_and_makes_no_request(prompts_dir, monkeypatch, capsys):
    module = load_script()
    monkeypatch.setattr(module, "get_settings", lambda: make_settings(voice_dir=prompts_dir))
    monkeypatch.setattr(sys, "argv", ["generate_prompt_audio.py", "--status"])
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "key configured: no" in out and "hi: 0/2 prompts have audio" in out and "welcome" in out


def test_script_generates_then_reports_a_complete_package(prompts_dir, monkeypatch, capsys):
    module = load_script()
    monkeypatch.setattr(module, "get_settings", lambda: make_settings(voice_dir=prompts_dir, google_tts_api_key=KEY, tts_provider="google"))
    monkeypatch.setattr(module, "GoogleCloudTTS", lambda key, voices: google(FakeGoogle()))
    monkeypatch.setattr(sys, "argv", ["generate_prompt_audio.py"])
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "generated 4, skipped 0, failed 0" in out and "hi: 2/2 prompts have audio" in out and "en: 2/2" in out and KEY not in out


def test_script_list_voices_says_whether_the_chosen_voice_exists(prompts_dir, monkeypatch, capsys):
    module = load_script()
    settings = make_settings(voice_dir=prompts_dir, google_tts_api_key=KEY, tts_voice_hi="hi-IN-Chirp3-HD-Zephyr")
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(module, "GoogleCloudTTS", lambda key, voices: google(FakeGoogle()))
    monkeypatch.setattr(sys, "argv", ["generate_prompt_audio.py", "--list-voices"])
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "hi-IN-Chirp3-HD-Zephyr is NOT in the list" in out and "en-IN-Neural2-A is AVAILABLE" in out and KEY not in out


def test_script_list_voices_without_a_key_explains(prompts_dir, monkeypatch, capsys):
    module = load_script()
    monkeypatch.setattr(module, "get_settings", lambda: make_settings(voice_dir=prompts_dir))
    monkeypatch.setattr(sys, "argv", ["generate_prompt_audio.py", "--list-voices"])
    assert module.main() == 0 and "not configured" in capsys.readouterr().out
