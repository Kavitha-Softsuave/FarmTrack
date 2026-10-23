"""NullTTS and GoogleCloudTTS (request construction and error handling, httpx.MockTransport, no network)."""
import base64
import json
import logging

import httpx
import pytest

from app.voice.tts import GOOGLE_TTS_URL, GoogleCloudTTS, NullTTS

KEY = "AIza-test-key-0123456789"
VOICES = {"hi": "hi-IN-Neural2-A", "en": "en-IN-Neural2-A"}
MP3 = b"ID3\x03\x00fake-mp3-bytes"
TEXT = "SECRET spoken text about the farm"


class Server:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    def body(self, i=0):
        return json.loads(self.requests[i].content)


def ok(audio=MP3):
    return httpx.Response(200, json={"audioContent": base64.b64encode(audio).decode()})


def tts_with(server, voices=None, sleeps=None, **kw):
    client = httpx.Client(transport=httpx.MockTransport(server))
    return GoogleCloudTTS(KEY, voices or VOICES, client=client, sleep=(sleeps.append if sleeps is not None else (lambda _s: None)), **kw)


def test_null_tts_returns_nothing():
    assert NullTTS().synthesize("text", "hi") is None and NullTTS().name == "null"


def test_request_construction_for_a_standard_voice():
    server = Server(ok())
    assert tts_with(server).synthesize(TEXT, "hi", 0.9) == MP3
    request = server.requests[0]
    assert request.method == "POST" and str(request.url) == GOOGLE_TTS_URL == "https://texttospeech.googleapis.com/v1/text:synthesize"
    assert request.headers["x-goog-api-key"] == KEY and KEY not in str(request.url)
    assert server.body() == {"input": {"text": TEXT}, "voice": {"languageCode": "hi-IN", "name": "hi-IN-Neural2-A"},
                             "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.9}}


def test_english_voice_uses_its_own_language_code():
    server = Server(ok())
    tts_with(server, {"hi": "hi-IN-Neural2-A", "en": "en-GB-Wavenet-B"}).synthesize(TEXT, "en", 1.0)
    assert server.body()["voice"] == {"languageCode": "en-GB", "name": "en-GB-Wavenet-B"}


@pytest.mark.parametrize("voice", ["hi-IN-Chirp3-HD-Aoede", "en-IN-Chirp3-HD-Charon"])
def test_chirp3_hd_voices_get_no_speaking_rate(voice):
    server = Server(ok())
    lang = "hi" if voice.startswith("hi") else "en"
    tts_with(server, {lang: voice}).synthesize(TEXT, lang, 0.8)
    audio_config = server.body()["audioConfig"]
    assert audio_config == {"audioEncoding": "MP3"}
    assert server.body()["voice"]["languageCode"] == voice[:5] and "ssml" not in json.dumps(server.body()).lower()


@pytest.mark.parametrize("speed,sent", [(0.1, 0.25), (0.9, 0.9), (3.5, 2.0)])
def test_speaking_rate_is_clamped(speed, sent):
    server = Server(ok())
    tts_with(server).synthesize(TEXT, "en", speed)
    assert server.body()["audioConfig"]["speakingRate"] == sent


def test_voice_name_without_a_language_prefix_falls_back_to_the_default_code():
    server = Server(ok())
    tts_with(server, {"hi": "custom"}).synthesize(TEXT, "hi")
    assert server.body()["voice"]["languageCode"] == "hi-IN"


def test_nothing_is_sent_for_empty_text_missing_voice_or_oversized_text():
    server = Server(ok())
    tts = tts_with(server, {"hi": "hi-IN-Neural2-A"})
    assert tts.synthesize("   ", "hi") is None
    assert tts.synthesize(TEXT, "en") is None                              # no English voice configured
    assert tts.synthesize("अ" * 2000, "hi") is None                        # 6000 bytes: over the API limit
    assert server.requests == []


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_return_none_without_retry(status):
    server = Server(httpx.Response(status, json={"error": {"status": "PERMISSION_DENIED", "message": f"key {KEY} text {TEXT}"}}))
    assert tts_with(server).synthesize(TEXT, "hi") is None
    assert len(server.requests) == 1


def test_server_errors_are_retried_then_none():
    server = Server(httpx.Response(503, json={}))
    sleeps: list[float] = []
    assert tts_with(server, sleeps=sleeps, max_retries=2).synthesize(TEXT, "hi") is None
    assert len(server.requests) == 3 and sleeps == [1, 2]
    server = Server(httpx.Response(429, json={}), ok())
    assert tts_with(server).synthesize(TEXT, "hi") == MP3


def test_network_errors_are_retried_then_none():
    server = Server(httpx.ConnectError("down"))
    assert tts_with(server, max_retries=1).synthesize(TEXT, "hi") is None
    assert len(server.requests) == 2
    server = Server(httpx.ReadTimeout("slow"), ok())
    assert tts_with(server).synthesize(TEXT, "hi") == MP3


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={}), httpx.Response(200, json={"audioContent": ""}), httpx.Response(200, json={"audioContent": "!!not base64!!"}),
    httpx.Response(200, text="<html>"), httpx.Response(200, json=[1, 2]),
])
def test_bad_success_bodies_return_none(response):
    assert tts_with(Server(response)).synthesize(TEXT, "hi") is None


def test_text_and_key_never_reach_the_logs(caplog):
    caplog.set_level(logging.DEBUG)
    tts = tts_with(Server(httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": f"bad {KEY} for {TEXT}"}})))
    tts.synthesize(TEXT, "hi")
    tts_with(Server(httpx.ConnectError(f"cannot reach {TEXT}"))).synthesize(TEXT, "hi")
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert logged and KEY not in logged and "SECRET" not in logged
    assert KEY not in repr(tts)
