# FarmTrack mobile (Flutter)

Voice-guided app for low-literacy farmers: it speaks every step (Hindi, English), the farmer takes a photo and ticks
green or red. Flutter 3.47 / Dart 3.13, **Android first** (minSdk 24 = Android 7+). The iOS project exists (iOS 15+) but
has not been looked at yet. No code generation.

## Run
```
flutter pub get
flutter run --dart-define=USE_MOCK_API=true                      # demo without a backend (canned answers, log in with f001 / farm1234)
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000      # real API (10.0.2.2 = host PC seen from the Android emulator;
                                                                 # a real phone needs the PC's LAN address or a deployed server)
flutter analyze && flutter test                                  # must stay clean (754 tests, about 1 minute)
flutter build apk --split-per-abi                                # needs the Android SDK, never run on the dev PC
```
Dart defines: `API_BASE_URL` (default `http://10.0.2.2:8000`), `USE_MOCK_API` (default false, always on in tests).
Demo account (mock and dev backend): user name `f001` (to `f050`), password `farm1234`. Backend demo: start it with
`DEMO_DISEASE_HINTS="Apple=Apple___Apple_scab:0.9"` to get a scab result from the stub vision.
Real backend check: `tool/run_live_check.ps1` (or `.sh`) starts a local offline backend, runs `test_live/` over real HTTP
(31 calls) and stops it. API fixtures for the contract test come from `backend/scripts/dump_api_fixtures.py`
(re-run it after any backend change, then `flutter test test/contract_fixtures_test.dart`).

## Try it on an Android phone
1. PC: `powershell -ExecutionPolicy Bypass -File ..\scripts/start_backend_for_phone.ps1` (real vision models, no cloud calls, listens on
   the Wi-Fi; allow Python through the Windows firewall once). It prints the PC's address.
2. Build: `powershell -ExecutionPolicy Bypass -File tool/build_apk.ps1` (needs JDK 17 and the Android SDK, see
   `../docs/open-questions.md`); the APK is copied to `../dist/FarmTrack-test.apk`. Copy it to the phone and install it
   (allow "install unknown apps" for the file manager).
3. Phone and PC on the same Wi-Fi. In the app, login screen: tap "Server" and type the address the script printed
   (`http://<PC address>:8000`). Log in with `f001` / `farm1234`.
4. Scan: camera button or the gallery button next to it (up to four photos), then listen.

## How it works
- **Voice:** prompts in `assets/voice/prompts.json` (copy of `../voice/prompts.json`; run `python tool/sync_voice_assets.py`
  after changing it). Per sentence: bundled mp3, else server audio (cached by hash), else the phone's TTS. Dynamic advice
  text comes from the server (`spoken`). Every screen is built with `VoiceScaffold` (speaks once on entry): one slim top bar (back, the screen's small buttons, the speaker), the
  content, and at the bottom only the screen's one main action. The spoken sentence floats over the content as a one-line caption while it is
  spoken (tap to open all of it); there is no footer. Colours: green = done/yes, red = stop/no, grey = waiting, yellow = warning only, blue = information.
- **Languages are data:** `assets/l10n/languages.json`, `strings.json`, the prompt file. A new language needs no code.
- **Voice package (24 Oct 2026):** at start the app loads the saved server catalogue, fetches a fresh one and, only over Wi-Fi or a cable,
  downloads every prompt audio file not on the phone yet (`VoicePackage` in `lib/core/voice/catalogue_sync.dart`; again when the phone reaches Wi-Fi;
  the farmer's language first). Order per sentence: bundled mp3, cached server file (works offline, checked first), download when online (6 s limit),
  phone TTS, caption only. Without any server audio (no TTS key yet) everything is spoken by the phone's voice.
- **Language list is data:** `assets/l10n/languages.json` (`badge` = the letter drawn in the button circle). More than two languages stack.
- **Weather flag:** `GET /v1/meta` `weather_enabled` (missing = true, last answer kept on the phone). False hides the forecast strip and the
  temperature/humidity/rain/leaf tiles of "My field" (the soil tile and the server's risks stay).
- **Offline:** photos and spray entries wait in `<app folder>/pending`, are sent when the network is back (connectivity stream, app resume, 30 s to 15 min
  timer, tap on the "Waiting to send" card), with an `Idempotency-Key` so a retry never duplicates. The queue survives restarts (7 days, 20 items); waiting
  diary entries show as waiting after a restart. The last advice (7 days) and the last diary list are kept on the phone: Home shows a "Last advice" card
  that opens it without internet, the diary shows its saved list with the offline marker.
- **Push:** `lib/core/push` has the interfaces only (no Firebase packages yet); steps to switch FCM on are in `../docs/design-notes/mobile2a.md`.
- **Login:** always required: user name + password (`POST /v1/auth/login`; no OTP, no phone number), tokens in secure storage,
  one shared refresh, a per-install device id sent at login. Only the last user name is remembered (never the password).

## Structure
```
lib/core/      config, theme, network (ApiClient, Dio, Mock), models, offline queue, push, voice, widgets, router, providers
lib/features/  onboarding auth home scan result diary field alerts ask settings
assets/        l10n (strings, languages, ask suggestions), voice (prompts), crops
test/          widget and unit tests; test/support = FakeVoice, fake TTS/audio/camera, TestEnv; test/fixtures/api = real backend answers
test_live/     tests against a running backend (not part of `flutter test`)
```

## Verified on 24 Oct 2026 / not verified
(24 Oct session, later: slim layout, green "I sprayed" tick and sprayed state looked at on the emulator at 411x731 dp and 320x569 dp with text 1.3 to 1.5, against
a real local backend; 754 tests. The release APK is arm64 and cannot start on the x86_64 emulator, so the emulator runs used a debug x86_64 build.)
Verified: analyze clean, 741 tests, release APK (arm64, 25 MB) built, debug x86_64 APK installed and started on an Android 15 emulator (language screen
seen and tapped), live check against the real backend (23 of 31 calls pass; the 8 others need the uncommitted photo folder).
Not verified: a real phone, real camera and permission texts, Hindi TTS voices, audio playback, secure storage on old phones, TalkBack,
behaviour on a 3 GB Android 9 phone, push, any screen after the language screen on the emulator. Design notes and doubts: `../docs/design-notes/mobile1.md`, `mobile2a.md`,
`mobile2b.md`, `contract.md`; open questions for the owner: `../docs/open-questions.md`.
