# FarmTrack MVP: Plan

**Last updated:** 19 Oct 2026 (re-baselined after the scope changes: all Himachal crops, automatic crop detection, voice guidance, target phones)
**Status:** Plan for team review. **The earlier "about 6 weeks" estimate predates these changes and must be re-estimated by the team** (see §7).
**Build (19 Oct 2026):** the MVP described here was built autonomously, Android first (`backend/`, `mobile/`). What exists, what is untested and what needs the owner or an expert is in `docs/open-questions.md`; work packages in §7 are done in code except the items listed there (SMS gateway, FCM, real providers, device and Docker/Postgres verification, native Hindi review).
**Inputs:** `docs/requirements.md`; `docs/research/cv-models.md`; `docs/research/agronomy-data.md`; `data/README.md`; `data/model_test/review_2026-10-19.md`

---

## 1. Goal and decisions

**The product (user, 19 Oct 2026):** a bespoke, very simple, **voice-guided** app for farmers in **all of Himachal Pradesh**, most of whom are not educated and know only farming. The farmer **opens the app, which speaks to them**, takes a photo, and the **system itself identifies the crop** (the farmer never says "this is apple"). It then finds the disease, gives the solution and the **medicine from the approved list only**, personalised by the farmer's spray history (Zoho) and the weather, and later the **watering** advice.

**MVP demo:** one end-to-end story: the app speaks the steps, the farmer photographs a leaf, the app names the crop and says it aloud, gives approved advice read aloud in Hindi or English, the farmer ticks "sprayed", the record lands in (mock) Zoho, and the system later pushes an alert on its own (rain washed the spray off, or weather turns risky).

### Decisions

