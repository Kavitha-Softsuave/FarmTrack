"""Copy the fixed voice prompts and any generated audio into the Flutter assets.

    python tool/sync_voice_assets.py            (run from anywhere)

What it does:
  1. voice/prompts.json             -> mobile/assets/voice/prompts.json
  2. voice/audio/<lang>/<id>.mp3    -> mobile/assets/voice/<lang>/<id>.mp3  (stale mp3 files are removed)
  3. rewrites the asset block between the `voice-assets:begin/end` markers in pubspec.yaml so that every
     language listed in prompts.json has a declared asset folder (adding a language needs no manual edit).

The app plays a bundled mp3 first and falls back to server audio and then on-device speech, so it is fine
to run this before any audio exists: the folders are created empty (with a .gitkeep).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

MOBILE = Path(__file__).resolve().parent.parent
REPO = MOBILE.parent
SRC_PROMPTS = REPO / "voice" / "prompts.json"
SRC_AUDIO = REPO / "voice" / "audio"
DST = MOBILE / "assets" / "voice"
PUBSPEC = MOBILE / "pubspec.yaml"
BEGIN = "# voice-assets:begin"
END = "# voice-assets:end"


def main() -> int:
    if not SRC_PROMPTS.is_file():
        print(f"missing {SRC_PROMPTS}", file=sys.stderr)
        return 1
    data = json.loads(SRC_PROMPTS.read_text(encoding="utf-8"))
    languages = sorted(set(data.get("languages", [])) | _audio_languages())

    DST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC_PROMPTS, DST / "prompts.json")

    copied = 0
    for lang in languages:
        out = DST / lang
        out.mkdir(parents=True, exist_ok=True)
        (out / ".gitkeep").touch()
        source = SRC_AUDIO / lang
        wanted = {p.name for p in source.glob("*.mp3")} if source.is_dir() else set()
        for stale in out.glob("*.mp3"):
            if stale.name not in wanted:
                stale.unlink()
        for name in wanted:
            shutil.copyfile(source / name, out / name)
            copied += 1

    _update_pubspec(languages)
    print(f"prompts: {len(data['prompts'])}, languages: {', '.join(languages)}, audio files copied: {copied}")
    return 0


def _audio_languages() -> set[str]:
    if not SRC_AUDIO.is_dir():
        return set()
    return {p.name for p in SRC_AUDIO.iterdir() if p.is_dir()}


def _update_pubspec(languages: list[str]) -> None:
    text = PUBSPEC.read_text(encoding="utf-8")
    pattern = re.compile(rf"(?P<indent>[ ]*){re.escape(BEGIN)}[^\n]*\n.*?{re.escape(END)}", re.S)
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"pubspec.yaml has no '{BEGIN}' / '{END}' markers")
    indent = match.group("indent")
    lines = [f"{indent}{BEGIN} (managed by tool/sync_voice_assets.py)"]
    lines += [f"{indent}- assets/voice/{lang}/" for lang in languages]
    lines.append(f"{indent}{END}")
    PUBSPEC.write_text(text[: match.start()] + "\n".join(lines) + text[match.end():], encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
