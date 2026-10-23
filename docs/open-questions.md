# FarmTrack MVP: open questions and decisions to review

Written 19 Oct 2026 at the end of the autonomous build. You were away, so every doubt below was settled by me with the
safest or most conventional option; nothing was left half done. Go through A first (needs you), then B (needs an
expert), then veto anything in D. The per-agent working notes with the full detail are in `notes/` (reference only,
delete the folder when you no longer need it).

## A. Decided by you on 19 Oct 2026, and what is still open
**Decided (already in the code):**
- **No callback.** Farmers photograph a leaf and get the answer at once (disease and what to do); the case is saved in the
  database. No expert phone call, no in-app expert reply. The "not sure" texts say: do not spray yet, take another photo or
  show the plant to a local expert, with no promise that anyone answers. The expert queue and the admin pages remain as an
  internal review list; the "save this case" button on the result screen only records it.
- **No SMS and no OTP for the MVP.** Login is user name + password and is always required (light security on purpose;
  OTP code is still in the backend behind `OTP_LOGIN_ENABLED`). Demo accounts `f001` to `f050`, password `farm1234`
  (`DEMO_PASSWORD`). Real farmers get their login from the admin site (Set login / Create farmer). Decide later: SMS gateway,
  who creates accounts, whether a PIN or a printed card would suit farmers better than typing a password, "forgot password".
- **Automatic medicine advice for every disease with chemical control** (`RULES_AUTO_ADVICE_DISEASES=*`). The evidence says
  the models cannot tell apple scab, Alternaria and Marssonina apart, so a wrong disease can give a wrong medicine; the
  hard guards stay (expert-review, no-cure, low confidence below 0.65, unknown disease, wrong crop, no approved data for the
  crop all go to the safe "do not spray yet" answer). Set the variable empty to go back to scab only.
- **No seasons during development** (22 Oct 2026). A disease is advised on any date: the rules no longer reject scab outside
  its season or leaf spots before 1 June, and the growth stage no longer excludes products (setting `RULES_SEASON_CHECK`,
  default `false`; `true` brings the production behaviour back). Before real use, decide whether to switch it on again.
  What still goes to the safe "do not spray yet" answer: Root rot, Brown spot and Black rot (flagged "needs an expert" in
  the disease list), the combined "Scab & Rust" class, low confidence, and crops without approved medicines.
- **Android only for now**, iOS later. The camera screen also has a gallery button (up to 4 photos per scan).

**Still open:**
1. **Photo retention** is 365 days, then deleted (the scan result stays). Photos can show people and houses. There is no
   "delete my data" route yet. Decide the retention period and whether a deletion route is required.
2. **Watering/irrigation** is not in the MVP (as agreed). Confirm it stays out.
3. **Admin site** is server-rendered pages (login with an admin key, CSRF, no JavaScript), not a React/Flutter web app.
   It covers: expert queue, expert requests, release advice to a farmer, product on/off switch, farmers, alerts, audit,
   demo clock. Say if you want a richer UI.
4. **Languages:** Hindi and English only. A third language is data only (strings, prompts, glossary, audio) but each
   needs a native review.
5. **Hosting and operations:** run ONE uvicorn worker (scheduler and in-memory rate limits assume it); PostgreSQL with
   pgvector; a reverse proxy with `--proxy-headers`; who owns backups and the admin key.
6. **Weather licence:** Open-Meteo's free endpoint and IMD data are non-commercial; production needs a paid plan or
    another source. Zoho field names (`Farmer_ID`, `Advisory` subform) and the client's IoT platform are assumptions.
7. **OpenAI model:** `gpt-4o-mini` shuts down 14 Jan 2027. The name is in `.env` (`OPENAI_MODEL`), switch to `gpt-6-luna`
    and rerun `data/model_test/` before then. The key in `.env` was never read or printed by me.
8. **Phones:** **Android first, as you asked; iOS was deliberately not touched** (the project folder exists, nothing was
    checked or built for it; Flutter 3.47 needs iOS 15, so an iPhone 6s/7 only works after updating to iOS 15). Android
    minSdk is 24 (Android 7); you said Android 9+, so older Android is a bonus, not a promise.

## B. Needs an expert
**Native Hindi speaker (everything Hindi is machine-drafted):** `voice/prompts.json` (spoken prompts), interface words in
`mobile/assets/l10n/strings.json`, advice phrases and numbers (`app/advice`), rules messages, alert texts, `services/texts.py`,
ask suggestions, diary words ("बीता कल" for yesterday because "कल" also means tomorrow), severity words ("Serious" for red),
crop names, button picture names ("green tick", "gear"). Also: **listening test of the generated voices** (hi-IN and en-IN
Neural2 are unverified defaults; Hindi availability and TTS prices were not checked) and whether farmers understand the
Material icons used for buttons.

**Agronomist:**
- Two different pesticides logged on one day give no warning (the rules cannot tell one tank from two). Add a soft
  "if mixed in one tank, do not" warning?
- Ziram 27 % SC rows have no waiting period in the data, the 80 % WP row has 21 days. Confirm.
- Doses for tomato/potato are per hectare; farmers think in bigha/kanal or per tank. Conversion is not done.
- Wording of the general protective measures (remove fallen leaves, watch the plants) and the Hindi crop-name table.
- The Marssonina rule text mentions "6 h leaf wetness on rain days"; the data scripts and the engine do not apply it.
- Demo scenarios S6, S7, S8, S10 disagree with the engine on purpose (policy, "never repeat the same chemical", no cure for
  virus, 97 vs 73 days). The engine is right under the rules; fix the scenario facts.
- Which crops beyond apple get approved lists (client counts and lists are still missing; "all HP crops" has data for apple only).

