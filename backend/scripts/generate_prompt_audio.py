"""Generate the audio for the fixed voice prompts and the native-speaker review sheet.

  python scripts/generate_prompt_audio.py                 # every prompt, both languages (skips files that are up to date)
  python scripts/generate_prompt_audio.py --force         # regenerate everything
  python scripts/generate_prompt_audio.py --lang hi --only welcome,ask_phone --voice-hi hi-IN-Neural2-B

Needs GOOGLE_TTS_API_KEY (in the shared .env or the environment). Without it the script explains what to do and exits 0.
Writes voice/audio/<lang>/<id>.mp3, voice/audio/manifest.json and voice/review_sheet.csv (give the sheet to the native speaker).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.voice.prompt_audio import LANGS, generate_prompt_audio  # noqa: E402
from app.voice.tts import GoogleCloudTTS  # noqa: E402

NO_KEY_HELP = """Google Cloud Text-to-Speech is not configured, so no audio was generated.

To generate the prompt audio:
  1. Enable the Text-to-Speech API in a Google Cloud project and create an API key.
  2. Put it in FarmTrack/.env as GOOGLE_TTS_API_KEY=... (optionally TTS_VOICE_HI / TTS_VOICE_EN).
  3. Run this script again.
The review sheet (voice/review_sheet.csv) was still written so the native speaker can check the texts now."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="regenerate files that already exist")
    parser.add_argument("--lang", choices=LANGS, action="append", help="only this language (repeatable)")
    parser.add_argument("--only", help="comma-separated prompt ids")
    parser.add_argument("--speed", type=float, default=0.9)
    parser.add_argument("--voice-hi")
    parser.add_argument("--voice-en")
    args = parser.parse_args()

    settings = get_settings()
    voices = {"hi": args.voice_hi or settings.tts_voice_hi, "en": args.voice_en or settings.tts_voice_en}
    langs = tuple(args.lang or LANGS)
    only = {i.strip() for i in args.only.split(",") if i.strip()} if args.only else None

    if not settings.google_tts_configured or not settings.google_tts_api_key:
        from app.voice.prompt_audio import load_prompts, write_review_sheet

        write_review_sheet(settings.voice_dir, load_prompts(settings.voice_dir), langs)
        print(NO_KEY_HELP)
        return 0

    tts = GoogleCloudTTS(settings.google_tts_api_key, voices)
    print(f"voices: hi={voices['hi']} en={voices['en']} speed={args.speed}")
    summary = generate_prompt_audio(settings.voice_dir, tts, voices, speed=args.speed, force=args.force, langs=langs,
                                    only_ids=only, log=print)
    print(f"generated {len(summary.generated)}, skipped {len(summary.skipped)}, failed {len(summary.failed)}")
    print(f"review sheet: {settings.voice_dir / 'review_sheet.csv'}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
