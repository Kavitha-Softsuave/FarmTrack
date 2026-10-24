# Voice package: generating the spoken prompts once a Google key exists

Status (24 Oct 2026): **no key exists, so no audio has been generated and no real Google call has ever been made.** Everything below was
tested against a mocked Google service only (`backend/tests/api/test_voice_package_api.py`). Until the audio exists the app speaks with the
phone's own voice. Whether a Hindi voice such as `hi-IN-Neural2-A` really exists, how it sounds and what it costs are **unverified**:
find out with the steps below, with a real call.

## What the "voice package" is
- `voice/prompts.json`: the fixed prompts (159 ids, Hindi and English text). The Hindi text is machine-drafted and needs a native speaker.
- `voice/audio/<lang>/<id>.mp3` plus `voice/audio/manifest.json`: the generated audio (not committed until it is reviewed).
- `voice/review_sheet.csv`: one row per prompt and language for the native speaker (text, audio file, OK, corrected text, notes).
- The backend serves it: `GET /v1/voice/catalogue?lang=hi` (texts, audio url and sha256 per prompt; the `version` changes whenever a
  text or an audio file changes and is the ETag), `GET /audio-prompts/<lang>/<id>.mp3` (one file), and `GET /v1/voice/package?lang=hi`
  (all files of one language in one zip with a `manifest.json`; 404 `voice_package_empty` until audio exists; 304 when the app is current).
- The app compares the catalogue `version` and downloads what changed the next time it is online. Nothing is copied into the app by hand.
- Advice audio (different every time) is synthesised on demand by the backend and cached in `backend/storage/audio/`: it needs the same key.

## 1. Get a key
1. Google Cloud console: create or pick a project, **enable "Cloud Text-to-Speech API"**, and make sure billing is enabled for the project.
2. APIs and Services > Credentials > Create credentials > API key. Restrict the key to the Cloud Text-to-Speech API (and, for production,
   to the server's IP address). The key travels in the `X-Goog-Api-Key` header, never in a URL, and is never logged.
3. In `FarmTrack/.env` (never commit it, never paste it anywhere):
   ```
   TTS_PROVIDER=google
   GOOGLE_TTS_API_KEY=<the key>
   TTS_VOICE_HI=hi-IN-Neural2-A
   TTS_VOICE_EN=en-IN-Neural2-A
   ```
   The two voice names are defaults chosen without a listening test.

## 2. Check that the voices exist (real call, no audio is generated)
```
cd backend
.venv/Scripts/python scripts/generate_prompt_audio.py --list-voices
```
It prints every voice Google offers for `hi-IN` and `en-IN` and whether the configured one is in the list ("AVAILABLE" or "NOT in the list").

## 3. Listening test (a person, not a script)
Candidates to compare on the same 5-10 prompts, by the native Hindi speaker (and an English speaker for `en-IN`): one or two `Neural2` voices
(female and male), one `Wavenet` voice and, if the list shows them, a `Chirp3-HD` voice. Chirp 3 HD has no speaking-rate control, so it
cannot be slowed down; the others are generated at speed 0.9. Pick by clarity of numbers, units and medicine names, not by how pleasant it is.
```
.venv/Scripts/python scripts/generate_prompt_audio.py --lang hi --only welcome,choose_language --voice-hi hi-IN-Neural2-B --force
```
Listen to `voice/audio/hi/*.mp3`, copy what you want to keep elsewhere, repeat with the next voice. Then put the winner in `.env`
(`TTS_VOICE_HI`, `TTS_VOICE_EN`) and delete the trial files in `voice/audio/` before the full run.

## 4. Generate everything
```
.venv/Scripts/python scripts/generate_prompt_audio.py          # or: make voice
.venv/Scripts/python scripts/generate_prompt_audio.py --status # or: make voice-status
```
Safe to repeat: a file is regenerated only when its text, voice or speed changed (`manifest.json`); a file with no manifest entry (a human
recording that was dropped in) is never overwritten without `--force`. The command exits 1 if any prompt failed, and prints, per language,
how many prompts have audio. The same numbers are on the admin site, page **Voice**, and as a line on the dashboard.

## 5. Review and publish
1. Give `voice/review_sheet.csv` to the native speaker. A text changed after review is flagged `TEXT CHANGED after review`.
2. Corrections go into `voice/prompts.json`; run step 4 again (only the changed prompts are regenerated).
3. Commit `voice/prompts.json`, `voice/audio/` and the review sheet (decide with the owner whether the mp3 files belong in git or on the server only).
4. Deploy the backend with the `voice/` folder. The app sees the new catalogue `version` and downloads the new files.

## Known limits
- No Google voice list mentions Pahari dialects; Hindi and English only.
- Machine speech mispronounces numbers and units unless the text is written for the ear (spoken texts are written that way; the review catches the rest).
- Prices were not verified. Spoken advice audio is cached by text, so each distinct sentence is paid for once.