**Hindi crop names** beyond the demo crops and the voice list (banana, brinjal, okra, custard apple ...) are my draft
(`backend/app/advice/crop_names.py`, one table for scan cards and advice text); "beans" is `बीन्स` in advice sentences but
`फलियों` in the voice prompt.

**Client:** real field photos (the quality thresholds and the crop prior were tuned on 28 web photos), Zoho org details,
the IoT platform, a few farmers' real phones for a field test.

## C. Not tested here (no device, no Docker, no keys)
- **Android and iOS builds** (no SDK on this PC): no APK, camera, real Hindi TTS, audio playback, secure storage, TalkBack,
  push. 600+ widget tests, analyze and format are clean, and the real client was run against the real backend (31 calls).
- **Docker image never built; PostgreSQL/pgvector never run** (SQLite only). Run `pytest tests/services/test_migrations.py`
  and the pgvector store tests (`PG_TEST_URL`) once, then build the image.
- **Never called for real:** OpenAI (LLM and embeddings), Google TTS, Zoho, FCM, SMS, Open-Meteo.
- **Vision models:** the real crop and disease models run on a laptop CPU in a smoke test (apple named 28/28 with the farmer's
  crop as prior; scab/Alternaria/Marssonina still not separable, so only scab gets automatic advice). The Docker image has no
  ML libraries (stub vision) and the on-device model is not converted (stub). Setting `CROP_ID_PROVIDER=model` needs a torch image.
- **FCM push** needs a Firebase project, `google-services.json`, APNs key (steps in `docs/design-notes/mobile2a.md`).
- Load and performance; a 3 GB Android 9 phone; install size (build with `--split-per-abi`).

## D. Review wave (stopped early at your request)
A correctness/safety review and a security review of the backend ran in parallel and were stopped before they wrote their
final reports; what they had already fixed is in the code with tests (`tests/security/test_hardening.py`,
`tests/api/test_security_hardening_api.py`, `tests/security/test_environment_and_clock.py`, `tests/integrations/test_dotenv_settings.py`):
- text a farmer types into the medicine field could end up in a warning, then in the synthesised audio served publicly at
  `/audio/<hash>.mp3` (a name or phone number would have been published): typed text is now replaced in spoken warnings;
- login-code guessing: parallel guesses can no longer exceed the attempt cap, wrong codes are limited per phone over all of
  its code requests, the admin key limit applies before the comparison;
- `ENV=production`/`prod`-like spellings all count as production, an unknown `ENV` refuses to start instead of running with
  development defaults, the Docker image defaults to prod, production refuses a fixed demo clock;
- bounds: long typed names and app versions, audio file names with a trailing newline, error bodies never echo the input,
  image decoding concurrency, in-memory throttle/cache sizes, log-line injection;
- `ZOHO_*` and `OPEN_METEO_API_KEY` now also work from the `.env` file.
**Not done (checklist items that never ran):** a full JWT/CSRF/admin-XSS pass, a dependency vulnerability audit, a data-deletion
route, prompt-injection tests beyond the ask validator, resource limits on the admin lists. Run a proper security review
before real farmers use it.

## E. Decisions I made for you (veto any)
- **Safety design:** rules decide, the LLM only words it; a draft that deviates is replaced by a fixed template. No approved
  data = no medicine. A healthy result below 0.65 confidence goes to an expert (never "your plant is healthy" on a guess).
- **Crop identification:** two detectors, farmer's own crops as a prior (others at 0.15), ask with tick/cross when unsure;
  the on-device guess is ignored by the server.
- **Offline:** photos and spray entries queue on the phone and are sent when the network returns (safe retries through an
  `Idempotency-Key`; no duplicates). Expert requests are not queued. Items older than 7 days are dropped.
- **Login:** OTP + rotating refresh tokens, one session per device id, replay revokes that device. Rate limits are my numbers
  (OTP 3 per 15 min per phone, scans 30 and questions 20 per 10 min per farmer).
- **Spray diary:** the "I sprayed" tick records the first product of the advice (the one read aloud); typed names are matched
  to the catalogue by exact identity only, ambiguous or unknown names are saved as typed with a soft warning.
- **Voice:** fixed prompts are bundled audio when generated, else server audio, else the phone's voice. Spoken text never
  contains digits or personal data (audio files are public, addressed by a hash of the text).
- **Admin disables a product** and the rules fail closed if that switch cannot be read.
- **Demo clock** is frozen at 12 May 2026 (apple season); a strip on every screen says so. Set `DEMO_CLOCK` empty for real time.
- **Contract:** `contracts/openapi.json` is the API truth; changes stay additive.
- **Test build talks plain http to a PC** on the same Wi-Fi (`usesCleartextTraffic="true"` in the Android manifest, address
  typed in the app: login screen, "Server"). A deployed server needs https; then remove that attribute.
- Tools installed on this PC as a side effect: Flutter (`C:\siva\tools\flutter`), JDK 17 and the Android SDK
  (`C:\siva\tools\jdk17`, `C:\siva\tools\android-sdk`; the Android SDK licence was accepted for you on 19 Oct 2026).

## F. Known limits and tech debt
- Rate limits and idempotency locks live in process memory (one worker); use Redis before scaling out.
- Scan photos can be added to an existing scan from the API but the app sends all photos with the first upload.
- Waiting diary entries show as waiting only until the app restarts (they are still sent).
- Embedding dimension change (hash 512 to OpenAI 1536) needs `DROP TABLE kb_notes`; the Ask relevance threshold (0.25) was
  calibrated with the hash embedder and must be re-calibrated with real embeddings.
- A refresh token replayed within seconds (lost answer on a bad network) revokes that device's sessions; the app now sends
  a per-install device id so only that phone is affected.
