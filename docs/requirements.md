# FarmTrack Farmer Advisory App — Requirements

**Client:** FarmTrack AgTech, contact **Mr. Shehzad (Shezad) Sharif**
**Vendor:** Soft Suave Technologies (Aaliya, Manigandan)
**Status:** Requirements gathered. **MVP plan written: see `docs/mvp-plan.md`** (19 Oct 2026).
**Last updated:** 19 Oct 2026

> **MVP scope decisions (19 Oct 2026):**
> - Generic multi-crop, with apple as the deep demo crop.
> - Flutter app.
> - Zoho and IoT mocked.
> - OpenAI LLM: **`gpt-4o-mini`** (user decision). It shuts down on 14 Jan 2027, so the model name is configurable and must switch to `gpt-6-luna` before then.
> - No model training; pretrained models only. The client's photos are used as a test set only.
> - Fabricated but source-grounded data.
> - **FR-3 (irrigation) deferred.**
>
> **SCOPE UPDATE, 19 Oct 2026 (later; stated by the user):**
> - The app is for **all crops grown in Himachal Pradesh**, not only apple.
> - **No crop picker.** The farmer just takes a photo; **the system must identify the crop itself**, then the disease, the solution and the medicine (**from the approved list only**), and the **crop watering** advice.
> - Watering stays **deferred for the MVP** (earlier decision) but is part of the full product. To be confirmed.
> - Consequence: automatic crop identification becomes the first and most critical step. A wrong crop means a wrong disease list and a wrong medicine list. See `docs/mvp-plan.md` section 4.8.
>
> **VOICE REQUIREMENT, 19 Oct 2026 (later; stated by the user):**
> - Most users are **not educated** and know only farming, so the app must be **very basic, very easy, and voice-guided**: it **speaks** every step ("open the camera and take a photo of the diseased leaf", "tick this box", "tap this to add more photos", "tap send").
> - **One-way for now:** the app speaks, it does not listen. Two-way voice (voice commands, asking by voice) is a later phase.
> - **Languages now: Hindi and English** (the user said "Assafno"; read as "as of now"). **Later: many Indian languages**, because people understand only their home language. The design must make adding a language a data task, not a code change.
> - Design implications: one step per screen, speech starts automatically on each screen, big picture buttons, an always-visible replay button, almost no typing or reading. See `docs/mvp-plan.md` section 4.9.
>
> **These decisions change parts of this document:**
> - **FR-1.5 (90–95% accuracy):** moved to phase 2. It needs fine-tuning on the client's field photos.
> - **NFR-7 (private GPU LLM):** moved to phase 2. The MVP uses the OpenAI API behind a swappable interface.

### Where each requirement came from

| Tag | Source |
|---|---|
| **[D]** | Discovery call and requirements summary PDF, 16 Oct 2026 (3 min 51 s, recorded) |
| **[T]** | Technical call notes (FarmTrack and Soft Suave); date not stated in the notes |
| **[U]** | Internal brief, 19 Oct 2026 |
| **[P]** | Soft Suave proposal or inference. **Not yet confirmed by the client.** |

---

## 1. What the product is

A lightweight, very simple **mobile app for farmers**. A farmer takes a **photo of a diseased leaf**, and the app:

1. **Identifies the disease** [D][T]
2. Recommends the **right pesticide or fungicide**: product, dose, and **when to spray** [U][D]
3. Advises **how much to water and when** [U]

Every piece of advice is personalised from:
- the farmer's own **spray history in Zoho CRM**
- live **IoT sensor readings**
- **IMD weather data**
- the **client's own advisory database**

[D][T]

The client's edge is **his own data, model and advisory**. He knows similar apps exist. [D]

**Likely crop and region:** apple orchards in Himachal Pradesh. The FarmTrack and Shimla context, the chemicals in Zoho, and the "state-approved brands in Himachal" requirement all point this way. [D][T] — **confirm the crop list.**

---

## 2. Users

