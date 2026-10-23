# FarmTrack Farmer Advisory App: project memory

Read this first in any session about this project. Last rewritten 19 Oct 2026.

| File | What it is |
|---|---|
| **`docs/mvp-plan.md`** | **The current plan** (scope, architecture, vision/voice/device approach, data, work packages, risks) |
| `docs/requirements.md` | Requirements with source tags and scope updates |
| `docs/open-questions.md` | **Doubts and autonomous decisions made while building (read at review)** |
| `docs/research/cv-models.md`, `docs/research/agronomy-data.md` | Verified research (models, datasets; HP 2026 schedule, doses, rules, bans) |
| `data/` | Built demo data, photo test set, model test kits (`data/README.md`, `data/model_test/`) |
| `backend/`, `mobile/`, `voice/` | The application (built autonomously from 19 Oct 2026; see "Build status") |
| `docs/design-notes/` | Per-agent working notes of the build (reference detail: rules, vision, platform, mobile ...) |
| `contracts/openapi.json`, `scripts/` | The API contract (truth for the app) and helper scripts (phone-test backend start) |
| `README.md` | Overview, repository layout and quick start for people new to the repository |

## What this is
Soft Suave Technologies is building a **bespoke, very simple, voice-guided mobile app** for **FarmTrack AgTech** (client contact Mr. Shehzad Sharif; Soft Suave: Aaliya prototype, Manigandan architecture). The farmer takes a photo; the **system identifies the crop itself** (no crop picker), then the disease, the solution and the **medicine from the approved list only**, personalised by Zoho spray history and weather; later watering. For **all Himachal Pradesh crops**. Most users are uneducated farmers, so **the app speaks every step**.

