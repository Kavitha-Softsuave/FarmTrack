# MOBILE2B notes (offline queue, Ask, Settings, demo-clock strip, accessibility)

Status 19 Oct 2026: `flutter analyze` clean, `dart format` clean, `flutter test` 635 pass (5 skipped = the CONTRACT agent's "known mismatch"
tests). 124 of those are new and mine: offline_queue 34, offline_flow 12, ask 23, settings 15, demo_banner 12, a11y_layout 16, a11y_contrast 12.
Nothing could be run on a phone (no Android SDK): see "Not verified".

## What was built
- **Offline queue** (`lib/core/offline/`): `PersistentOfflineQueue` (+ `KeyedOfflineQueue`, `QueueClock`) behind the frozen `OfflineQueue`;
  `offlineQueueProvider` now builds it (files in `<app support folder>/pending/<key>.json`, photos copied to `pending/<key>/`).
  `offline_status.dart` = `offlineStatusProvider`: flush triggers (login, back online, resume), the events, the Home cards' data.
  Screens: `features/offline/saved_offline_screen.dart` (route `/scan/saved`), `offline_cards.dart` (Home: waiting card, result card).
- **Ask** (`features/ask/`): `/ask` (ten cards from `assets/l10n/ask_suggestions.json` + "ask my own question"), `/ask/type`, `/ask/answer`.
- **Settings** (`features/settings/`): language buttons speak their own name, speech speed, volume, written words, log out through
  `/settings/logout` (tick/cross), version line (+ server URL in debug builds only).
- **Demo-clock strip**: `core/widgets/demo_clock_banner.dart`, shown by `VoiceScaffold` on every screen.
- **Accessibility/performance**: see the last section.

## Decisions (and why)
- **Synchronous file I/O in the queue** (`writeAsStringSync`, `copySync`...): items are a few small files (a copy of 4 photos is a few ms), the
  limit check and the write cannot interleave with another enqueue, and it runs under the fake clock of widget tests (async file I/O hangs
  there; MOBILE2A's tests also use the default queue). Documented in the class comment.
- **Folder:** the app support folder (private, not user-visible), not "documents": it is the folder `supportDirectoryProvider` already gives.
- **Same key for the live attempt, the retry button and the queue.** The frozen `enqueueScan` generates its own key, so a request that reached
  the server but timed out would have been repeated as a second scan. Added the additive interface `KeyedOfflineQueue.enqueue*WithKey`
  (the frozen interface is unchanged); `ScanFlowNotifier` keeps one key per photo set (reset on new photos, `reset()`, success). Diary
  (MOBILE2A): use `enqueueSprayLogWithKey` with the key of the live `createSprayLog` attempt for the same protection.
- **Which errors are retried** (deviation from the brief in two places): connection problem, timeout, **401 and 429 stop the round and keep
  everything** (401: the login ran out, the items wait for the next login; 429: slow down), **5xx and unexpected errors keep that item and try the
  next one** (one poison item must not block the rest), **400/404/422 drop the item** with a `dropped` event. 429 and 401 are not dropped
  because dropping a farmer's photo for a rate limit or an expired login would lose data. `unknown` kind is kept (a captive portal answers 200 HTML).
- **Items remember their farmer** (`owner`): on a shared phone farmer A's photo is not sent under farmer B's login (it waits until A logs in, or
  ages out after 7 days); a round does nothing while nobody is logged in (`canSend`). "Result ready" cards are scoped the same way.
- **Result card survives a restart:** ids of sent scans are kept in SharedPreferences (`offline_ready_scans`, 5 at most, 7 days); the result is
  fetched with `GET /v1/scans/{id}` when the in-memory answer is gone. There is no scan history screen, so the card is the only way back to it.
- **Announcements:** `back_online_sent` then `offline_result_ready` (new prompt) after a queued scan was sent, appended to the speech
  (`interrupt: false`), silent while the app is in the background. Sent diary entries are NOT announced here: MOBILE2A speaks `diary_sent` while the
  diary is open. A dropped item (4xx, expired, photo gone) says `error_try_again` once (also for diary items: if MOBILE2A also speaks, it is twice).
- **Queue full / photo gone:** `OfflineQueueException(reason)` -> ErrorRetryScreen -> `error_try_again` (as asked), with the retry button.
- **Ask:** every card has a voice prompt `ask_q_<id>` with the same text (a test enforces it), so bundled audio is used once generated; the
  server gets the same text. Typed questions are not read back. The answer is shown as large body text, so the caption strip is off on that
  screen (`VoiceScaffold.showCaption`). A refusal speaks the server's own text (`ask_no_answer` only when the text is empty: the real refusal
  already says "talk to an expert", so both would repeat it) and offers the blue expert button (`createExpertRequest(message: question)`, no scan,
  then `ask_expert_sent`). Expert requests are not queued offline (the queue has no such kind): error screen with retry. The question goes with the
  farmer's `primary_crop`, else the first of `crops`.
- **Questions were checked against the real backend gating** (`AskService` with a fake LLM, no network, `.env` not read): the first draft had four
  questions the server would refuse before the LLM ("medicine" is a trigger word; Hindi retrieval is lexical), now all ten reach the LLM in Hindi and
  English with crop Apple. Without any crop "rain after spray" is refused as ambiguous. "How to keep records" is NOT in the approved notes, so there
  is no such card. Cards never ask for a medicine or a dose.
