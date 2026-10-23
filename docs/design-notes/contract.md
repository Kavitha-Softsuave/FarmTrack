# CONTRACT (Flutter app vs the REAL backend): findings, decisions, how to run

Status 19 Oct 2026: 93 real answers recorded, 181 contract tests (176 pass, 5 skipped = known mismatches below), live run against a
real local backend passed (31 tests, 1 warning). No Android SDK or phone: everything here runs with `flutter test` and a local Python server.

## What exists (all new files)
- `backend/scripts/dump_api_fixtures.py`: runs the real FastAPI app in-process (TestClient, no network, mock providers, real rules,
  composer, auth, validation, rate limits, error handlers) and writes one JSON per scenario to `mobile/test/fixtures/api/`
  (`{request, status, response_headers, body, note}`). Only the disease result is forced (hinted stub). One command, about 10 s:
  `backend\.venv\Scripts\python backend\scripts\dump_api_fixtures.py` (`--out DIR`, `--verbose`). It prints `WARN` lines when a
  scenario no longer behaves as designed (for example a scan status changed) and when `contracts/openapi.json` is out of date.
- `mobile/test/contract_fixtures_test.dart` (default `flutter test`): parses every fixture with the real models and checks them.
- `mobile/test_live/live_api_test.dart` + `mobile/tool/run_live_check.ps1` / `.sh`: real HTTP, real `DioApiClient`, real backend.

## How to run
- Fixtures: command above, then `cd mobile; flutter test test/contract_fixtures_test.dart`. Run both after every backend change.
- Live check (not in CI, workflows untouched): `powershell -ExecutionPolicy Bypass -File mobile\tool\run_live_check.ps1`
  (`-NoHints`, `-Port N`) or `bash mobile/tool/run_live_check.sh` (`NO_HINTS=1 PORT=N`). It starts uvicorn from `backend\.venv` with
  ENV=dev LLM_PROVIDER=mock OPENAI_API_KEY= TTS_PROVIDER=null GOOGLE_TTS_API_KEY= EMBEDDINGS_PROVIDER=hash VECTOR_STORE=memory
  PUSH_PROVIDER=log ZOHO_PROVIDER=mock IOT_PROVIDER=mock WEATHER_PROVIDER=csv ALERT_SCHEDULER=0, a temp SQLite file and storage
  folder, `DEMO_DISEASE_HINTS=Apple=Apple___Apple_scab:0.9` (the setting exists now), waits for `/health`, runs
  `flutter test test_live`, ALWAYS stops the server (tested: success, failed start, bash variant) and prints LIVE CHECK PASSED/FAILED.
  The server is started through a one-line launcher that switches the repo `.env` off, so that file is not even read. The test
  itself refuses to run unless `/v1/meta` says env dev/test, llm mock, tts null, push log, zoho mock.
- **Port 8765 is taken on this PC** (`eaip-agent.exe`, pid 5284, listens on 127.0.0.1:8765 and answers 404). Both scripts therefore
  use the next free port (8766 in my runs) unless a port is given; the test reads it from `--dart-define=LIVE_API_URL`.

## Mismatches found (nothing in other agents' files was edited; no model or client fix was needed)
Each: what the server sends, where the app reads it, proposed fix. Items 1 to 3 and 5 have a test that is SKIPPED with this number
while the mismatch exists and passes by itself once fixed.

1. **confirm_crop never asks the question** (medium, 1-line fix). Server: `scan_service.py:328`
   `next_steps: [{"action": "confirm_crop", "prompt_id": "crop_tap_yes"}]`. App: `crop_confirm_screen.dart:34-37` speaks
   `pickPrompt(next_steps[confirm_crop], 'crop_confirm_prompt')` then `crop_tap_yes`, `crop_tap_no`; the server id wins, `promptList`
   drops the duplicate, so the farmer hears "This looks like apple. If it is right, tap the tick. If not, tap the cross." and never
   "Is this the right crop?". The mock sends `crop_confirm_prompt`. Fix: backend line 328 `prompt_id="crop_confirm_prompt"` (the
   documented meaning of `next_steps[].prompt_id` is the prompt for that step; `ScanOut.spoken` already asks the question).
2. **Crop ids differ in case** (medium). Server writes `Apple`, `Tomato`, `Maize`... (`/v1/meta supported_crops`, `crop.crop_id`,
   `farmer.crops`); `assets/l10n/strings.json` keys are `apple`, `tomato`. `AppResources.cropName/cropGroup`
   (`app_resources.dart:95-102`) look up case-sensitively, so the crop chooser (`crop_choose_screen.dart:95-96`, ids from
   `supported_crops`) shows English names in Hindi mode and every crop gets the tree picture (`cropGroup` falls back to fruit).
   Screens that pass `serverName` are fine. Fix: `_crops[id] ?? _crops[id.toLowerCase()]` in both methods. The backend accepts any
   case (live test: spray log, ask and confirm with `apple` all answer `Apple`).
3. **No Hindi name for most crops** (low/medium). `crop.name = {"en": "Pea", "hi": "Pea"}` (also Wheat, Cauliflower, ...; only the
   demo crops have Hindi). `cropName(..., serverName:)` trusts the server `hi`, so the app's own Hindi table is ignored. Fix: backend
   fills `name_hi` (the app has 27 names in `strings.json`), or the app prefers its table when `hi` has no Devanagari.
