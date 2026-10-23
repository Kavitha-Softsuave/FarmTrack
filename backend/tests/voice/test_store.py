"""FileAudioStore (content-addressed cache), build_audio_store and spoken_out."""
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from app.api.schemas import SpokenOut
from app.interfaces import AudioStore
from app.voice import store as store_module
from app.voice.factory import build_audio_store
from app.voice.spoken import spoken_out
from app.voice.store import FileAudioStore
from app.voice.tts import GoogleCloudTTS, NullTTS
from tests.voice.helpers import make_settings

VOICES = {"hi": "hi-IN-Neural2-A", "en": "en-IN-Neural2-A"}


class FakeTTS:
    name = "fake"

    def __init__(self, audio=b"AUDIO-1"):
        self.audio = audio
        self.calls: list[tuple[str, str, float]] = []

    def synthesize(self, text, lang, speed=0.9):
        self.calls.append((text, lang, speed))
        return self.audio


def make_store(tmp_path, tts=None):
    return FileAudioStore(tmp_path / "storage", tts or FakeTTS(), VOICES)


def test_get_or_create_writes_a_content_addressed_file(tmp_path):
    tts = FakeTTS(b"AUDIO-1")
    store = make_store(tmp_path, tts)
    url, sha = store.get_or_create("namaste", "hi")
    key = hashlib.sha256(b"namaste|hi|hi-IN-Neural2-A|0.90").hexdigest()
    assert url == f"/audio/{key}.mp3"
    assert sha == hashlib.sha256(b"AUDIO-1").hexdigest()
    assert (tmp_path / "storage" / "audio" / f"{key}.mp3").read_bytes() == b"AUDIO-1"
    assert tts.calls == [("namaste", "hi", 0.9)]


def test_second_call_is_served_from_the_cache(tmp_path):
    tts = FakeTTS()
    store = make_store(tmp_path, tts)
    first = store.get_or_create("namaste", "hi")
    assert store.get_or_create("namaste", "hi") == first and len(tts.calls) == 1
    other_process = make_store(tmp_path, tts)                           # a fresh store sees the file on disk
    assert other_process.get_or_create("namaste", "hi") == first and len(tts.calls) == 1


def test_text_language_voice_and_speed_all_change_the_key(tmp_path):
    store = make_store(tmp_path)
    keys = {store.cache_key("a", "hi"), store.cache_key("b", "hi"), store.cache_key("a", "en"), store.cache_key("a", "hi", 0.8)}
    assert len(keys) == 4
    other_voice = FileAudioStore(tmp_path / "storage", FakeTTS(), {"hi": "hi-IN-Wavenet-B", "en": "x"})
    assert other_voice.cache_key("a", "hi") != store.cache_key("a", "hi")
    assert store.cache_key("  a  ", "hi") == store.cache_key("a", "hi")


def test_speed_is_passed_to_the_tts(tmp_path):
    tts = FakeTTS()
    make_store(tmp_path, tts).get_or_create("slow words", "en", 0.7)
    assert tts.calls == [("slow words", "en", 0.7)]


def test_no_audio_means_none_and_no_file(tmp_path):
    for tts in (FakeTTS(audio=None), NullTTS()):
        store = make_store(tmp_path, tts)
        assert store.get_or_create("namaste", "hi") is None
    assert not (tmp_path / "storage" / "audio").exists() or not any((tmp_path / "storage" / "audio").iterdir())


def test_blank_text_is_never_synthesised(tmp_path):
    tts = FakeTTS()
    store = make_store(tmp_path, tts)
    assert store.get_or_create("   ", "hi") is None and tts.calls == []


def test_get_cached_never_calls_the_tts(tmp_path):
    tts = FakeTTS()
    store = make_store(tmp_path, tts)
    assert store.get_cached("namaste", "hi") is None
    created = store.get_or_create("namaste", "hi")
    assert store.get_cached("namaste", "hi") == created and len(tts.calls) == 1


def test_write_is_atomic_no_partial_file_or_temp_file_when_it_fails(tmp_path, monkeypatch):
    store = make_store(tmp_path)

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(store_module.os, "replace", broken_replace)
    assert store.get_or_create("namaste", "hi") is None                  # fails soft
    assert list((tmp_path / "storage" / "audio").iterdir()) == []        # no .mp3 and no leftover .tmp
    monkeypatch.undo()
    assert store.get_or_create("namaste", "hi") is not None              # and it works again afterwards


