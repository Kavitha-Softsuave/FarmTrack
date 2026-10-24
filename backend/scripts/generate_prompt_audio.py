"""Generate the audio for the fixed voice prompts and the native-speaker review sheet.

  python scripts/generate_prompt_audio.py                 # every prompt, both languages (skips files that are up to date)
  python scripts/generate_prompt_audio.py --force         # regenerate everything
  python scripts/generate_prompt_audio.py --lang hi --only welcome,ask_phone --voice-hi hi-IN-Neural2-B
  python scripts/generate_prompt_audio.py --status        # how complete is the voice package (no key needed, no request made)
  python scripts/generate_prompt_audio.py --list-voices   # ask Google which hi-IN / en-IN voices exist (needs the key)

Needs GOOGLE_TTS_API_KEY (in the shared .env or the environment). Without it the script explains what to do and exits 0.
Writes voice/audio/<lang>/<id>.mp3, voice/audio/manifest.json and voice/review_sheet.csv (give the sheet to the native speaker).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.voice.package import package_status  # noqa: E402
from app.voice.prompt_audio import LANGS, generate_prompt_audio  # noqa: E402
from app.voice.tts import GoogleCloudTTS  # noqa: E402

NO_KEY_HELP = """Google Cloud Text-to-Speech is not configured, so no audio was generated.

To generate the prompt audio:
  1. Enable the Text-to-Speech API in a Google Cloud project and create an API key.
  2. Put it in FarmTrack/.env as GOOGLE_TTS_API_KEY=... (optionally TTS_VOICE_HI / TTS_VOICE_EN).
  3. Run this script again.
The review sheet (voice/review_sheet.csv) was still written so the native speaker can check the texts now."""


def print_status(settings) -> None:  # noqa: ANN001
    print(f"TTS_PROVIDER={settings.tts_provider}  key configured: {'yes' if settings.google_tts_configured else 'no'}  "
          f"voices: hi={settings.tts_voice_hi} en={settings.tts_voice_en}")
    for row in package_status(settings):
        size = f"{row.audio_bytes / 1024:.0f} KB"
        print(f"  {row.lang}: {row.with_audio}/{row.prompts} prompts have audio ({size}), catalogue version {row.version}")
        if row.missing:
            shown = ", ".join(row.missing[:8]) + (" ..." if len(row.missing) > 8 else "")
            print(f"      without audio: {shown}")


def list_voices(settings) -> int:  # noqa: ANN001
    if not settings.google_tts_configured or not settings.google_tts_api_key:
        print(NO_KEY_HELP)
        return 0
    tts = GoogleCloudTTS(settings.google_tts_api_key, {"hi": settings.tts_voice_hi, "en": settings.tts_voice_en})
    failed = False
    for code, chosen in (("hi-IN", settings.tts_voice_hi), ("en-IN", settings.tts_voice_en)):
        names = tts.list_voices(code)
        if names is None:
            print(f"{code}: the voice list could not be fetched (see the log line above)")
            failed = True
            continue
        print(f"{code}: {len(names)} voices; chosen {chosen} is {'AVAILABLE' if chosen in names else 'NOT in the list'}")
        print("   " + ", ".join(names))
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="regenerate files that already exist")
    parser.add_argument("--lang", choices=LANGS, action="append", help="only this language (repeatable)")
    parser.add_argument("--only", help="comma-separated prompt ids")
    parser.add_argument("--speed", type=float, default=0.9)
    parser.add_argument("--voice-hi")
    parser.add_argument("--voice-en")
    parser.add_argument("--status", action="store_true", help="show how many prompts have audio, then stop (no request is made)")
    parser.add_argument("--list-voices", action="store_true", help="list the Google voices for hi-IN and en-IN, then stop")
    args = parser.parse_args()

    settings = get_settings()
    if args.status:
        print_status(settings)
        return 0
    if args.list_voices:
        return list_voices(settings)
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
    print_status(settings)
    print("Next: copy nothing by hand. The backend serves voice/audio at /audio-prompts and GET /v1/voice/catalogue (or "
          "/v1/voice/package) lists it; the app downloads what changed the next time it is online.")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
