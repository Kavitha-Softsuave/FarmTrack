# FarmTrack MVP: demo data

**Generated:** 19 Oct 2026 by `scripts/` (re-runnable). **Validation:** `PASS 89 | WARN 0 | FAIL 0` (`python scripts/validate.py`).

This folder holds everything the MVP needs to run a convincing end-to-end demo **without the client's real systems**. It mixes three kinds of data. **Do not present the fabricated or simulated parts as real client data.**

## 1. What is real, what is fabricated

| Data | Origin | Notes |
|---|---|---|
| Product doses, waiting periods, target diseases, stages (apple) | **REAL**: HP Horticulture Dept + UHF Nauni *Spray Schedule 2026 (Apple)* | Doses and waiting periods were checked against the rendered PDF pages on 19 Oct 2026 |
| Official brand list per product, with manufacturer | **REAL**: same schedule, "Pesticides formulations recommended and evaluated" table | `reference/brand_master.csv`, 103 brands |
| Non-apple doses (tomato, potato, maize, grape) | **REAL**: CIB&RC Major Uses 30.09.2026, NIPHM, TNAU, ICAR-IIMR | Rows with inferred mappings are flagged `confidence=I` |
| Resistance codes, rotation limits, rain rules, weather-disease rules | **REAL**: FRAC/IRAC, FRAC guidance, HP 2026, NIPHM, Penn State | See `reference/rules_config.json`. mm rain thresholds are **inferred defaults** |
| Weather (`weather/`) | **REAL**: Open-Meteo ERA5 archive, 12 stations, 15 Feb to 17 Oct 2026 | Free tier is **non-commercial**; fine for the demo, not for production |
| Sensor readings (`iot/`) | **SIMULATED** from the real weather | Adds bias, noise, outages, glitches; leaf wetness is a proxy (rain or RH >= 90%) |
| Farmers (`farmers.csv`) | **FABRICATED** | Real villages/varieties, invented people. Phones are deliberately invalid (+91 00000 ...) |
| Mock Zoho rows (`mock_zoho/`) | **FABRICATED** in the client's real column shape | Spray dates follow the stage calendar and real weather |
| Stage calendar (`reference/stage_calendar.csv`) | **ESTIMATE** | Anchored to Priyanka et al. 2021 (flowering Julian days by altitude); offsets inferred. **The client's agronomist should correct it.** |
| Hindi text | **DRAFT** written by the assistant | A native-speaker agronomy reviewer must approve it before any client demo |

## 2. Folder map

| Path | Contents | Rows |
|---|---|---|
| `reference/product_master.csv` | Recommendable products with dose, waiting period, FRAC/IRAC, targets, ban status, HP brands | 97 (68 apple) |
| `reference/brand_master.csv` | Official HP 2026 evaluated brands + company | 103 |
| `reference/disease_catalogue.csv` | All 38 on-device model labels (exact spelling) + 8 server-model apple labels + extras; flags for expert referral | 50 (37 in demo scope) |
| `reference/offlabel_products.csv` | Products in the client's Zoho that are NOT approved for apple (flag, never recommend) | 3 |
| `reference/banned_restricted.csv` | Banned / restricted / excluded actives | 7 |
| `reference/stage_calendar.csv` | Apple stage dates by elevation band (B1 under 1500 m, B2 1500-2000, B3 2000-2500, B4 2500+) and cultivar harvest | 128 |
| `reference/rules_config.json` | Thresholds: Mills table, rain, rotation, confidence, late-blight rule, alerts | 1 file |
| `reference/advisory_notes.jsonl` | RAG knowledge base: product, rule and disease notes, EN + draft HI | 186 |
| `reference/hindi_glossary.json` | Crop, stage, disease and active-ingredient names in Hindi (draft) | n/a |
| `farmers.csv` | Fabricated farmers | 50 |
| `mock_zoho/advisory_rows_flat.csv` | Advisory-table rows in the client's columns (+ hidden `_` helper columns) | 444 |
| `mock_zoho/contacts.json` | Zoho-API-style Contacts with Advisory, Variety_Mix, Nutrition, Notes | 50 contacts |
| `weather/stations.csv`, `weather/weather_hourly_raw.csv` | 12 stations, hourly real weather | 12 stations, 70,560 rows |
| `iot/sensor_readings.csv` | Simulated sensor feed; `_seeded_*.csv` list the planted glitches and outages (for QA) | 69,072 |
| `demo_scenarios.json` | 11 scripted demo stories anchored to real weather events | 11 |
| `scripts/` | Everything that generates and validates the above | n/a |