| User | Needs |
|---|---|
| **Farmer** (primary) | Low digital literacy, low-cost Android phone, weak network, Hindi or regional language. Needs scanning, advice, alerts and a spray diary. [D][T] |
| **Agronomist / client expert** | Reviews low-confidence scans and, if required, approves advice before it is sent. [D][P] |
| **Client admin team** | Manages the advisory DB, disease list, approved products and alerts, and views farmer data. [D] |
| **Field staff** | Currently type spray records into Zoho by hand. Their role after launch is TBD. [D] |

---

## 3. Functional requirements

### FR-1 Disease detection from a photo
- **FR-1.1** The farmer photographs a leaf or plant, and the app identifies the disease. [D][T]
- **FR-1.2** Scope: **about 8–10 common disease patterns**. [T] (The discovery call said 10. [D])
- **FR-1.3** Uses the **client's own trained model**, or one we train with his data. [D] — *who owns or builds the model is open.*
- **FR-1.4** **Runs on the device** for speed, so basic detection works **offline**. [T]
- **FR-1.5** Target accuracy: **90–95%**. [T] *(See Risk R-1.)*
- **FR-1.6** Returns a **confidence score**. Low-confidence or "unknown" results go to an agronomist instead of producing automatic advice. [D][P]
- **FR-1.7** Photos are saved for retraining, so the dataset grows through use. [P]

### FR-2 Pesticide / spray recommendation
- **FR-2.1** Advice comes **only from the client's advisory database** through a **RAG** pipeline. No general-knowledge answers. [D][T]
- **FR-2.2** Recommends only **state-approved brands and salts for Himachal**. [T]
- **FR-2.3** Each recommendation states: **what the problem is, which product, dose (how much), when to spray**, plus a **photo of the product pack**. [D][U]
- **FR-2.4** Personalised with the farmer's **spray history**, including **FRAC/IRAC group rotation** so the same resistance group is not repeated. [D][P]
- **FR-2.5** Accounts for **rainfall since the last spray**, which decides whether to re-spray. Zoho already has a column for this, though it is empty today. [D]
- **FR-2.6** Advice appears as **plain-language text**, with **green / yellow / red** severity. [D][T]

### FR-3 Irrigation / watering advice — *new on 19 Oct; not in either meeting's notes* — **DEFERRED: out of MVP scope (19 Oct 2026)**
- **FR-3.1** Tells the farmer **when to water and how much (the limit)**. [U]
- **FR-3.2** Based on **soil moisture** (IoT), **rainfall and forecast** (IMD), temperature and humidity, and crop stage. [T][P]
- **FR-3.3** Uses thresholds defined by the client's experts (e.g. "skip irrigation if rain above X mm is forecast within 48 h"). [P]
- ⚠ **Confirm with the client** that irrigation advice is in scope, and that he has the agronomic rules for it. Many Himachal apple orchards are rain-fed. [P]

### FR-4 Environmental data
- **FR-4.1** Pull **weather, temperature, humidity, soil moisture and rainfall** from the client's **IoT systems**. [T]
- **FR-4.2** Pull weather and forecasts from the **IMD (India Meteorological Department) API**. [T]
- **FR-4.3** "**My field**" screen shows live readings for the farmer's plot. [D]
- **FR-4.4** IoT readings currently flow into Zoho CRM. [D] Proposal: read raw sensor data from the IoT platform or a time-series store, and write only **summaries and alerts** to Zoho. [P]

### FR-5 Automatic advisories (push, no farmer action needed)
- **FR-5.1** The system generates **bespoke text advisories** when **environmental thresholds** are crossed, e.g. humidity or leaf wetness indicating a scab risk. [T]
- **FR-5.2** Other triggers: weather forecast, crop stage or season, and **disease detections from nearby farms**. [D]
- **FR-5.3** Delivery by **app push** and **WhatsApp**; SMS to be confirmed. [D]
- **FR-5.4** Automatic advisories use the **same RAG engine** and the same approved-product rules as FR-2. [D]

### FR-6 Zoho CRM integration
- **FR-6.1** Each farmer is a **Zoho Contact**. [D]
- **FR-6.2** The app **reads** the farmer's data: Advisory/spray table, Variety Mix, Nutrition, Notes, Visits, Attachments. [D]
- **FR-6.3** The app **writes back** diagnoses, advice sent and spray logs to the farmer's Zoho record. [D]
- **FR-6.4** Current Advisory table columns: Name, F.T.A Frac Group, Self Spray Dt., Self Sprayed, Self Spray Frac Group, Self Spray Trade Name, Date/Time 1, Total Rainfall Since Last Spray. [D]

