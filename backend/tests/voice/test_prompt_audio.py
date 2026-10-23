"""scripts/generate_prompt_audio.py and app.voice.prompt_audio: idempotent generation and the native-speaker review sheet."""
import csv
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from app.config import BACKEND_ROOT
from app.voice.prompt_audio import REVIEW_COLUMNS, generate_prompt_audio
from tests.voice.helpers import make_settings

VOICES = {"hi": "hi-IN-Neural2-A", "en": "en-IN-Neural2-A"}
SCRIPT = BACKEND_ROOT / "scripts" / "generate_prompt_audio.py"


class FakeTTS:
    name = "fake"

    def __init__(self, fail=()):
        self.calls: list[tuple[str, str]] = []
        self.fail = set(fail)

    def synthesize(self, text, lang, speed=0.9):
        self.calls.append((text, lang))
        return None if text in self.fail else f"MP3:{lang}:{text}".encode()


def write_prompts(voice_dir: Path, prompts):
    voice_dir.mkdir(parents=True, exist_ok=True)
    (voice_dir / "prompts.json").write_text(json.dumps({"version": "1", "prompts": prompts}, ensure_ascii=False), encoding="utf-8")


def two_prompts():
    return [{"id": "welcome", "en": "Welcome.", "hi": "स्वागत है।"}, {"id": "ask_phone", "en": "Type your phone number.", "hi": "फ़ोन नंबर लिखिए।"}]