## 3. Rebuild

```
cd data/scripts
python fetch_weather.py 2026-10-17     # needs internet; skip to keep the committed weather
python build_reference.py              # reference/*
python build_sensors.py                # iot/*
python build_farmers.py                # farmers.csv
python build_zoho.py                   # mock_zoho/* and demo_scenarios.json
python build_advisory_notes.py         # reference/advisory_notes.jsonl
python validate.py                     # must end with FAIL 0
```
Requires Python 3 with `pandas` and `numpy`. All random generators are seeded, so rebuilding reproduces the same files.

## 4. Things to know about the data

- **Stations:** `weather/stations.csv` gives the Open-Meteo **grid-cell elevation**, which can differ from the village's true elevation (e.g. Kotgarh grid 1,450 m). Farmers' orchard elevations and stage bands are derived from the grid value so they stay consistent with the weather.
- **Client column names:** the Advisory columns are copied from the 16 Oct 2026 screenshot. The meaning of `Name` and `F.T.A Frac Group` is **assumed** to be the advisor's recommended product and its group; the Zoho API field names are assumed.
- **Mess is deliberate:** blank cells (about 26% of FRAC cells), free-typed names, M3 vs M03, out-of-order rows, a mostly empty rainfall column. Clean rows exist only for the scripted scenario farmers.
- **Off-label rows:** Miravis Duo, Meothrin and Trot appear only for farmer F008, copied from the client's real rows.
- **The HP schedule's waiting periods** are the only ones used for apple. Where the table prints "-" the value is blank, and `rules_config.json` says to ask an expert if harvest is within 30 days.
- **Brands:** the HP table lists brands that were *recommended and evaluated*. A brand missing from it is not necessarily unapproved.
- **Sources of doubt:** `confidence` columns use V (verified in source), V-s (secondary), I (inferred). Grape rows are mapped by inference. Streptomycin + tetracycline is excluded.
- **A US poison-control number** (1-800-222-1222) is printed in the HP PDF's safety section. It is not shown anywhere in this data; the client must supply an Indian helpline.

## 5. Demo scenarios

Each scenario is anchored to a real weather event found in the archive (see `facts` in `demo_scenarios.json`; `validate.py` recomputes them).

| ID | Story | Farmer | Station | Demo clock |
|---|---|---|---|---|
| S1 | Scab at petal fall, scanned offline, carbendazim used 10 days ago | F001 | ST01 | 2026-05-12 16:00:00 |
| S2 | Marssonina blotch weather in July: the on-device model has no Marssonina class, so the server apple model is needed | F028 | ST06 | 2026-07-05 08:00:00 |
| S3 | Heavy rain right after a mancozeb spray -> automatic 're-spray within 7 days' alert | F007 | ST02 | 2026-03-30 20:00:00 |
| S4 | Scab infection period reached the Mills threshold -> automatic alert to every apple farmer in the Jubbal block | (all apple farmers at ST05) | ST05 | 2026-05-04 21:00:00 |
| S5 | Off-label products found in the farmer's Zoho history (copied from the client's real rows) | F008 | ST02 | 2026-07-27 09:00 |
| S9 | Micronutrients logged the same day as a fungicide (the client's own 14/04/2026 pattern) | F011 | ST02 | 2026-04-15 09:00 |
| S6 | Four DMI (FRAC 3) sprays already used -> next recommendation must avoid DMI | F016 | ST04 | 2026-06-11 08:00:00 |
| S7 | Potato late-blight weather (NIPHM 7-day rule) turns true -> automatic alert and advice | F032 | ST07 | 2026-07-12 08:00:00 |
| S8 | Tomato yellow leaf curl virus: no cure, only vector control + roguing | F044 | ST11 | 2026-06-24 08:00:00 |
| S10 | Stale Zoho record (last update > 60 days) -> advice asks the farmer to confirm recent sprays | F013 | ST03 | 2026-10-17 09:00 |
| S11 | Sensor station offline: 'My field' shows a stale-data warning, alerts are marked 'based on forecast only' | (all farmers at ST08, Sangla) | ST08 | 2026-07-12 09:00 |

The demo needs a **configurable clock** because it is October and apple spray stages are not current. The weather after the clock is served from the real archive as a "perfect forecast" with noise.

## 6. Not modelled yet

Zoho Visits, Calls, Messages and Attachments content; field staff workload; the client's real IoT platform schema; per-plot sensors; irrigation (deferred); Pahari or other regional languages; photos (no leaf images are generated: use public datasets, see `docs/research/cv-models.md`).