4. **The app sends no `device_id` at login** (medium, found by the live run, printed as `LIVE WARNING`). `otp_screen.dart:69`
   calls `verifyOtp(requestId:, otp:)`. Server: a refresh token used twice (for example the answer of a refresh got lost on a bad
   network, the app retries with the old token) revokes every session with the same `device_id`; with none, that is every session of
   the farmer (`auth_service.py:128/151`). Measured: the second phone was logged out too. Fix: the app creates a random id once per
   install (secure storage) and sends it (`OtpVerifyIn.deviceId` exists); optional backend grace window for the previous token.
5. **not_a_disease opens with a question** (low). Server: `next_steps = [add_photo -> scan_add_more, ask_expert -> result_expert]`.
   `expert_screen.dart:69-70` speaks the add_photo prompt as the "variant", so `scan_add_more` ("Is the problem on other leaves too?
   take one more photo") comes before the finding ("I do not see a disease", which is in `scan.spoken`, spoken next). Mock data uses
   `result_not_disease` there. Fix: speak the fixed `result_not_disease` first, then `scan.spoken`, then the add-photo prompt.

### Observed, safe, no change needed
- Closed enums all match: scan status (6 of 6 seen), next action (6), disease route (3), severity (3), timing (`spray_now`, `wait`,
  `repeat_within_days` seen; `not_needed` and `unknown` are in the schema but no scenario produces them). Open sets seen:
  warning codes `NO_TANK_MIX DOSE_PER_200L NO_WAITING_PERIOD DODINE_RESTRICTIONS PROPOSED_BAN CAPTAN_OIL_INFO PRODUCT_NOT_RECOGNISED`
  (`STALE_HISTORY` also exists, seen for Maize farmers only), alert kinds
  `scab_infection_risk marssonina_alternaria_risk late_blight_risk rain_washoff waiting_period`, risk ids, quality issues
  `blurry too_dark too_bright too_small` (+ documented `unreadable`: the app has no icon or tip for it and falls back to the blurry tip).
- Unknown values degrade: unknown status = needs_expert (expert screen), severity = yellow, route = none, next action = unknown.
- All 8 distinct prompt ids the server names in `next_steps` / `tip_prompt_id` exist in `voice/prompts.json` (app copy 135 ids; the server
  catalogue ids and texts equal the app copy, so `sync_voice_assets.py` is current at the time of the run).
- `needs_expert` with an unknown crop (farmer with two crops, no guess) is a `needs_expert` scan with `crop.unknown=true`, not
  `confirm_crop`: the app's route "confirm_crop + unknown crop -> crop chooser" cannot happen with this backend (harmless).
- `ask` answers hold only the answer language in `spoken.text` (other language is `""`); `LocalizedText.forLang` falls back.
- Audio refs: `/audio/<sha256>.mp3`, `sha256` is 64 hex, `audio.hi|en` are `null` without TTS (all fixtures except the fake-TTS ones).
- Errors: every body has `code` and `message`; 422 also has FastAPI's `detail`; 429 has `Retry-After` and `details.retry_after_seconds`;
  the OTP screen's codes (`invalid_otp`, `otp_expired`, `otp_attempts_exceeded`, `otp_already_used`) match. `invalid_phone` is never
  sent for a bad format (it is a 422 `validation_error`), harmless because the app checks 10 digits first.
- Idempotency works for scans, spray logs and expert requests (same id, header `Idempotent-Replayed: true`). The app only sends the
  key on scans and spray logs (`ApiClient` has no key for expert requests; the server supports it).
- Spray diary: the plain "I sprayed" tick (only `advice_id`) works and uses the first product (the one read aloud). Times without
  offset (what `DateTime.now().toIso8601String()` writes) are read as India time (checked). For "today" send no `sprayed_at`: the
  server then uses its demo clock; a phone date after the demo clock is accepted but lands "in the future" of the demo data.
- CORS now allows the `Idempotency-Key` header (BACKEND-FIX); native apps do not need CORS anyway.
- `contracts/openapi.json` equals the current backend schema; every call of `DioApiClient` hits a path, method and query the contract has.

## Decisions and doubts
- Fixtures are made deterministic: ids are rewritten to fixed 32-hex values (references stay consistent), tokens become
  `FIXTURE-ACCESS-TOKEN` / `FIXTURE-REFRESH-TOKEN`, alert lists are sorted (equal timestamps have random ids). Two dumps give identical files.
  Re-running with a changed backend changes them, which is the point; review the diff.
- "Known mismatch" tests are skipped, not failed, so the default suite stays green while the owners decide; remove the wrapper when fixed.
  The closed enum and prompt-id checks are strict: a new status or an unknown prompt id fails the suite on purpose.
- The scenario with audio uses an offline fake TTS (bytes are not real mp3); the real TTS format is not covered.
- Hindi quality is only checked softly (Devanagari present); native review of the texts is still open.
- Not covered by fixtures: `otp_expired` (needs time travel), 413 upload too large, a `Retry-After` on scans, Postgres, real models, FCM push.
- The diary, field, alerts, ask and settings screens (MOBILE2) were still being written during this work; they are covered at model level
  (every real answer parses, key fields, enums) but not through their screens. Re-run the contract test after they land.

## Not verified
Anything that needs a device (camera, TTS voices, audio playback, secure storage), a real TLS or mobile network, the real OpenAI or Zoho
services, Postgres, and the scheduler running on its own (the live backend runs with `ALERT_SCHEDULER=0`; alerts come from the evaluator
called in the dump script).
