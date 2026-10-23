# MOBILE1 notes (Flutter app: architecture, voice layer, login, home, scan flow, results)

Status 19 Oct 2026 (login changed later, see mobileauth.md: 685 tests now): `flutter analyze` clean, `flutter test` 198 tests pass (about 25 s), `dart format` clean.
Nothing could be built or run on a device: **no Android SDK, JDK or phone here**. See "Not verified".

## Decisions (and why)
- **State and routing:** flutter_riverpod 3 (Notifier, no code generation), go_router 18. Flat route list (no nesting) so `go()`
  replaces the screen instead of stacking. Screens that were opened with `push` get a back arrow by themselves; screens
  opened with `go` must pass `onBack` to `VoiceScaffold` (it also maps the phone's back button to it).
- **One frame for every screen:** `VoiceScaffold` = back arrow, body, voice-missing banner, large caption, speaker button
  bottom-left, optional main action bottom-right. It owns `SpeakOnEnter`, so every screen speaks once per visit and stops
  when it goes away. Speech that answers a tap uses the screen's `owner` object (`speak(items, owner: _owner)`) so the caption
  shows and a closing screen never cuts off the next screen's speech (`stop(owner:)`).
- **Voice order:** bundled mp3, then server audio (`/audio-prompts/<lang>/<id>.mp3` from `GET /v1/voice/catalogue`, cached by
  sha256 in the app support folder, 40 MB cap), then on-device TTS (`flutter_tts`, hi-IN or en-IN, falling back to en-US/en-GB).
  If the bundled file fails to play the server copy is tried next. Dynamic text: `SpokenOut.audio[lang]` else TTS of the text.
  No audio exists yet (`voice/audio/` is absent), so every sentence is currently spoken by the phone's TTS.
- **No voice for a language:** the caption stays for a reading time (60 ms per character, 1.5 to 8 s), `VoiceState.missingVoices`
  gets the language and a yellow banner shows. The first lookup waits 700 ms once because the Android engine starts late.
- **Languages are data:** `assets/l10n/languages.json` (native name, TTS locales, `prompt_id` of the language-name prompt),
  `assets/l10n/strings.json` (interface words and crop names), `assets/voice/prompts.json`. A new language = those three
  files plus `python tool/sync_voice_assets.py` (it also edits the pubspec asset list). `LocalizedText` keeps every key.
- **Server is the source of truth:** `next_steps[].prompt_id` is used when the catalogue knows the id (else our own mapping);
  `quality.tip_prompt_id` likewise (else mapped from `issues`); the advice `spoken` text and audio are played as sent.
  An unknown scan `status` is treated as `needs_expert`; an unknown severity as yellow.
- **Home tour:** the very first Home visit speaks the intro and each button (6 prompts); later visits only `home_intro`; the
  speaker button always replays the whole tour. After a fresh login `login_ok` comes first.
- **Crop confirm:** speaks `crop_is_<crop>` (or the crop name when no prompt exists), `crop_confirm_prompt`, then also
  `crop_tap_yes` and `crop_tap_no` (the brief names only the first two; first-time farmers need to hear what tick and cross mean).
- **Pictures:** tick = `check`, cross = `close`, camera = `photo_camera`, speaker = `volume_up`, notebook = `edit_note`
  (sheet with a pencil), gear = `settings`, bell = `notifications`, house = `home`, back = `arrow_back`, round arrow = `refresh`,
  green arrow = `arrow_forward`. **Ask expert uses `live_help` (speech bubble with a question mark)** because `home_ask` says
  "question mark picture". **My field shows grass under a cloud** because `home_field` says "field picture" while
  `field_tap_weather` says "cloud picture". All icons are Material stock icons: **test them with real farmers** and replace
  with drawn pictures if confusing.
- **Crop pictures:** none exist. Each crop shows the generic picture of its group (tree = fruit, leaf = vegetable, grass = cereal)
  in a group colour. Drop `assets/crops/<crop_id>.png` in and `CropPicture` uses it automatically (apple and pear look the same today).
- **Photos:** `image_picker` with `imageQuality: 80`, `maxWidth/maxHeight: 1600`; no extra compression package. Thumbnails decode
  at 400 px. The camera opens through the phone's own camera app, so the manifest has **no CAMERA permission**; on Android
  `permission_denied_camera` is therefore only reachable if that permission is ever added (iOS reports it).
  `retrieveLostData` is handled (Android may kill the app while the camera is open on a 3 GB phone).
- **Login (changed 19 Oct 2026, no OTP, no phone number):** one screen at `/login`: user name + password typed with the phone's own keyboard
  (64 dp+ fields with a picture and a word above, a big eye button to show or hide the password, the green tick logs in). The app
  always asks (a logged-out farmer cannot reach any other route). The user name is trimmed and lower-cased; the last successful one is
  prefilled from SharedPreferences (`last_username`), the password is never stored (the session is in secure storage). Errors map to prompts:
  `invalid_credentials` (or a malformed pair, or a 422) to `login_wrong`, an empty field to `login_fields_needed`, connection problems to
  `error_no_internet`, `rate_limited` and the rest to `error_try_again`. Details in `docs/design-notes/mobileauth.md`.
- **Tokens:** `flutter_secure_storage`; 401 triggers one shared refresh (refresh tokens rotate and a replay revokes the device),
  the request is replayed (multipart bodies are cloned); a rejected refresh clears tokens and sends the router to login; an
  unreachable server keeps the login. Logout clears the phone at once and calls `POST /v1/auth/logout` in the background.
- **GET retry:** 2 retries (0.5 s, 1 s) on connection errors, timeouts and 502/503/504. POST is never retried.
- **Riverpod 3 retry** is switched off (`retry: (_, _) => null`) so a failure reaches our error screen immediately.
- **Format:** `analysis_options.yaml` sets `formatter: page_width: 120`; the CI workflow fails on unformatted code.

## Bugs found by the tests while building (fixed, worth knowing)
- `Future.whenComplete(() => map.remove(key))` returns the very future it waits for: a deadlock (audio cache). Use a block body.
- Speaking from `didUpdateWidget` or `dispose` updates a `ValueNotifier` while the tree is locked: both are deferred now.
- Old pages stay mounted during a route fade: a rebuild of the old page must not speak (review screen) or redirect (result screens
  keep the last scan: `ScanScope`).
- Labels under big buttons and the speaker/main-action row overflowed on 320 dp phones and at 1.6x text: labels now scale down.

## Doubts for the owner or the team
- **Hindi UI words** in `assets/l10n/strings.json` (Fine/Be careful/Serious for severity, "Show written words", crop names, "Coming
  soon") are my draft; the voice prompts were not touched. Native review needed, like the prompts.
- **Severity wording** "Serious" for red is a guess: red means a serious disease or an urgent warning, not "danger to you".
- **Home tour length:** about six sentences on the first visit. May be too long for farmers; field test.
- **Captions:** only the sentence being spoken (or the last one) shows, 20 sp, at most 17 percent of the screen height. A deaf user
  with sound off sees sentences go by at the reading-time pace. Consider a "show all sentences" list later.
- **No gestures:** crops are paged with big arrows (6 per page); the advice and settings screens scroll (long content). Everything
  else fits a 360x640 phone at 1.0 text and mostly at 1.5x.
- **Unused optional prompts:** `otp_resend`, `ask_phone`, `ask_otp`, `otp_sent`, `otp_wrong`, `phone_invalid` (OTP prompts, no screen uses them any more), `scan_remove_photo`,
  `scan_add_more_yes/no`, `scan_keep_still`, `scan_tap_capture` (the system camera has its own shutter), `nav_home`, `nav_back`,
  `please_wait`, `permission_denied_notifications`, `notification_permission`, alerts/diary/field/ask detail prompts (MOBILE2).
- **Button highlight while a button is being spoken about** (plan 4.9) is not built; only the speaker button rings while speaking.
- **App name and icon:** launcher icon and native splash are the Flutter defaults; app label is "FarmTrack".
- **Offline:** an upload without network ends in the error screen with one retry. The queue (`offline_saved`, `back_online_sent`) is
  MOBILE2's: the single hook is `ScanFlowNotifier.submit()` (phase `failed`, error `ApiException` with `isConnectionProblem`).
- **On-device detector:** `OnDeviceDetector` is a stub returning null (documented in its doc comment: model not converted, and
  field tests showed 0 of 23 correct). The upload sends `client_crop` and `client_confidence` only when it returns something.
- `POST /v1/scans/{id}/photos` (`addPhotos`) exists in the clients but the UI never uses it: all photos travel with the first upload.

## Not verified (needs an Android SDK or a phone)
APK and IPA build; the real camera flow and permission texts; `flutter_tts` Hindi voices and the stop/cancel callback order on
real engines (a late "cancel" is ignored once per stop, and `speak` has a length based safety timeout); `just_audio` completion
semantics; secure storage on old phones; iOS 15 build and ATS (`NSAllowsLocalNetworking` added for a local dev server); behaviour
on a 3 GB Android 9 phone; install size (use `--split-per-abi`); Ahem font widths in tests are wider than real fonts, so test
layouts are pessimistic. Visual check was done only through temporary test screenshots (deleted) with Nirmala UI and Material
icon fonts loaded.

## Packages (pinned by `flutter pub add`, Flutter 3.47.7)
flutter_riverpod 3.4.3, go_router 18.1.0, dio 5.11.1, flutter_secure_storage 11.2.0, shared_preferences 2.5.6, flutter_tts 4.2.5,
just_audio 0.10.6, image_picker 1.2.4, connectivity_plus 7.3.2, path_provider 2.1.6, crypto 3.0.7. Removed from the template:
cupertino_icons. **Deliberately not added:** permission_handler (the system camera app asks by itself), flutter_image_compress
(image_picker already resizes and re-encodes), url_launcher (to open the phone's settings after `permission_denied_camera`;
add it if the voice prompt is kept), intl, uuid, firebase_* (push is MOBILE2). `material_ui 1.7.0` appears as a new transitive
dependency of Flutter 3.47; nothing to do. Private named parameters (`required this._ui`) need Dart 3.12 or newer.

## For MOBILE2
- Replace the placeholder screens in place (same route names): `lib/features/{diary,field,alerts,ask}/*_screen.dart`.
  `/diary?advice=&crop=&product=` arrives preselected (`DiaryScreen.adviceId/cropId/productId`, `Routes.diaryFor`).
- Build screens with `VoiceScaffold(script: promptList([...]), owner: _owner, body: ...)`; dynamic text with
  `spoken.toUtterance(lang)`; errors with `ErrorRetryScreen` / `errorPromptFor`; typing with the system keyboard (see `features/auth/login_screen.dart`, `ask_type_screen.dart`).
- `ApiClient` already has `createSprayLog`, `listSprayLogs`, `field`, `listAlerts`, `markAlertRead`, `registerDevice`, `ask`,
  `createExpertRequest`; `MockApiClient` answers all of them (including a refused answer for questions containing "lottery").
- `unreadAlertsProvider` feeds the bell badge on Home; `onlineProvider` the offline sign; `connectivityServiceProvider` is ready.
- Tests: `test/support/fakes.dart` (FakeVoice with `spokenIds`/`log`/`unknownIds`, FakeTts, FakeAudio, FakePhotoPicker) and
  `test/support/harness.dart` (`TestEnv.create(...)`, `pumpApp`, `useSmallPhone`); `finders.dart` has `tapKey`, `enterLogin`, `logInWith`,
  `expectBigTouchTargets`. `FakeVoice.unknownIds` catches a typo in a prompt id; `prompt_catalogue_test` scans the sources for ids.

## Contract observations (no change requested)
- The app sends no language with a scan; it uses `PATCH /v1/me {language}` after login and on every language change.
- Audio urls are used exactly as given and resolved against `API_BASE_URL` when relative (`/audio/..`, `/audio-prompts/..`).
- A server prompt id that is not in `voice/prompts.json` is skipped silently by the app (the fallback id is spoken instead).