### FR-7 Spray diary (replaces manual entry)
- **FR-7.1** The farmer marks an action as done with a **checkbox**, e.g. "medicine applied". [T]
- **FR-7.2** Products are **picked from a fixed list** (or captured by photographing the label), not typed. [D]
- **FR-7.3** Date, weather and rainfall are **filled automatically**. [D]
- **FR-7.4** Entries sync to Zoho (FR-6.3). [D]
- **FR-7.5** Reminders by push or WhatsApp. [D]

### FR-8 Ask an expert
- Chat or **voice** questions answered by the RAG engine from the client DB, with **one-tap "Talk to expert"** escalation. [D]

### FR-9 Admin panel (client team)
- Manage the advisory DB, disease list, and **approved product master** (trade name, salt, FRAC group, dose, approval status). [D][P]
- Review the low-confidence scan queue. [D]
- View sent alerts and farmer data. [D]
- Set the thresholds for automatic advisories and irrigation rules. [P]

### FR-10 Login and onboarding
- **Phone-number OTP** login, no passwords. Choose a language at first launch. [D]

---

## 4. Non-functional requirements

| ID | Requirement | Source |
|---|---|---|
| NFR-1 | **Extremely simple UI**: home screen with 4 big buttons (Scan crop, My field, Ask expert, Spray diary); photo to advice in 2 taps; icons beside text; checkboxes instead of typing | [D][T] |
| NFR-2 | **Avoid the "Fusel App" problem**, where a complex interface made users abandon it. *(Likely "Fasal"; confirm.)* | [T] |
| NFR-3 | **Hindi and regional languages**; voice input; advice read aloud | [D] |
| NFR-4 | **Lightweight** build for low-end Android phones; **low computational overhead** | [T] |
| NFR-5 | **Offline mode**: on-device detection and a photo queue that syncs later. Full advisory retrieval needs connectivity. | [T] |
| NFR-6 | **No hallucinations**: the LLM answers only from retrieved client data, with a refusal or expert fallback when nothing matches | [T] |
| NFR-7 | **Security and privacy**: custom LLM on a **private GPU server**; farmer data does not go to public AI APIs | [T] |
| NFR-8 | **Cost-effective** to run | [T] |
| NFR-9 | Sunlight-readable large text; compressed photo uploads | [D] |
| NFR-10 | Trust markers: "Advice by [client] experts" on every answer | [D] |

---

## 5. Proposed architecture (Manigandan, technical call)

```
[Farmer app (Android)]
   ├─ On-device CV model (TFLite/ONNX, quantised) ──> disease + confidence  (works offline)
   ├─ Offline queue (photos, diary entries)
   └─ API ──> [Backend]
                ├─ RAG service ──> Vector DB (client advisory DB, approved product master)
                │      └─> Private LLM on own GPU server (answers only from retrieved context)
                ├─ Rules engine (thresholds: disease risk, irrigation, re-spray after rain)
                ├─ IoT ingest / time-series store  <── client IoT platform
                ├─ IMD weather API
                ├─ Zoho CRM connector (read profile/history; write diagnoses, advice, spray logs)
                ├─ Notifications (push, WhatsApp, SMS?)
                └─ Admin panel (web)
```

**Design principle [P]:** deterministic rules and the approved-product master decide **what** may be recommended. The LLM only **explains it in plain language** from the retrieved records. This is the strongest guard against unsafe chemical advice.

---

## 6. Risks and gaps identified

