import hashlib

import pytest

NAME = "a" * 64 + ".mp3"
BYTES = b"ID3fake-mp3-bytes"


@pytest.fixture
def audio_dirs(api_settings):
    tts = api_settings.storage_dir / "audio"
    tts.mkdir(parents=True)
    name = hashlib.sha256(b"x").hexdigest() + ".mp3"
    (tts / name).write_bytes(BYTES)
    prompts = api_settings.voice_dir / "audio" / "hi"
    prompts.mkdir(parents=True)
    (prompts / "crop_is_apple.mp3").write_bytes(b"prompt-audio")
    return name


# ------------------------------------------------------------------------------------------------ catalogue
def test_catalogue_is_public_and_lists_the_prompts_in_the_requested_language(api_client):
    body = api_client.get("/v1/voice/catalogue?lang=en").json()
    assert body["language"] == "en" and body["version"].startswith("test+")
    prompts = {p["id"]: p for p in body["prompts"]}
    assert prompts["crop_is_apple"]["text"] == "This looks like apple." and prompts["crop_is_apple"]["audio"] is None
    hindi = api_client.get("/v1/voice/catalogue").json()                         # default language: Hindi
    assert hindi["language"] == "hi" and {p["id"]: p for p in hindi["prompts"]}["crop_is_apple"]["text"] == "यह सेब की फसल लगती है।"


def test_catalogue_points_at_generated_prompt_audio(api_client, audio_dirs):
    prompt = {p["id"]: p for p in api_client.get("/v1/voice/catalogue?lang=hi").json()["prompts"]}["crop_is_apple"]
    assert prompt["audio"]["url"] == "/audio-prompts/hi/crop_is_apple.mp3"
    assert prompt["audio"]["sha256"] == hashlib.sha256(b"prompt-audio").hexdigest()
    served = api_client.get(prompt["audio"]["url"])
    assert served.status_code == 200 and served.content == b"prompt-audio" and served.headers["content-type"] == "audio/mpeg"


def test_catalogue_version_is_an_etag(api_client):
    first = api_client.get("/v1/voice/catalogue?lang=en")
    etag = first.headers["etag"]
    assert first.headers["cache-control"] == "no-cache"
    again = api_client.get("/v1/voice/catalogue?lang=en", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    assert api_client.get("/v1/voice/catalogue?lang=hi", headers={"If-None-Match": etag}).status_code == 200      # per language


def test_catalogue_rejects_an_unknown_language(api_client):
    assert api_client.get("/v1/voice/catalogue?lang=fr").status_code == 422


def test_missing_prompts_file_gives_an_empty_catalogue_not_an_error(api_client, api_settings):
    (api_settings.voice_dir / "prompts.json").unlink()
    body = api_client.get("/v1/voice/catalogue").json()
    assert body["prompts"] == [] and body["version"] == "missing"


# ------------------------------------------------------------------------------------------------ /audio/{name}
def test_audio_is_served_immutable_and_public(api_client, audio_dirs):
    response = api_client.get(f"/audio/{audio_dirs}")
    assert response.status_code == 200 and response.content == BYTES
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["etag"] == f'"{audio_dirs.removesuffix(".mp3")}"'
    assert response.headers["x-content-type-options"] == "nosniff"


def test_audio_supports_range_requests(api_client, audio_dirs):
    response = api_client.get(f"/audio/{audio_dirs}", headers={"Range": "bytes=0-2"})
    assert response.status_code == 206 and response.content == BYTES[:3]


def test_unknown_audio_is_404(api_client, audio_dirs):
    response = api_client.get(f"/audio/{NAME}")
    assert response.status_code == 404 and response.json()["code"] == "audio_not_found"


@pytest.mark.parametrize("name", [
    "..", "../secret.mp3", "..%2f..%2fetc%2fpasswd", "%2e%2e%2fsecret.mp3", "..\\secret.mp3", "a" * 64, "a" * 64 + ".wav",
    "A" * 64 + ".mp3", "a" * 63 + ".mp3", "a" * 65 + ".mp3", "a" * 64 + ".mp3 ", "a" * 64 + ".mp3/../x", "c%3A%5Cwindows%5Cwin.ini",
    "a" * 64 + ".MP3", "%00" + "a" * 60 + ".mp3", "g" * 64 + ".mp3",
])
def test_audio_names_are_strictly_validated(api_client, audio_dirs, name):
    response = api_client.get(f"/audio/{name}")
    assert response.status_code in (404, 422) and "audio/mpeg" not in response.headers.get("content-type", "")
    assert response.json()["code"] in ("audio_not_found", "not_found", "validation_error")


def test_a_symlink_or_file_outside_the_audio_directory_is_never_served(api_client, api_settings, audio_dirs):
    secret = api_settings.storage_dir / "secret.txt"
    secret.write_text("top secret")
    link = api_settings.storage_dir / "audio" / ("b" * 64 + ".mp3")
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks not permitted on this machine")
    assert api_client.get(f"/audio/{link.name}").status_code == 404


def test_synthesised_audio_is_not_served_from_the_prompt_route_and_vice_versa(api_client, audio_dirs):
    assert api_client.get(f"/audio-prompts/hi/{audio_dirs}").status_code == 404
    assert api_client.get("/audio/crop_is_apple.mp3").status_code == 404


@pytest.mark.parametrize("path", ["/audio-prompts/hi/..%2f..%2fprompts.json", "/audio-prompts/fr/crop_is_apple.mp3",
                                  "/audio-prompts/hi/crop_is_apple.wav", "/audio-prompts/hi/Crop-Is-Apple.mp3",
                                  "/audio-prompts/hi/../en/x.mp3", "/audio-prompts/hi/%2e%2e%2f%2e%2e%2fsecret.mp3"])
def test_prompt_audio_names_are_strictly_validated(api_client, audio_dirs, path):
    assert api_client.get(path).status_code in (404, 422)


def test_prompt_audio_cache_policy(api_client, audio_dirs):
    response = api_client.get("/audio-prompts/hi/crop_is_apple.mp3")
    assert response.headers["cache-control"] == "public, max-age=86400" and response.headers["etag"]


def test_audio_routes_need_no_login(api_client, audio_dirs):
    assert api_client.get(f"/audio/{audio_dirs}").status_code == 200
    assert api_client.get("/audio-prompts/hi/crop_is_apple.mp3").status_code == 200