## Decisions (user, 19 Oct 2026 unless noted)
- **Scope:** all Himachal crops; **automatic crop identification** (first and most critical gate; **not yet tested**); MVP covers fewer crops (apple deep; tomato, potato, maize, grape light).
- **Voice:** one-way (app speaks, does not listen); **generated voice** reviewed by a native speaker; **Hindi + English now**, many languages later as a data task. Fixed prompts = audio generated once and bundled; dynamic advice = backend writes a separate "spoken version" and generates audio (cached).
- **Phones:** Android 9+, iPhone "newer than 6" (Flutter needs iOS 15, so effectively iPhone 6s/7+), 3-6 GB RAM, 32-128 GB storage.
- **Stack:** Flutter app; Python FastAPI backend + PostgreSQL/pgvector; FCM push; admin web (server-rendered). Zoho and IoT mocked behind adapters.
- **LLM:** OpenAI `gpt-4o-mini`, name in `FarmTrack/.env` (never read `.env`: it holds the user's key). **Shuts down 14 Jan 2027**; switch to `gpt-6-luna`. **Role: explain, personalise, answer questions. NOT the diagnostic safety net, symptom reader or photo-quality gate** (test evidence below).
- **No model training now.** Watering deferred for the MVP. Leaf images are never generated.
- **Build mode (19 Oct 2026, later):** user is away, said "do not ask any question, do not stop midway, note doubts in an md file, use multi-agent, best practice". So: decide autonomously, record doubts in `docs/open-questions.md`, keep other docs light.

## Core design rules
- **Rules decide; the LLM only explains.** Rules engine + product master choose product, dose, timing; LLM output is validated against the rule output, else a safe template.
- **Approved list is enforced in code** per crop. **No medicine advice for a crop with no approved data.**
- **Zoho history is read with queries and computed in code** (rotation, counts, dates, rain since spray); RAG only for free-text notes.
- Banned, off-label and waiting-period checks are hard rules.
- **Auto-advice policy:** every disease with chemical control (`RULES_AUTO_ADVICE_DISEASES=*`, owner decision 19 Oct 2026, widened from the original apple-scab-only plan despite the evidence below). Hard guards stay: expert-review/no-cure/low-confidence/unknown/wrong-crop go to the expert queue. Set the variable empty to narrow it back to scab.

## Evidence so far (directional: 23 web-image leaf photos, unconfirmed labels)
- **Vision:** model A (on-device, 38 classes) 0/23 over all classes, 3/23 apple-only (calls Marssonina "scab" at 0.6-1.0); model B (server apple, 8 classes) 6/23 exact, 11/23 lenient (scab 4/4, Alternaria 1/8, Marssonina 2/11; 5/8 Alternaria and 5/11 Marssonina called scab at ~0.9). **Confidence did not separate right from wrong; A/B agreement did not help.** Only scab is recognised with any reliability.
- **ChatGPT vision (gpt-4o-mini):** answer depends on the prompt (no menu: "scab" 22/23; with menu: "Marssonina" 15/23), templated probabilities, symptom descriptions echo the prompt, marks every photo usable; hybrid with vision top-3: 13/23 (fixed 3, broke 1). Real cost $0.17 per 84 requests (~$0.002 per photo; the earlier "3-5 cents" estimate was wrong).
- **Plan impact (original; the owner later widened the policy, see above):** auto-advice only for apple scab; date/growth stage as a main signal; leaf-spot-family protocol needs agronomist approval; agronomist queue for Alternaria/Marssonina; phase-2 fine-tuning on confirmed client photos (a few hundred per disease, Mar-Aug 2027). Training is not done now.
- Review files: `data/model_test/review_2026-10-19.md`; kits: `run_models.py`, `run_llm_vision.py` (key in `.env`, uploads photos to OpenAI: non-client photos only).

## Data (built, `data/`, 89 checks pass, reproducible)
Real: HP 2026 apple doses/waiting periods/stages (checked against the PDF), HP evaluated-brand table (103 brands), CIB&RC/NIPHM/TNAU doses (tomato, potato, maize, grape), FRAC/IRAC, weather rules, real hourly 2026 weather for 12 stations. Simulated: sensors. Fabricated: 50 farmers (invalid phones), 444 mock Zoho rows in the client's columns, 11 scenarios. Counts: 97 products (68 apple), 50 disease classes, 186 notes, 40 rules. **Estimates/drafts:** stage calendar (agronomist to correct), all Hindi text (native review), rain thresholds in mm. The demo needs a configurable clock (it is October). Photo test set v1: 23 leaf, 5 fruit, 4 excluded; internal testing only.

## Things easy to get wrong
- Field accuracy is far below lab accuracy; never promise 90-95% before phase 2. Crop ID errors compound (wrong crop = wrong medicine list).
- HP 2026: heavy rain within 12 h of a spray means repeat within 7 days ("heavy" undefined: config default 10 mm); do not repeat the same chemical; **point 7: do not mix any other pesticide, chemical, micronutrient, growth regulator or hormone with the recommended products**; dodine not above 30 C; captan 15 days away from oil. FRAC limits: DMI 4/season, QoI 3 (mixtures only), SDHI 2 consecutive. Mite schedule has a third stage (`walnut_plus_40d`).
- Off-label products in the client's Zoho (Miravis Duo, fenpropathrin 30 EC, thiamethoxam 30 FS): flag, never recommend. Exclude streptomycin + tetracycline. "Proposed to be banned" (captan, carbendazim, mancozeb, thiophanate-methyl, zineb, ziram, chlorpyriphos): still registered; show a warning.
- A brand missing from the HP table is "not in the HP evaluated list", not "unapproved". The HP PDF prints a US poison-control number: never show it.
- Weather licensing: IMD and Open-Meteo free tier are non-commercial.
- Voice: Chirp 3 HD has no SSML or speaking rate; TTS prices and Hindi voice availability not verified; no TTS lists Pahari; machine voice mispronounces numbers and units unless the text is written for the ear.
- PlantVillage licence is ambiguous; `ixrbhii` models are new (4 Oct 2026).
- Zoho CRM is not a sensor store.

## Build status (update as work proceeds)
- **19 Oct 2026: MVP built autonomously (owner away), Android first, iOS deliberately not looked at yet.** Read `docs/open-questions.md` first (decisions to veto, questions, what is untested), then `backend/README.md` and `mobile/README.md`. `notes/` holds the per-agent working notes (reference).
  - **Backend** (`backend/`, FastAPI + SQLAlchemy 2 + Alembic): rules engine (approved list, season/stage, FRAC/IRAC, waiting period, rain, risks), vision (quality gate, crop id, disease; stub by default, torch models optional), advice composer + validator, RAG ask, voice/TTS cache, scan pipeline, spray diary with idempotent offline replay, field, alerts + scheduler, Zoho/IoT/weather/push adapters (mock + real-shaped), security layer, server-rendered admin. About 2.7k tests offline. `contracts/openapi.json` is the API truth.
  - **Mobile** (`mobile/`, Flutter, Riverpod, no codegen): voice-first screens for login, home, scan, advice/expert results, diary, field, alerts, ask, settings; offline queue; push interfaces. About 670 tests, analyze clean; real client verified against the real backend (`mobile/tool/run_live_check.*`, 31 calls).
  - **Not verified:** any device build, camera, TTS audio, Docker image, PostgreSQL/pgvector, real OpenAI/TTS/Zoho/FCM/SMS/Open-Meteo calls. Stub vision by default; on-device model not converted.
  - **Owner decisions after the build (19 Oct 2026):** (1) expert answers go by PHONE CALL (admin expert page shows the farmer's phone); (2) SMS gateway: later; for the MVP there is NO OTP: login = username + password, always required, light security (OTP code kept behind `OTP_LOGIN_ENABLED`); (3) automatic advice for ALL diseases with chemical control (`RULES_AUTO_ADVICE_DISEASES=*`; hard guards unchanged); (4) mobile = Android only for now, iOS later; (5) no seasonal restriction during development (`RULES_SEASON_CHECK=false`, default; true restores scab/leaf-spot seasons and stage-based products).
  - Still open: native Hindi review, agronomist questions, photo retention, hosting. See `docs/open-questions.md`.

## Open items (client and team)
Crop counts from the client's Zoho; approved lists for other crops (HP stone fruit / mango / citrus schedules not yet loaded; CSKHPKV package of practices not found); agronomist confirmation of labels, stage calendar, rain threshold and leaf-spot-family idea; the client's real photos with dates and villages; native Hindi review; TTS listening test and prices; team re-estimate of the work packages.

## Conventions
- Source tags: [D] discovery, [T] technical call, [U] internal brief, [P] proposal. Research labels: V verified, V-s secondary, I inferred, NF not found. Never invent doses.
- After each decision or milestone update `docs/mvp-plan.md`, `docs/requirements.md` and this file.