| ID | Risk | Why it matters | Mitigation [P] |
|---|---|---|---|
| **R-1** | **90–95% accuracy target vs ~50 images in total** (about 5 per disease) | A reliable field model typically needs hundreds of real field photos per disease. At this data size, 90–95% is not realistic for phase 1. | Fine-tune a pretrained model; add public plant-disease datasets; collect photos through the app; agronomist review of low-confidence results. **Agree how accuracy is measured** (top-1 accuracy on held-out **field** photos, per disease). |
| R-2 | **Wrong spray advice** | Crop damage, farmer trust, regulatory exposure | Approved-product master; label-claim doses only; FRAC rotation; expert fallback; optional agronomist approval |
| R-3 | **Approved product list not yet supplied** | FR-2.2 cannot be built without it | Client provides the list of state-approved brands and salts per disease, with doses (possibly from the state or university spray schedule; confirm the source) |
| R-4 | **Irrigation rules undefined** (FR-3) | Not discussed with the client; may be out of scope | Confirm scope; get thresholds from the client's experts |
| R-5 | **Zoho as a sensor store** | Zoho CRM is not built for continuous sensor data and has API limits | Time-series store; only summaries go to Zoho |
| R-6 | **Messy Zoho data** | Blank cells, free-typed product names, rows out of order, stale records | Clean a sample; build the product master; map trade names to salts and FRAC groups |
| R-7 | **On-device model vs private GPU LLM cost** | GPU server running cost conflicts with "cost-effective" | Small open model (7–8B, quantised); size the GPU to load; consider batching automatic advisories |
| R-8 | **Offline vs advice** | Offline detection without advice may confuse farmers | Offline: show the disease plus a cached basic advisory card per disease; full advice when back online |
| R-9 | **Model ownership** | Unclear whether the client has a trained model or we build it | Ask in the next meeting |

---

## 7. Open questions for the client

**AI and data**
1. Is the vision model already trained, or do we build it? If it exists: framework, format, accuracy, training data?
2. "50 leaves": is that 50 images in total, or 50 per disease?
3. Which **crops** and which **8–10 diseases** exactly?
4. Where does the **advisory DB** live (Zoho, Excel, PDFs, a separate DB)? How big is it, and who updates it? Please share 20–50 sample records.
5. Please share the **list of state-approved brands and salts** with doses per disease, and its source.
6. Should advice go **directly** to farmers, or be **approved by an agronomist** first?
7. How is the **90–95% accuracy** measured, and on which images?

**Irrigation (new)**
8. Is **watering advice** (when and how much) in scope? Which crops are irrigated, and by what method (drip, sprinkler, manual)?
9. What are the soil-moisture and rain thresholds, and who defines them?

**IoT and weather**
10. Which sensors and parameters, which IoT platform, how does data reach Zoho, and how often?
11. Is there one device per farmer or per plot? How many are installed, and how much history is stored?
12. Is there **IMD API access** (registration or key), or should we arrange it?

**Zoho**
13. Which Zoho data appears in the app? Is it read-only or two-way? What does "**F.T.A**" stand for? How many farmer Contacts are there?
14. Who fills the Advisory table today, and how?

**Users and app**
15. How many farmers in year one? Which languages? Android only, or iOS too? Is a web admin panel enough?
16. Alerts by push, WhatsApp or SMS?
17. What exactly went wrong with the **"Fusel" (Fasal?) app**? Any app he likes?

**Commercials**
18. Budget range, target launch date, MVP-first approach?

---

## 8. Suggested MVP scope [P]

| In MVP | Later phases |
|---|---|
| OTP login, Hindi + English | More regional languages, full voice chat |
| Scan → on-device detection (8–10 diseases) → RAG advice from approved list | Retraining pipeline, nearby-outbreak alerts |
| Agronomist review queue for low confidence | Fully automatic advice once accuracy is proven |
| Spray diary with checkboxes and Zoho write-back | Label photo capture (OCR) |
| IoT + IMD "My field" screen; threshold alerts by push | WhatsApp/SMS channels, irrigation scheduling (if confirmed) |
| Basic admin panel (product master, disease list, review queue) | Analytics and reporting |

---

## 9. Next steps

- [ ] Soft Suave (Aaliya and team) build the **prototype** matching the technical spec, for review in the follow-up meeting. [T]
- [ ] Send the client the open-questions list (§7), especially the **approved product list**, the **dataset**, and **irrigation scope**.
- [ ] Get sample data: 20–50 advisory records, the disease images, and a sample of IoT readings.
