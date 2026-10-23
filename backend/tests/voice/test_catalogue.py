import hashlib
import json

import pytest

from app.config import REPO_ROOT
from app.voice.catalogue import PROMPT_AUDIO_URL_PREFIX, load_catalogue
from tests.voice.helpers import make_settings

# the ids every agent relies on (voice/prompts.json, docs/design-notes/voice.md)
FIXED_IDS = """
welcome choose_language language_hindi language_english ask_phone ask_otp otp_sent otp_wrong login_ok home_intro home_scan home_field
home_diary home_ask scan_open_camera scan_hold_close scan_one_leaf scan_daylight scan_tap_capture scan_photo_taken scan_add_more
scan_send scan_uploading scan_wait scan_retake_blurry scan_retake_dark scan_retake_far scan_retake_no_leaf crop_confirm_prompt
crop_tap_yes crop_tap_no crop_choose_other result_intro result_expert result_no_data result_not_disease result_listen_again
result_next_diary diary_intro diary_tick_sprayed diary_saved diary_warning field_intro field_stale alert_new alert_open ask_intro
ask_type_question ask_no_answer error_no_internet error_try_again offline_saved back_online_sent settings_speed settings_volume
camera_permission notification_permission crop_is_apple crop_is_tomato crop_is_potato crop_is_maize crop_is_grape
""".split()


def write_prompts(voice_dir, prompts, version="2026-01-01.1"):
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "prompts.json").write_text(json.dumps({"version": version, "prompts": prompts}, ensure_ascii=False), encoding="utf-8")


def prompt(pid, en="Hello.", hi="नमस्ते।"):
    return {"id": pid, "screen": "x", "when": "y", "en": en, "hi": hi}


def catalogue(voice_dir, lang="hi", store=None):
    return load_catalogue(make_settings(voice_dir=voice_dir), lang, store)


def test_texts_come_from_the_file_per_language(tmp_path):
    write_prompts(tmp_path, [prompt("welcome", "Welcome.", "स्वागत है।"), prompt("ask_phone", "Phone?", "फ़ोन?")])
    hi, en = catalogue(tmp_path, "hi"), catalogue(tmp_path, "en")
    assert [(p.id, p.text) for p in hi.prompts] == [("welcome", "स्वागत है।"), ("ask_phone", "फ़ोन?")]
    assert [(p.id, p.text) for p in en.prompts] == [("welcome", "Welcome."), ("ask_phone", "Phone?")]
    assert hi.language == "hi" and en.language == "en" and hi.prompts[0].audio is None


def test_missing_or_broken_file_fails_soft(tmp_path):
    empty = catalogue(tmp_path / "nowhere")
    assert empty.version == "missing" and empty.prompts == [] and empty.language == "hi"
    (tmp_path / "prompts.json").write_text("{ broken", encoding="utf-8")
    assert catalogue(tmp_path).version == "missing"
    (tmp_path / "prompts.json").write_text(json.dumps({"version": "1"}), encoding="utf-8")
    assert catalogue(tmp_path).version == "missing"
    (tmp_path / "prompts.json").write_text(json.dumps({"version": "1", "prompts": "nope"}), encoding="utf-8")
    assert catalogue(tmp_path).prompts == []


def test_unusable_entries_are_skipped(tmp_path):
    write_prompts(tmp_path, [prompt("ok"), prompt("../escape"), prompt("Bad Id"), prompt("no_hindi", hi=""), {"id": "no_text"}, "junk", prompt("fine_two")])
    assert [p.id for p in catalogue(tmp_path).prompts] == ["ok", "fine_two"]
    assert [p.id for p in catalogue(tmp_path, "en").prompts] == ["ok", "no_hindi", "fine_two"]


def test_audio_is_referenced_when_the_file_exists(tmp_path):
    write_prompts(tmp_path, [prompt("welcome"), prompt("ask_phone")])
    (tmp_path / "audio" / "hi").mkdir(parents=True)
    (tmp_path / "audio" / "hi" / "welcome.mp3").write_bytes(b"MP3-HI")
    hi, en = catalogue(tmp_path, "hi"), catalogue(tmp_path, "en")
    assert hi.prompts[0].audio.url == f"{PROMPT_AUDIO_URL_PREFIX}/hi/welcome.mp3" == "/audio-prompts/hi/welcome.mp3"
    assert hi.prompts[0].audio.sha256 == hashlib.sha256(b"MP3-HI").hexdigest()
    assert hi.prompts[1].audio is None and en.prompts[0].audio is None


def test_version_changes_with_text_and_audio_and_is_stable_otherwise(tmp_path):
    write_prompts(tmp_path, [prompt("welcome")])
    v1 = catalogue(tmp_path).version
    assert catalogue(tmp_path).version == v1 and v1.startswith("2026-01-01.1+")
    write_prompts(tmp_path, [prompt("welcome", hi="नया पाठ।")])
    v2 = catalogue(tmp_path).version
    assert v2 != v1
    (tmp_path / "audio" / "hi").mkdir(parents=True)
    (tmp_path / "audio" / "hi" / "welcome.mp3").write_bytes(b"A")
    v3 = catalogue(tmp_path).version
    (tmp_path / "audio" / "hi" / "welcome.mp3").write_bytes(b"B")
    v4 = catalogue(tmp_path).version
    assert len({v2, v3, v4}) == 3
    assert catalogue(tmp_path, "en").version != v4                       # per language


def test_audio_store_cache_is_used_without_synthesis(tmp_path):
    write_prompts(tmp_path, [prompt("welcome")])

    class Store:
        def __init__(self):
            self.created = 0

        def get_cached(self, text, lang, speed=0.9):
            return ("/audio/cached.mp3", "a" * 64) if text == "नमस्ते।" else None

        def get_or_create(self, text, lang, speed=0.9):
            self.created += 1

    store = Store()
    assert catalogue(tmp_path, "hi", store).prompts[0].audio.url == "/audio/cached.mp3"
    assert catalogue(tmp_path, "en", store).prompts[0].audio is None and store.created == 0


def test_the_real_prompt_file_loads_and_has_every_fixed_id():
    settings = make_settings(voice_dir=REPO_ROOT / "voice")
    hi, en = load_catalogue(settings, "hi"), load_catalogue(settings, "en")
    assert hi.version != "missing" and hi.version != en.version
    for cat in (hi, en):
        ids = {p.id for p in cat.prompts}
        assert not (set(FIXED_IDS) - ids), sorted(set(FIXED_IDS) - ids)
        assert all(p.text.strip() for p in cat.prompts)
    assert [p.id for p in hi.prompts] == [p.id for p in en.prompts]


@pytest.mark.parametrize("lang", ["hi", "en"])
def test_catalogue_serialises_to_the_api_shape(tmp_path, lang):
    write_prompts(tmp_path, [prompt("welcome")])
    data = catalogue(tmp_path, lang).model_dump(mode="json")
    assert set(data) == {"version", "language", "prompts"} and set(data["prompts"][0]) == {"id", "text", "audio"}