def test_no_temp_files_remain_after_success(tmp_path):
    store = make_store(tmp_path)
    store.get_or_create("one", "hi")
    store.get_or_create("two", "en")
    assert sorted(p.suffix for p in (tmp_path / "storage" / "audio").iterdir()) == [".mp3", ".mp3"]


def test_concurrent_requests_for_the_same_text_leave_one_valid_file(tmp_path):
    store = make_store(tmp_path)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: store.get_or_create("namaste", "hi"), range(16)))
    assert len(set(results)) == 1
    files = list((tmp_path / "storage" / "audio").iterdir())
    assert len(files) == 1 and files[0].read_bytes() == b"AUDIO-1"


def test_concurrent_requests_synthesise_only_once(tmp_path):
    import time

    class SlowTTS(FakeTTS):
        def synthesize(self, text, lang, speed=0.9):
            time.sleep(0.05)
            return super().synthesize(text, lang, speed)

    tts = SlowTTS()
    store = make_store(tmp_path, tts)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: store.get_or_create("namaste", "hi"), range(16)))
    assert len(tts.calls) == 1


def test_store_has_the_audio_store_shape(tmp_path):
    store: AudioStore = make_store(tmp_path)
    assert store.get_or_create("namaste", "hi") is not None


# ---------------------------------------------------------------------------------------------- build_audio_store
def test_default_settings_give_a_silent_store(tmp_path):
    store = build_audio_store(make_settings(storage_dir=tmp_path / "s"))
    assert store.provider_name == "null" and store.get_or_create("namaste", "hi") is None


def test_google_settings_build_a_working_store(tmp_path):
    store = build_audio_store(make_settings(storage_dir=tmp_path / "s", tts_provider="google", google_tts_api_key="AIza-real-key-123456",
                                            tts_voice_hi="hi-IN-Chirp3-HD-Aoede", tts_voice_en="en-IN-Chirp3-HD-Charon"))
    assert store.provider_name == "google"
    assert isinstance(store._tts, GoogleCloudTTS) and store._tts.voice_for("hi") == "hi-IN-Chirp3-HD-Aoede"
    assert store.directory == tmp_path / "s" / "audio"


def test_google_without_a_key_is_silent_and_warns_once(tmp_path, caplog):
    from app.voice import factory
    factory._warned = False
    caplog.set_level(logging.WARNING)
    for _ in range(2):
        store = build_audio_store(make_settings(storage_dir=tmp_path / "s", tts_provider="google", google_tts_api_key=""))
        assert store.provider_name == "null"
    assert sum("GOOGLE_TTS_API_KEY is not set" in r.getMessage() for r in caplog.records) == 1


# ---------------------------------------------------------------------------------------------- spoken_out
class DictStore:
    def __init__(self, result):
        self.result, self.calls = result, []

    def get_or_create(self, text, lang, speed=0.9):
        self.calls.append((text, lang))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_spoken_out_without_a_store_has_text_and_empty_audio():
    out = spoken_out(None, "Hello", "नमस्ते")
    assert isinstance(out, SpokenOut) and out.text.en == "Hello" and out.text.hi == "नमस्ते"
    assert out.audio == {"hi": None, "en": None}


def test_spoken_out_adds_audio_references():
    store = DictStore(("/audio/abc.mp3", "f" * 64))
    out = spoken_out(store, "Hello", "नमस्ते")
    assert out.audio["hi"].url == "/audio/abc.mp3" and out.audio["en"].sha256 == "f" * 64
    assert store.calls == [("नमस्ते", "hi"), ("Hello", "en")]


def test_spoken_out_with_a_silent_or_failing_store_keeps_the_text():
    assert spoken_out(DictStore(None), "Hello", "नमस्ते").audio == {"hi": None, "en": None}
    out = spoken_out(DictStore(RuntimeError("cache broken")), "Hello", "नमस्ते")
    assert out.text.en == "Hello" and out.audio == {"hi": None, "en": None}


def test_spoken_out_skips_blank_languages():
    store = DictStore(("/audio/abc.mp3", "f" * 64))
    out = spoken_out(store, "Hello", "  ")
    assert out.audio["hi"] is None and out.audio["en"] is not None and store.calls == [("Hello", "en")]


def test_spoken_out_end_to_end_with_the_file_store(tmp_path):
    out = spoken_out(make_store(tmp_path), "Hello", "नमस्ते")
    assert out.audio["hi"].url.startswith("/audio/") and out.audio["hi"].url.endswith(".mp3")
    assert os.path.exists(tmp_path / "storage" / "audio" / out.audio["hi"].url.rsplit("/", 1)[1])
    assert out.model_dump(mode="json")["audio"]["en"]["sha256"]