def read_sheet(voice_dir: Path):
    with open(voice_dir / "review_sheet.csv", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def run(voice_dir, tts, **kw):
    return generate_prompt_audio(voice_dir, tts, VOICES, **kw)


def test_files_manifest_and_review_sheet_are_written(tmp_path):
    write_prompts(tmp_path, two_prompts())
    tts = FakeTTS()
    summary = run(tmp_path, tts)
    assert sorted(summary.generated) == ["en/ask_phone", "en/welcome", "hi/ask_phone", "hi/welcome"] and not summary.failed and not summary.skipped
    assert (tmp_path / "audio" / "hi" / "welcome.mp3").read_bytes() == "MP3:hi:स्वागत है।".encode()
    assert set(json.loads((tmp_path / "audio" / "manifest.json").read_text(encoding="utf-8"))) == set(summary.generated)
    rows = read_sheet(tmp_path)
    assert list(rows[0]) == REVIEW_COLUMNS == ["id", "lang", "text", "audio_file", "native_speaker_ok", "corrected_text", "notes"]
    assert len(rows) == 4
    first = rows[0]
    assert (first["id"], first["lang"], first["text"], first["audio_file"]) == ("welcome", "hi", "स्वागत है।", "audio/hi/welcome.mp3")
    assert first["native_speaker_ok"] == first["corrected_text"] == first["notes"] == ""


def test_second_run_changes_nothing_and_does_not_call_the_tts(tmp_path):
    write_prompts(tmp_path, two_prompts())
    run(tmp_path, FakeTTS())
    before = {p: p.read_bytes() for p in (tmp_path / "audio").rglob("*") if p.is_file()}
    sheet_before = (tmp_path / "review_sheet.csv").read_bytes()
    tts = FakeTTS()
    summary = run(tmp_path, tts)
    assert tts.calls == [] and summary.generated == [] and len(summary.skipped) == 4
    assert {p: p.read_bytes() for p in (tmp_path / "audio").rglob("*") if p.is_file()} == before
    assert (tmp_path / "review_sheet.csv").read_bytes() == sheet_before


def test_force_regenerates_everything(tmp_path):
    write_prompts(tmp_path, two_prompts())
    run(tmp_path, FakeTTS())
    tts = FakeTTS()
    assert len(run(tmp_path, tts, force=True).generated) == 4 and len(tts.calls) == 4


def test_changed_text_voice_or_speed_regenerates_only_that_file(tmp_path):
    write_prompts(tmp_path, two_prompts())
    run(tmp_path, FakeTTS())
    prompts = two_prompts()
    prompts[0]["hi"] = "नया स्वागत।"
    write_prompts(tmp_path, prompts)
    summary = run(tmp_path, FakeTTS())
    assert summary.generated == ["hi/welcome"] and len(summary.skipped) == 3
    assert (tmp_path / "audio" / "hi" / "welcome.mp3").read_bytes() == "MP3:hi:नया स्वागत।".encode()
    assert len(run(tmp_path, FakeTTS(), speed=0.8).generated) == 4                 # a slower voice means new audio
    other_voice = generate_prompt_audio(tmp_path, FakeTTS(), {"hi": "hi-IN-Wavenet-B", "en": VOICES["en"]}, speed=0.8)
    assert sorted(other_voice.generated) == ["hi/ask_phone", "hi/welcome"]


def test_a_hand_made_recording_is_never_overwritten_unless_forced(tmp_path):
    write_prompts(tmp_path, two_prompts())
    (tmp_path / "audio" / "hi").mkdir(parents=True)
    (tmp_path / "audio" / "hi" / "welcome.mp3").write_bytes(b"HUMAN-RECORDING")
    summary = run(tmp_path, FakeTTS())
    assert "hi/welcome" in summary.skipped and (tmp_path / "audio" / "hi" / "welcome.mp3").read_bytes() == b"HUMAN-RECORDING"
    run(tmp_path, FakeTTS(), force=True)
    assert (tmp_path / "audio" / "hi" / "welcome.mp3").read_bytes() != b"HUMAN-RECORDING"


def test_a_failed_synthesis_is_reported_and_leaves_no_file(tmp_path):
    write_prompts(tmp_path, two_prompts())
    summary = run(tmp_path, FakeTTS(fail={"फ़ोन नंबर लिखिए।"}))
    assert summary.failed == ["hi/ask_phone"] and not (tmp_path / "audio" / "hi" / "ask_phone.mp3").exists()
    assert read_sheet(tmp_path)[2]["audio_file"] == ""                            # the sheet shows which audio is missing
    again = run(tmp_path, FakeTTS())
    assert again.generated == ["hi/ask_phone"]                                    # and a rerun fills the gap


def test_language_and_id_filters(tmp_path):
    write_prompts(tmp_path, two_prompts())
    tts = FakeTTS()
    summary = run(tmp_path, tts, langs=("en",), only_ids={"welcome"})
    assert summary.generated == ["en/welcome"] and tts.calls == [("Welcome.", "en")]


def test_review_sheet_keeps_what_the_reviewer_wrote(tmp_path):
    write_prompts(tmp_path, two_prompts())
    run(tmp_path, FakeTTS())
    rows = read_sheet(tmp_path)
    rows[0].update(native_speaker_ok="yes", notes="good")
    rows[1].update(native_speaker_ok="no", corrected_text="सही पाठ", notes="too fast")
    with open(tmp_path / "review_sheet.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    run(tmp_path, FakeTTS())
    again = read_sheet(tmp_path)
    assert (again[0]["native_speaker_ok"], again[0]["notes"]) == ("yes", "good")
    assert (again[1]["native_speaker_ok"], again[1]["corrected_text"], again[1]["notes"]) == ("no", "सही पाठ", "too fast")


def test_review_sheet_flags_text_changed_after_review(tmp_path):
    write_prompts(tmp_path, two_prompts())
    run(tmp_path, FakeTTS())
    rows = read_sheet(tmp_path)
    rows[0].update(native_speaker_ok="yes", notes="good")
    with open(tmp_path / "review_sheet.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    prompts = two_prompts()
    prompts[0]["hi"] = "बदला हुआ।"
    write_prompts(tmp_path, prompts)
    run(tmp_path, FakeTTS())
    changed = read_sheet(tmp_path)[0]
    assert changed["native_speaker_ok"] == "" and changed["notes"].startswith("TEXT CHANGED after review") and "good" in changed["notes"]


def test_the_real_prompts_produce_a_complete_review_sheet(tmp_path):
    real = json.loads((BACKEND_ROOT.parent / "voice" / "prompts.json").read_text(encoding="utf-8"))["prompts"]
    write_prompts(tmp_path, real)
    run(tmp_path, FakeTTS())
    rows = read_sheet(tmp_path)
    assert len(rows) == 2 * len(real) and all(r["text"] for r in rows)
    assert {(r["id"], r["lang"]) for r in rows} == {(p["id"], lang) for p in real for lang in ("hi", "en")}


# ---------------------------------------------------------------------------------------------- the command line
def test_script_without_a_key_explains_and_exits_zero(tmp_path):
    write_prompts(tmp_path, two_prompts())
    env = {**os.environ, "GOOGLE_TTS_API_KEY": "", "VOICE_DIR": str(tmp_path)}
    done = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, encoding="utf-8", cwd=BACKEND_ROOT, timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    assert "not configured" in done.stdout and "GOOGLE_TTS_API_KEY" in done.stdout
    assert len(read_sheet(tmp_path)) == 4 and not (tmp_path / "audio").exists()


def load_script():
    spec = importlib.util.spec_from_file_location("generate_prompt_audio_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_with_a_key_generates_and_reports(tmp_path, monkeypatch, capsys):
    write_prompts(tmp_path, two_prompts())
    module = load_script()
    seen = {}

    class Fake(FakeTTS):
        def __init__(self, api_key, voices):
            super().__init__()
            seen.update(key=api_key, voices=voices)

    monkeypatch.setattr(module, "get_settings", lambda: make_settings(voice_dir=tmp_path, google_tts_api_key="AIza-real-key-123456"))
    monkeypatch.setattr(module, "GoogleCloudTTS", Fake)
    monkeypatch.setattr(sys, "argv", ["generate_prompt_audio.py", "--lang", "hi", "--voice-hi", "hi-IN-Wavenet-B"])
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "generated 2, skipped 0, failed 0" in out and "AIza" not in out
    assert seen["voices"]["hi"] == "hi-IN-Wavenet-B" and (tmp_path / "audio" / "hi" / "welcome.mp3").exists()
    assert not (tmp_path / "audio" / "en").exists()
    monkeypatch.setattr(sys, "argv", ["generate_prompt_audio.py", "--lang", "hi", "--voice-hi", "hi-IN-Wavenet-B"])
    assert module.main() == 0 and "generated 0, skipped 2" in capsys.readouterr().out