- **Settings:** the model already had slow/normal/fast, volume and "written words"; kept all (the brief said normal/slow; removing fast would break
  `settings_speed`, "slower or faster"). Speed is applied to the phone voice rate and the mp3 playback speed by `DeviceVoiceService` (tested).
- **Demo strip:** one `GET /v1/meta` (`MetaOut.demo_clock` already existed in the contract and model), refetched when the phone is back online and
  on resume. Hidden when `release build AND env == prod`. The date is shown in Indian time with month names from `demo_month_words`. **It does not
  call the server under `flutter test`** (`demoBannerFetchProvider`): an extra meta call would eat a failure other tests queue for another call.
- **New route names:** `/scan/saved`, `/ask/type`, `/ask/answer`, `/settings/logout`. Direct deep links to `/ask/...` do not exist: the app always starts
  at Home (splash), tests use `router.go`.

## Small edits outside my own files
`routes.dart`, `app_router.dart` (4 routes; no fade when the phone disables animations), `app_theme.dart` (`amberDark`, `severityAccent`),
`processing_screen.dart` (queued scan goes to the saved screen), `home_screen.dart` (cards, `offline_result_ready` in the script, `amberDark` on the
notebook), `main.dart` (startup), `assets/l10n/strings.json` (keys `offline_`, `ask_`, `settings_`, `demo_`), `voice/prompts.json` (+15 ids:
offline_waiting, offline_result_ready, settings_logout_confirm, ask_tap_picture, ask_expert_sent, ask_q_x10; validator OK, synced). Existing tests
changed: `home_settings_test` (log out now asks first), `scan_capture_review_test` ("no internet" with a photo that does not exist now says
`error_try_again`; the real offline path is in `offline_flow_test`). No new packages.

## Accessibility and performance
- **Contrast:** `a11y_contrast_test` checks the three severity colours: text on the band (green 5.1, amber 8.9, red 5.6), ink on the soft panels, and
  the colour as an icon/border. **Amber failed:** `AppColors.amber` (#F2A900) as an icon on a light panel is only 1.8 to 2.0:1. It stays as a fill
  (ink text on it is 8.9:1); new `amberDark` (#946100, 5.0 on paper) and `severityAccent()` are the foreground. I used it in my screens and on the Home
  notebook. **Still bright amber as a foreground (not mine, please swap to `amberDark`):** `status_views.dart:34`, `advice_widgets.dart:72`,
  `expert_screen.dart:73`, `retake_screen.dart:34`, `diary_list_screen.dart:84,97`, `field_widgets.dart:32`, `field_words.dart:140`.
- **Text size:** every screen I own (and Home with the cards) is tested on 320x568 and 360x640 at 1.0, 1.6 and 2.0 in both languages without overflow.
  `app.dart` still caps the text at 1.6 (MOBILE1's choice: other screens were only checked to about 1.5); raise it to 2.0 only after checking them.
- **Semantics:** every icon-only button has a label (`BigIconButton` requires one); new ones reuse the `a11y_*` words ("First page", "Ask a farm
  expert", "Yes"/"No") or new `ask_send`. They are short action words, not the full voice sentence (TalkBack reads them with "button").
- **Animations:** page fades are off with `disableAnimations`; the Ask waiting bar stands still then. `ProcessingBody` (MOBILE1, scan upload) still
  animates its bar.
- **Before `runApp` (main.dart):** orientation lock, `AppResources.load` (2 JSON files, 11 KB), `PromptCatalogue.load` (prompts 40 KB + the asset
  manifest), `SharedPreferences.getInstance`, `getApplicationSupportDirectory`. They were awaited one after the other; now they run together
  (`(...).wait`), debug builds print `startup: <step> ready after N ms` and `runApp called after N ms`. Parsing on this PC takes 3 to 17 ms for
  both JSON files together, so the phone cost is mostly the platform-channel round trips. Everything else starts after the first frame: the offline
  queue (`FarmTrackApp` reads `offlineStatusProvider` post-frame), voice catalogue refresh, push, demo date. Not measured on a phone.
- **Thumbnails:** the only photo thumbnail (review screen) already decodes at 400 px; the new screens show no photos.

## Doubts for the owner or the team
- **Hindi wording** of the 15 new prompts and of the new interface words (draft, native review needed). The Hindi "रसायन" in the repeat-chemical
  question was chosen because the server's retrieval matches it (the notes say "chemical"); farmers may say "दवा".
- **7 days and 20 items / 100 MB** are the brief's numbers; a farm without signal for a week loses its photos silently except for one spoken error.
- **Expert requests offline** are not saved; a farmer without signal who is refused cannot queue the question.
- **Sources** under an answer are the server's English source strings (e.g. "HP Horticulture Dept ..."); a non-reader gets nothing from them.
- **Result cards:** only the oldest result shows (a count badge when more); the farmer cannot browse older results.

## Not verified (needs a phone)
Real file copy time of four camera photos on a 3 GB phone; `connectivity_plus` behaviour on captive Wi-Fi (it says online, the request times out: the
queue then retries with back-off); Android killing the app while items wait (files survive, covered by the restart tests on a PC); TTS of the new
Hindi sentences; the keyboard on the typing screen with Hindi input; TalkBack reading order; the real `rootBundle` load of the suggestions on a device
(tested through `tester.runAsync`).
