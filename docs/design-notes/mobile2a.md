# MOBILE2A notes (spray diary, My field, alerts, push)

Status 19 Oct 2026: `flutter analyze` clean, `dart format lib test` clean, `flutter test` all pass (about 640 tests, 5 skipped = the CONTRACT
agent's known mismatches). 137 of them are new (diary 57, field 30, alerts 25, push 25). Nothing could be run on a phone or an Android
SDK: see "Not verified".

## What exists
- **Diary** (`lib/features/diary/`): `/diary?advice=&crop=&product=` is the confirm screen ("I sprayed"), plain `/diary` is the list,
  `/diary/add` (plus button) is "write a spray I did". One flow widget (`diary_entry_screen.dart`) serves both entries: crop, medicine
  (typed, max 200 chars, or a name used before), confirm (crop picture, medicine, tick = save, cross = back; today / yesterday / other
  day of the last 14), saved (warning cards). `diary_providers.dart` holds the list, the waiting entries and the saver.
- **Field** (`lib/features/field/`): tiles with a word and the number small, risk cards, 7-day strip, stale and no-data states, a round
  arrow, the last answer cached per farmer in shared_preferences (`field_cache_<farmer id>`).
- **Alerts** (`lib/features/alerts/`): list (unread highlighted), detail `/alerts/detail?id=` (new route), scan button, 5-minute and
  resume refresh (`AlertsAutoRefresh`, wrapped around Home and the list in `app_router.dart`).
- **Push** (`lib/core/push/`): `PushTokenSource` (+ `NoopPushTokenSource`), `NotificationPermissionPort` (+ unsupported default),
  `PushService`, providers, `PushBootstrap` (wraps Home: attaches the router, starts the service, asks the permission once).
- Also edited (additive): `routes.dart` (`diaryAdd`, `alertDetail`, `alertDetailFor`), `app_router.dart`, `AlertOut.scanId` (+ `copyWithRead`),
  `MockApiClient` / `MockData` (new scenarios, below), `strings.json` (keys `diary_*`, `field_*`, `alerts_*`), `voice/prompts.json` (15 ids).
  Existing tests touched: `prompt_catalogue_test` (120 prompts became "at least 120"), `scan_results_test` (the diary now opens on the confirm
  screen, so it says name, question, tick, cross instead of `diary_intro`).

## Behaviour worth knowing
- **Speech after saving:** no warning = the prompt `diary_saved`. With warnings: the server's `spoken` text when it already contains the first
  warning (the real server reads "Done" + `diary_warning` + the FIRST warning only, with generated audio), then every other warning from its own
  text; if the server text is missing, `diary_saved`, `diary_warning` and each warning. Each warning card has its own speaker button.
- **Warnings are never colour only:** card colour + its own picture (warning triangle, red octagon) + the words "Be careful" / "Serious".
- **No internet while saving:** the entry goes to the offline queue with the SAME idempotency key as the live attempt (`KeyedOfflineQueue`
  of MOBILE2B), dated now (or the server would date it the day it is finally sent), is shown in the list with "Waiting to send", and
  `diary_saved_offline` is spoken. `diary_sent` is spoken if the diary is open when the queue sends it. Waiting entries live in memory
  (`pendingSpraysProvider`): after an app restart the queue still sends them but the list cannot show them as waiting (the queue has no list
  API). A retry after an error reuses the key of that entry.
- **Dates:** "today" sends no `sprayed_at` (the server clock decides); yesterday / other day send noon of that day in UTC. Dates are
  written as "12 May" and spoken as "twelve May" (word lists in `strings.json`: `diary_month_words`, `diary_number_words`, `diary_weekday_words`,
  `field_weekday_short`, one comma separated list per language, so a language is data only).
- **Crop ids:** the server writes `Apple`, the app's names and pictures are keyed `apple`. My screens look names and pictures up in lower case and send
  the id as the server listed it (contract finding 2 is not fixed in `AppResources`).
- **Field speech:** `field_intro`, then the server's `spoken` (audio if sent, else phone TTS). `field_stale` / `field_no_data` are added only when the server text
  does not already say them (it does: the server prepends them). An answer read from the phone's memory says only `field_stale` and shows a banner: its old
  weather and risks are not read out as if they were today's. "Old" = the server's `stale` flag or a cached answer; I do not compare `as_of` with the phone's date
  (the demo server clock is May 2026, so everything would look old). Numbers are on the screen small and are never spoken.
- **Alerts:** opening an alert (list or push) marks it read, then reloads the list and the bell badge. Newest first (sorted again on the phone). The
  scan button loads the scan and shows it through the normal advice / expert screens; only `ok`, `needs_expert`, `no_approved_data`, `not_a_disease` have a
  result screen, others say `error_try_again`.
- **Push:** `handleNotificationTap({alert_id, kind, level})` opens `/alerts/detail?id=` (the list when there is no id). A tap before login or before the
  router exists waits. The backend also sends `scan_id` in the data; the app does not use it from the push, it goes through the alert's `scan_id` and the green
  arrow on the detail screen. A message while the app is open says `alert_new` + `alert_open` and refreshes the badge. The permission is asked once, at the
  first Home visit after a build with a real plugin (`notification_permission` spoken first, then the system question, `permission_denied_notifications` if
  refused); with the default port nothing is asked or said. After logout only the "registered token" is forgotten (nothing can be sent without a login):
  the next login registers the token again, the server then moves it to that farmer.
- **Mock scenarios added** (additive): `MockApiClient.fieldOverride`, `alertItems`, read state for alerts, `MockData.fieldStale()` / `fieldNoData()`,
  `getScan('scan-alert')`, alert 1 has `scan_id`, `createSprayLog` returns warnings by typed name (Mancozeb: yellow `proposed_ban`; Miravis / fenpropathrin: red
  `off_label`; an unknown name: yellow `PRODUCT_NOT_RECOGNISED`) and a `spoken` shaped like the real one.

## Decisions and doubts (owner or team to review)
- **`diary_saved_offline` instead of `offline_saved`:** the brief said to speak `offline_saved`, but its text says "your photo is saved". A spray note would be
  announced as a photo, so I added `diary_saved_offline` ("Your spray note is saved and will be sent later"). Switch back by one id if a generic text is wanted.
- **Hindi (all drafts, native review):** "कल" means both yesterday and tomorrow: the button says "बीता कल" and the prompt "बीता हुआ कल"; "नम" (damp air), "अच्छा"
  (pleasant) and "थोड़ी गीली" for the tiles; weekday names in full in the day chooser, abbreviated ("सोम") in the forecast strip; the severity words "सावधान" / "गंभीर"
  are MOBILE1's. Brand names (Score) are Latin script inside Hindi speech: check how the phone's Hindi voice reads them.
- **Words for numbers (tiles):** limits (cold below 5 C, cool below 15, pleasant below 25, warm below 32; no rain below 1 mm, light below 10; air dry below 50 %,
  damp from 80 %; leaves wet from 240 min; soil dry below 15 %, wet from 40 %) copy the server's own bands where they exist, the rest are my guesses: agronomist to
  check. They only choose a word; the server's rules decide risks.
- **Order on My field:** risks first, then tiles, then the forecast: with the caption box and the speaker row, a 640 dp phone shows little more than one block.
- **Save speaks nothing while waiting**, only a spinner on the tick. If the server is slow farmers get no sound for a few seconds (consider `please_wait` after 2 s).
- **Alerts "kind" has no picture of its own**, only the bell plus the level picture. Candidates: umbrella (wash-off), clock (waiting period), refresh (rotation).
- **Fixed prompts are long for the confirm screen** (name, question, tick, cross = 4 sentences). Field test whether the cross sentence can go.
- The diary's list shows at most 50 entries (the API limit used) and has no paging.

## Contract requests (nothing in other agents' files was edited for these)
1. (Done by MOBILE2B while I worked: `ScanFlowNotifier.showResult(ScanOut)`; `features/alerts/open_scan.dart` calls it. My first version set the notifier state from outside.)
2. **`AppResources.cropName/cropGroup` case-insensitive** (contract finding 2): then the lower-casing in my diary widgets can go.
3. **Backend: `SprayLogOut.spoken` reads only the first warning.** The app reads the others itself; if the server ever speaks all of them the app needs no change.
4. Backend `GET /v1/spray-logs` returns no `free_text` and no `advice_id`-resolved name for entries without product: names come from `product_name` (fine today).

## Switching real push on (FCM). UNTESTED: none of this could be run here (no Android SDK, no Firebase project, no phone)
The app side is ready: only two classes and a few build files are missing.
1. `cd mobile && flutter pub add firebase_core firebase_messaging` (use the versions `pub` picks for Flutter 3.47; never `pub upgrade`).
2. Firebase console: create a project; add an Android app with package `com.softsuave.farmtrack` (`android/app/build.gradle.kts`) and an iOS app with the bundle id from
   `ios/Runner.xcodeproj`. Download `google-services.json` into `mobile/android/app/` and `GoogleService-Info.plist` into `mobile/ios/Runner/` (add it to the Runner target in Xcode).
   Do not commit service-account JSON; the backend (`PUSH_PROVIDER=fcm`, `FCM_CREDENTIALS_FILE`) has its own credentials.
3. Android Gradle: in `android/settings.gradle.kts` `plugins { id("com.google.gms.google-services") version "<current 4.x>" apply false }`; in `android/app/build.gradle.kts`
   `plugins { id("com.google.gms.google-services") }`. In `AndroidManifest.xml` add `<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>` (Android 13 and newer).
4. iOS: Xcode capabilities "Push Notifications" and "Background Modes > Remote notifications"; in the Apple developer account create an APNs Auth Key (.p8), upload it in
   Firebase console > Project settings > Cloud Messaging > Apple app configuration. Push does not work in the iOS simulator.
5. `main.dart`: `await Firebase.initializeApp();` before `runApp`. (The backend sends `notification` + `data`, so the system shows the message when the app is in the
   background and no background handler is needed. If data-only messages are ever sent, add a top-level `FirebaseMessaging.onBackgroundMessage` handler.) On iOS call
   `FirebaseMessaging.instance.setForegroundNotificationPresentationOptions(alert: false, badge: false, sound: false)`: the app speaks `alert_new` itself.
6. Write the two classes (suggested file `lib/core/push/fcm_push.dart`, the only file that imports firebase):
   - `FcmPushTokenSource implements PushTokenSource`: `getToken` = `FirebaseMessaging.instance.getToken()` (on iOS it needs the APNs token: catch the error and return null,
     the `onTokenRefresh` event follows); `onTokenRefresh` = `FirebaseMessaging.instance.onTokenRefresh`; `onForegroundMessage` = `FirebaseMessaging.onMessage.map((m) => m.data)`;
     `onNotificationTap` = `FirebaseMessaging.onMessageOpenedApp.map((m) => m.data)`; `getInitialMessage` = `(await FirebaseMessaging.instance.getInitialMessage())?.data`.
   - `FcmNotificationPermissionPort implements NotificationPermissionPort`: `status` maps `getNotificationSettings().authorizationStatus` (authorized/provisional = granted,
     denied = denied, notDetermined = notDetermined); `request` = `requestPermission(alert: true, badge: true, sound: true)` mapped the same way (Android below 13 reports authorized).
7. Wire them in `main.dart`'s `ProviderContainer(overrides: [...])`: `pushTokenSourceProvider.overrideWithValue(FcmPushTokenSource())`,
   `notificationPermissionPortProvider.overrideWithValue(FcmNotificationPermissionPort())`.
8. Check on a real phone, in this order: first Home visit speaks `notification_permission` and shows the system question; `POST /v1/devices` arrives at the backend with the token;
   a test message from the Firebase console with data `{alert_id: <real id>, kind: rain_washoff, level: red}` opens that alert when tapped (app in the background, app closed) and
   speaks `alert_new` + `alert_open` when the app is open; logout then login as another farmer moves the token (`device.farmer_id` changes).

## Not verified (needs a phone or an Android SDK)
Everything audible (phone TTS in Hindi, bundled / server audio for the diary and field texts, the order of speech on real engines); touch behaviour with real thumbs
(the 64 dp minimum is tested in widget tests only); the text field with a real keyboard (the screen scrolls, but a 320x568 phone with a keyboard open shows very little);
push on Android and iOS; the offline queue sending a spray entry in the background; how the screens look with the real fonts (a temporary screenshot check with Nirmala UI
and the Material icon font looked right on 360x640; deleted afterwards). Test icons with real farmers: bell, clock, history arrow, calendar, thermometer, umbrella and
the flask for medicine are Material stock icons.