| Topic | Decision | Date |
|---|---|---|
| **Crop scope** | **All Himachal crops (real product); no crop picker**: the system identifies the crop. The MVP covers a smaller set of crops (to be chosen; needs the client's crop counts). Apple is the deep crop because the client's real data is apple. | 19 Oct 2026 (later) |
| **Voice** | The app **speaks every step**. **One-way for now** (app speaks, does not listen). **Generated voice** (not human-recorded), **checked by a native speaker**. **Hindi and English now**; many Indian languages later, as a data task (no code change). | 19 Oct 2026 (later) |
| **Target phones** | Android **9 or newer** and iPhone "newer than 6", from about 5 years old to the latest; **3 to 6 GB RAM, 32 to 128 GB storage** (user). See §4.10. | 19 Oct 2026 (later) |
| Mobile | **Flutter** | 19 Oct 2026 |
| Backend | **Python (FastAPI) + PostgreSQL/pgvector**, push by FCM, admin web panel (see §3) | 19 Oct 2026 |
| Zoho and IoT | **Mocked**, shaped exactly like the real data, behind adapters | 19 Oct 2026 |
| LLM | **OpenAI `gpt-4o-mini`** (user decision), name in `.env`. **⚠ It shuts down on 14 Jan 2027** (OpenAI notice of 14 Oct 2026); OpenAI recommends `gpt-6-luna`. Behind a provider interface. **Role: explain, personalise, answer questions. NOT the diagnostic safety net, symptom reader or photo-quality gate** (§4.7). | 19 Oct 2026 |
| Watering / irrigation | In the full product; **deferred for the MVP** (to be confirmed) | 19 Oct 2026 |
| Model training | **None in the MVP; set aside** (user decision). Pretrained models only. Client photos are a test set only. | 19 Oct 2026 |
| Demo data | Farmers, Zoho records, sprays, sensors, advisory notes are **fabricated but grounded in real sources**; **leaf images are never generated** (real public photos only). Built and validated (§5). | 19 Oct 2026 |

---

## 2. Scope

### In the MVP
| # | Capability | Notes |
|---|---|---|
| 1 | **Voice guidance on every screen** (Hindi + English): speech starts automatically, replay button, picture buttons, one step per screen, almost no typing | §4.9 |
| 2 | **Phone-number login** (mocked OTP in the demo) and spoken language choice at first launch | Real SMS OTP later |
| 3 | **Home screen with a few big picture buttons**: Scan crop, My field, Spray diary, Ask expert | Icons, minimal text |
| 4 | **Scan:** camera guidance spoken, photo quality check, **automatic crop identification**, disease detection with a "not sure" answer | §4.8, §4.3 |
| 5 | **Crop confirmation:** the app says "This looks like apple", always shows the detected crop with a "wrong crop?" link, one-tap confirmation only when crop confidence is low | Safeguard |
| 6 | **Advice card** (approved product, dose, timing, waiting period, safety note, severity colours) **and a spoken version** of it | Rules decide, LLM phrases |
| 7 | **Personalised by spray history** (no repeat of the same chemical, FRAC/IRAC rotation, season limits) from mock Zoho | |
| 8 | **Weather-aware**: rain-wash rule, "spray now / wait", disease-risk | Open-Meteo in dev |
| 9 | **Automatic alerts** (push, spoken when opened): scab and Marssonina/Alternaria weather, late blight, rain wash-off, waiting-period reminders | Scheduler, same rules |
| 10 | **Spray diary with checkboxes** ("Sprayed ✔"), date and weather filled automatically | Writes to mock Zoho |
| 11 | **My field**: sensor readings, 7-day forecast, risk badges (no irrigation advice) | |
| 12 | **Ask expert**: text/chat over approved documents (RAG) | Voice questions are phase 2 |
| 13 | **Agronomist review queue** and **admin panel** (product list, thresholds, alerts, farmer view) | Basic |
| 14 | **Offline**: on-device crop and disease check, cached advice cards, queued photos and diary entries, **fixed voice prompts work offline** | Full advice needs the network |
| 15 | **Safety guards**: approved list only, banned and off-label checks, waiting period, "consult expert" when there is no approved data | Hard rules |

### Not in the MVP (phase 2 or later)
Watering advice · model training · two-way voice (voice commands, asking by voice) · languages beyond Hindi and English (Pahari and other regional) · real Zoho, real IoT, real SMS OTP, WhatsApp · payments · any accuracy guarantee (§4.4).

---

## 3. Architecture

```
Flutter app (Android 9+, iPhone 6s+ practically)
 ├─ Voice layer: prompt catalogue (text per language) + bundled audio files, replay/slow controls
 ├─ Camera → photo quality check
 ├─ On-device models (offline): crop identification + disease check (MobileNet-class, ~3 MB int8)
 ├─ Offline store: photos, diary entries, cached advice cards and their audio
 └─ REST API ───────────────────────────────────────────────────┐
                                                                 ▼
Backend (Python, FastAPI)                               Admin web (React or Flutter web)
 ├─ Crop identification service (with confidence)       review queue, product list, thresholds, alerts
 ├─ Disease services: per-crop models, server second opinion, optional Kindwise
 ├─ Rules engine (deterministic): approved list per crop, safety, rotation, rain, stage, weather risk
 ├─ Knowledge (RAG, pgvector): approved documents, disease notes
 ├─ LLM service (provider interface): writes advice + a separate SPOKEN version → validator
 ├─ Voice service: text-to-speech for the spoken advice, cached by text; number/unit-to-words step
 ├─ Alert scheduler (hourly)
 ├─ Adapters: Zoho (mock|real), IoT (mock|real), Weather (Open-Meteo|IMD|Visual Crossing)
 └─ PostgreSQL + pgvector; object storage for photos and audio
Push: Firebase Cloud Messaging
Offline tools (not in the app): voice-prompt generation + native-speaker review sheet
```

**Why a backend:** secrets (OpenAI, Zoho) cannot live in the app; the approved list and rules must be updated centrally without an app update; Zoho, sensors and weather are server jobs; alerts need a server; the review queue and admin need shared data. The only thing on the phone is the small model and the bundled prompts.

**Design rules:**
- **Rules decide; the LLM only explains.** Product, dose and timing come from the rules engine and the product master. The LLM gets only the rule output and retrieved notes, returns structured JSON, and a validator checks it (product exists in the master, dose matches). If it does not match, a safe template is used.
- **The approved list is enforced in code** (allow-list per crop), never by the LLM or by RAG alone.
- **Zoho history is read with normal queries and computed in code** (rotation, counts, dates, rain since last spray). RAG is for free-text notes only.
- **No medicine advice for a crop with no approved data.**
- **Adapters and a provider interface** keep Zoho, sensors, weather and the LLM swappable.

---

## 4. Vision, voice and device approach

### 4.1 The finding that shapes everything
No off-the-shelf model reaches 90–95% on field photos. Public models report 95–99% on lab images (PlantVillage) but drop to about 15–40% on real field photos (Mohanty 2016, PlantDoc paper, `neghani` 16% on 25 field photos). Even Plantix advertises about 73–74% on field images. Details: `docs/research/cv-models.md`.

### 4.2 Models (pretrained, no training)
| Layer | Model | Notes |
|---|---|---|
| On-device | `neghani/plantvillage-mobilenetv2`: 38 classes, 14 crops; convert to int8 TFLite (~3 MB) | Apache-2.0; no Alternaria or Marssonina class |
| Server, apple | `ixrbhii/apple-disease-convnext`: 8 apple classes incl. Marssonina and Alternaria (~99 MB) | CC-BY-4.0; the only public model with those classes |
| Server, other crops | `ixrbhii/multicrop-disease-models`: 42 crops, plus 2 crop-detector models | Includes apple, pear, apricot, cherry, peach, walnut, pomegranate, citrus, mango, strawberry, tomato, potato, maize, rice, cucumber, grape; **not** wheat, pea, cauliflower, cabbage, capsicum, ginger, kiwi, plum, barley, beans |
| Optional | Kindwise crop.health API (about 23 crops); €0.05 down to €0.01 per call | Not tested yet |
Runtime in Flutter: `flutter_litert` (active) or `tflite_flutter`.

### 4.3 First test results and what they mean (19 Oct 2026)
Both models were run on 23 leaf photos (web images, unconfirmed labels; **directional only**). Full review: `data/model_test/review_2026-10-19.md`.
- **Model A (on-device):** 0/23 over all 38 classes (17 confidently wrong); with apple classes only it calls Marssonina leaves "scab" at 0.6 to 1.0 confidence.
- **Model B (server):** scab 4/4; Alternaria 1/8; Marssonina 2/11 exact (6/11 if "Brown spot" is Marssonina). It calls 5 of 8 Alternaria and 5 of 11 Marssonina leaves "scab" at about 0.9.
- **Confidence did not separate right from wrong** (0.85 vs 0.86), and **A and B agreeing did not help** (right only 3 of 10 when they agreed).
- **ChatGPT (gpt-4o-mini) on the same photos:** the answer depends on the prompt (no menu: "scab" for 22 of 23; with a menu: "Marssonina" for 15 of 23), probabilities are templated, symptom descriptions echo the prompt, and it marks every photo usable. With the vision model's top 3 as a hint: 13/23 (fixed 3, broke 1: noise). Cost: **$0.17 for 84 requests, about $0.002 per photo** (gpt-4o-mini counts about 12,900 input tokens per photo).
- **So:** confidence cut-offs and "two models disagree" are **not a reliable safety net**. Use: **auto-advice only for apple scab**; the **date and growth stage as a main signal** (scab is spring; Marssonina and Alternaria start in June); a **leaf-spot-family protectant protocol** if the client's agronomist approves; the **agronomist queue** for Alternaria and Marssonina. Today **only scab is machine-recognised with any reliability.** Phase-2 fine-tuning on confirmed Alternaria and Marssonina photos is the real fix.

### 4.4 What we tell the client
The MVP shows the **workflow**. Accuracy on Himachal field photos will be low until we have their confirmed field photos (a few hundred per disease) and fine-tune. Until then the approved-list rules, the date check and the expert queue keep wrong advice from reaching farmers.

### 4.5 Class coverage gaps
Marssonina and Alternaria exist only in the server apple model; PlantVillage's cedar rust does not occur on apple in India (low-prior); no public model covers apple mites or woolly aphid. Several diseases have no Indian label recommendation (tomato leaf mold and target spot, grape black rot and esca, strawberry leaf scorch, maize gray leaf spot): the card says "consult your expert". Pea, cauliflower, cabbage, capsicum, wheat, ginger and others have **no photo model at all** (§4.8).

### 4.6 The client's photos and training
About 10 photos per leaf or disease (50 to 100 in total; **unconfirmed whether per disease or the same leaf**). Use first as a **test set**, split by leaf. Training is deferred: 23 test leaf photos with 1 reliable scab leaf, web images of unknown licence and unconfirmed labels are not a basis for training. **Phase 2** needs a few hundred agronomist-confirmed field photos per disease, taken in season (**March to August 2027**). Options, cheapest first: (1) no training (the MVP); (2) few-shot matching against confirmed examples; (3) light fine-tune of the last layers; (4) full fine-tune and compress for the phone. Compute is not the problem: a free Colab T4 or an RTX 3060 is enough (minutes to hours per run); data is. Details: `data/model_test/README.md` section 7.

### 4.7 The LLM's role
Not useless: it is the part that scales across crops (new crop = new approved documents, no new training), writes plain Hindi or English, personalises with history, and answers questions. What the test did **not** support: using it as the diagnostic safety net, a symptom reader or a photo-quality gate. A possible next test: `gpt-6-luna` (set `OPENAI_MODEL` in `.env`).

### 4.8 All Himachal crops and automatic crop detection
- **Why it is now the most critical step:** a wrong crop means a wrong disease list and a wrong medicine list (a medicine approved for apple may not be approved for another crop). Without any crop restriction, model A got 0/23.
- **Flow:** photo → quality check → **crop identification (with confidence)** → that crop's disease model, if one exists → that crop's rules and approved list → (watering, later) → LLM writes the advice → spoken. Unsure about the crop, or no approved data for it → expert.
- **Safeguards:** the farmer's **Zoho crops as a strong prior**; always show and speak the detected crop with a "wrong crop?" link; one-tap confirmation only when crop confidence is low; no medicine advice for a crop without approved data.
- **Crop groups in Himachal:** fruits (apple, stone fruits, pear, kiwi, pomegranate, walnut; mango, citrus and litchi in the low hills), vegetables (tomato, potato, pea, cauliflower, cabbage, capsicum, beans, ginger), cereals (maize, wheat, paddy, barley).
- **Approved-list sources:** HP Horticulture Dept + UHF Nauni publish yearly spray schedules for apple, mango, citrus, litchi and stone fruits (eUdyan; a 2023 mango and citrus PDF and a 2022 stone-fruit PDF exist, not yet read). **Not yet found:** the CSKHPKV Palampur package of practices for vegetables and cereals.
- **Not yet tested:** crop identification. Next test: a multi-crop photo set (PlantDoc, 13 species, CC-BY-4.0, plus the client's photos) run through the `ixrbhii` crop detector and ChatGPT vision.
- **Coverage today (approved-list data):** apple deep; tomato, potato, maize, grape light.

### 4.9 Voice guidance
**Decision:** generated voice, native-speaker review, Hindi + English now, one-way, extensible.
- **Two kinds of speech.** (1) **Fixed prompts** (the app's own instructions, a few dozen short sentences; count fixed during design): audio generated **once** offline, reviewed by a native speaker, **bundled in the app**; plays instantly, works offline, same on every phone. (2) **Dynamic advice** (differs every time): the backend writes a separate **spoken version** (short sentences, numbers and units written as words) and the **backend generates the audio** (cached by text), so the voice is consistent and does not depend on the language pack installed on an old phone. If offline: the phone's built-in voice via `flutter_tts` if the language is installed, otherwise the fixed prompts plus a picture result.
- **Screen design for non-readers:** one step per screen; speech starts automatically; big picture buttons (camera, green tick, plus); replay button always in the same place; highlight the button being spoken about; vibration and a sound on success; almost no typing; first-run language choice spoken in both languages with buttons labelled in each script; the detected crop is spoken and confirmed with a tick; on-screen captions as backup in noisy fields. **Test with real farmers early.**
- **Adding a language** = translate the text, native-speaker review, generate and review the audio, check a voice exists.
- **Engines (checked 19 Oct 2026):** `flutter_tts` 4.2.5 (MIT; Android, iOS, web, Windows; can check whether a language is installed). **Google Cloud TTS:** 30 Chirp 3 HD en-IN voices listed; Hindi in Chirp 3 HD per the March 2025 notes (Hindi rows not retrieved); **Chirp 3 HD has no SSML and no speaking-rate or pitch control**, so slower speech needs a Neural2/WaveNet/Standard voice (SSML listed; Hindi availability not checked) or audio time-stretching; **prices not verified** (the pricing page did not load). AI4Bharat Indic Parler-TTS: open source, Apache 2.0, about 0.9B parameters, 18 official Indic languages plus English (Punjabi unofficial), server use, access requires login; its card recommends a newer "Indic-Speak" (not checked). Bhashini (Government of India): free APIs, language count conflicting, docs not verified. OpenAI `gpt-4o-mini-tts` retires 6 Jan 2027: do not build on it. **No source found lists Pahari dialects (Kangri, Mandeali, Kullvi, others);** for those a recorded human voice is the realistic route, later.
- **Next step:** a listening test of 2 to 3 candidate voices on the same Hindi and English prompts, judged by the native speaker, before generating everything.
- **Risks:** machine mispronunciation of numbers, units and chemical names (needs the number-to-words step and a reviewed Hindi glossary); noisy fields; one voice for all hill regions.
- **Phase 2:** two-way voice (speech to text) needs Hindi recognition tested on rural accents and noise.

### 4.10 Target phones and technical limits
- **Flutter (docs, "as of Flutter 3.47"): Android 24 to 37 and iOS 15 to 27 supported.** Android 9 is API 28, so **Android 9+ is fine**. **iOS 15 minimum means iPhone 6 cannot be supported** (it stops at iOS 12; from my knowledge, not checked here); **iPhone 6s, SE (1st generation), 7 and newer can** (iOS 15, from my knowledge). Check whether farmers use iPhones at all.
- **3 to 6 GB RAM:** fine for the small on-device model (about 3 MB). The 99 MB models stay on the server. **32 GB storage:** keep the install small (target to be set in design); bundled audio is small (my estimate: a few dozen sentences in two languages at low bitrate, a couple of MB).
- **Weak networks:** offline queue, compressed photos, on-device first answer, bundled prompts.
- **Test on real low-end hardware** (a 3 GB RAM, Android 9 phone) in the first sprint, not at the end.

---

## 5. Data (built and validated 19 Oct 2026, in `FarmTrack/data/`)

89 validation checks pass; rebuild is byte-for-byte reproducible. Real vs fabricated is spelled out in `data/README.md`.
- **Real:** HP 2026 apple doses, waiting periods and stages (checked against the rendered PDF); the official HP **evaluated-brand table** (103 brands with manufacturer); CIB&RC, NIPHM and TNAU doses for tomato, potato, maize and grape; FRAC/IRAC codes; weather-disease rules; **real hourly 2026 weather** for 12 stations (Open-Meteo, non-commercial).
- **Simulated:** sensor feed. **Fabricated:** 50 farmers (invalid phone numbers on purpose), 444 mock Zoho Advisory rows in the client's exact columns (deliberately messy), 11 demo scenarios anchored to real weather events.
- **Counts:** 97 products (68 apple), 50 disease classes, 186 advisory notes (156 with draft Hindi), 40 rules.
- **Estimates or drafts:** stage calendar by elevation (agronomist to correct), all Hindi text (native review), rain thresholds in mm.
- **Corrections found while verifying:** HP point 7 forbids mixing *any other* chemical with the recommended pesticides; the mite schedule has a third stage; the HP PDF prints a US poison number that must not be shown.
- **Photo test set v1** (`data/images/`): 23 leaf photos, 5 fruit, 4 excluded; web images, unconfirmed labels, internal testing only.
- **Not yet built:** data for crops beyond apple, tomato, potato, maize and grape; the voice prompt catalogue; a multi-crop photo set.

---

## 6. How a recommendation is produced

```
input: photo, farmer, today, location
 0. Photo quality check; identify the crop (+ confidence). Low confidence -> ask the farmer to confirm with one tap, or expert
 1. Crop has no approved data in the product master -> "consult an expert" (stop)
 2. Detect the disease with that crop's model. Alternaria/Marssonina or low confidence -> agronomist queue + general protective advice
 3. Crop stage <- date + elevation band (configurable calendar); season check on the detected disease
 4. Candidates <- product master: crop, disease, stage match AND approved AND not banned
 5. Remove: same active ingredient or FRAC group as the last spray; groups over their season limit; waiting period longer than days to harvest
 6. Rank, then timing from the forecast (avoid rain within 12 h; dodine not above 30 C; repeat within 7 days after heavy rain)
 7. Retrieve notes (RAG)
 8. LLM writes the advice + a SPOKEN version from steps 1-7 only -> structured JSON
 9. Validate against the rule output; mismatch -> safe template
10. Voice service turns the spoken version into audio (cached); show the card, speak it; on "Sprayed ✔" write to Zoho
```
Automatic alerts reuse steps 3 to 10, triggered by the hourly scheduler.

---

## 7. Work packages (durations to be estimated by the team)

The earlier schedule assumed one crop picker, apple depth and no voice. The new scope adds crop identification, all-crop data, voice and low-end device testing, so **it needs a fresh estimate.** Suggested order:

| # | Work package | Contents | Notes |
|---|---|---|---|
| 0 | **Decisions and tests (first)** | Crop-identification test; client's crop counts; native Hindi reviewer named; TTS listening test (2 to 3 voices); test phone chosen | Decides WP2 and WP4 |
| 1 | Backend core | Database, adapters, rules engine, product master, tests against the 11 scenarios | Data is ready |
| 2 | Vision services | Crop identification, per-crop disease models, quality check, on-device conversion, evaluation harness | After WP0 |
| 3 | Knowledge and LLM | RAG, provider interface, spoken-advice writer, number-to-words, validator | |
| 4 | **Voice** | Prompt catalogue (EN and HI), generation pipeline, native-speaker review sheet, audio packaging, app player, replay and slow controls | Needs reviewer time |
| 5 | Mobile app | First-run language, home, camera flow with voice, crop confirmation, result, spray diary, my field, alerts, offline queue | Low-end optimisation |
| 6 | Alerts and integrations | Scheduler, weather, mock sensors and Zoho, push | |
| 7 | Admin web | Product list, thresholds, review queue, alerts | Basic |
| 8 | **Field usability test** | Real farmers, low-end phones, noisy conditions | Early and again before release |
| 9 | Operations | Hosting, secrets, backups, monitoring, privacy | Light |
| Later | Watering, two-way voice, more languages, more crops, private GPU model, training | | Phase 2 |

---

## 8. Demo scenarios

Data scenarios S1 to S11 are in `data/demo_scenarios.json` (scab offline, Marssonina in July, rain wash-off alert, scab infection alert, off-label catch, DMI limit, potato late blight, tomato yellow leaf curl "no cure", stale record, sensor offline, same-day mixing). **To add:** (S12) **voice walkthrough**: first-run language choice, spoken camera instruction, crop spoken and confirmed, advice read aloud in Hindi then English; (S13) **crop identification** with photos of several crops, including a wrong-crop correction.

---

## 9. Later / stretch
Two-way voice and voice questions in Hindi; WhatsApp alerts; label-photo recognition for the spray diary; Pahari voices (recorded); watering.

---

## 10. Risks

| Risk | Impact | Plan |
|---|---|---|
| **Crop identification errors** (untested) | Wrong disease list and wrong medicine list | Test first; Zoho crop prior; show and speak the detected crop; confirm when unsure; no advice without approved data |
| Field accuracy low (§4.1, §4.3) | Wrong diagnosis | Auto-advice for scab only; date and stage prior; expert queue; honest message to the client; phase-2 fine-tune |
| **Machine voice mispronounces** numbers, units, chemical names; one voice for all regions | Farmer misunderstands a dose | Number-to-words step; reviewed Hindi glossary; native-speaker review; listening test; field test |
| **Cheap or old phones** (3 GB RAM, Android 9, little storage; no iPhone 6) | Slow or unusable app | Small on-device model, small install, test on real low-end phones early |
| Many crops without approved data or photo models | Gaps for pea, cauliflower, cabbage, wheat, ginger and others | Tiered coverage; "consult an expert" by rule; find the CSKHPKV package of practices; load HP stone-fruit, mango and citrus schedules |
| PlantVillage licence ambiguity | Share-alike might reach models trained on it | Fine for an internal MVP; legal check before production |
| `ixrbhii` models are new (4 Oct 2026) with vague data | Unknown accuracy and licence chain | Test on real photos; attribution |
| Weather API licensing (IMD and Open-Meteo free are non-commercial) | Licence breach in production | Open-Meteo Standard (about $29/month) or Visual Crossing |
| gpt-4o-mini retires 14 Jan 2027 | Demo stops working | Model name in `.env`; test `gpt-6-luna`; switch before then |
| TTS pricing and Hindi voice availability not verified | Cost or quality surprise | Listening test and price check before committing |
| Wrong chemical advice | Crop damage, trust, legal | Rules engine and allow-list, banned and off-label checks, validator, agronomist review |
| Antibiotic spray ban not finalised; "proposed to be banned" products | Possible illegal advice | Exclude antibiotics; keep the others with a warning flag; admin can disable |
| "Heavy rain" undefined in mm | Rule ambiguity | Configurable (default 10 mm in 12 h); client agronomist to confirm |
| Mock sensors and Zoho may not match the real ones | Rework | Adapters plus a schema review with the client |

---

## 11. Decisions and questions

**For you (internal):**
1. **Which crops does the client's farmer base grow?** (Zoho counts.) This sets the MVP crop list.
2. **Can I run the crop-identification test now** (PlantDoc plus ChatGPT vision and the `ixrbhii` crop detector)?
3. **TTS:** which cloud account can we use for the listening test (Google Cloud, or the free self-hosted Indic Parler-TTS)? Who is the native-speaker reviewer, and how much time can they give?
4. **Team and timeline:** re-estimate §7 with the new scope. Which package can shrink?
5. **Watering:** still deferred for the MVP?
6. **iPhone:** do the farmers use iPhones at all? If so, iPhone 6s or newer is the realistic floor.
7. **Kindwise:** may we use the 100 free credits to test it? And test `gpt-6-luna`?
8. **Admin panel tech:** React or Flutter web?
9. **Client sharing:** show the client the honest accuracy section (§4.4)? I recommend yes.

**For the client:** crop counts; approved product list and doses (we use the HP schedules until then); whether a trained model exists; confirmed photos with dates and villages (especially Marssonina and Alternaria); an agronomist to confirm labels, the stage calendar, the rain threshold and the leaf-spot-family idea; the IoT platform; users and budget.
