# -*- coding: utf-8 -*-
"""Generate data/README.md from the actual files so counts and scenario facts cannot drift."""
import json, pathlib, subprocess, sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
rd = lambda p: pd.read_csv(ROOT / p, keep_default_na=False, na_values=[""])
pm, dis, bm, cal = rd("reference/product_master.csv"), rd("reference/disease_catalogue.csv"), rd("reference/brand_master.csv"), rd("reference/stage_calendar.csv")
f, flat, sr, st = rd("farmers.csv"), rd("mock_zoho/advisory_rows_flat.csv"), rd("iot/sensor_readings.csv"), rd("weather/stations.csv")
notes = [json.loads(l) for l in open(ROOT / "reference/advisory_notes.jsonl", encoding="utf-8")]
sc = json.load(open(ROOT / "demo_scenarios.json", encoding="utf-8"))["scenarios"]
res = subprocess.run([sys.executable, "validate.py"], cwd=ROOT / "scripts", capture_output=True, text=True, encoding="utf-8", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
summary = [l for l in res.stdout.splitlines() if l.startswith("PASS")]
passline = summary[-1] if summary else "validation not run"

demo_dis = dis[dis.in_demo_scope == True]
apple_pm = pm[pm.crop == "Apple"]
sc_rows = "\n".join(f"| {s['id']} | {s['title']} | {s['farmer_id']} | {s['station_id']} | {s['demo_clock']} |" for s in sc)

md = f"""# FarmTrack MVP: demo data

**Generated:** 19 Oct 2026 by `scripts/` (re-runnable). **Validation:** `{passline}` (`python scripts/validate.py`).

This folder holds everything the MVP needs to run a convincing end-to-end demo **without the client's real systems**. It mixes three kinds of data. **Do not present the fabricated or simulated parts as real client data.**

## 1. What is real, what is fabricated

| Data | Origin | Notes |
|---|---|---|
| Product doses, waiting periods, target diseases, stages (apple) | **REAL**: HP Horticulture Dept + UHF Nauni *Spray Schedule 2026 (Apple)* | Doses and waiting periods were checked against the rendered PDF pages on 19 Oct 2026 |
| Official brand list per product, with manufacturer | **REAL**: same schedule, "Pesticides formulations recommended and evaluated" table | `reference/brand_master.csv`, {len(bm)} brands |
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
| `reference/product_master.csv` | Recommendable products with dose, waiting period, FRAC/IRAC, targets, ban status, HP brands | {len(pm)} ({len(apple_pm)} apple) |
| `reference/brand_master.csv` | Official HP 2026 evaluated brands + company | {len(bm)} |
| `reference/disease_catalogue.csv` | All 38 on-device model labels (exact spelling) + 8 server-model apple labels + extras; flags for expert referral | {len(dis)} ({len(demo_dis)} in demo scope) |
| `reference/offlabel_products.csv` | Products in the client's Zoho that are NOT approved for apple (flag, never recommend) | 3 |
| `reference/banned_restricted.csv` | Banned / restricted / excluded actives | {len(rd('reference/banned_restricted.csv'))} |
| `reference/stage_calendar.csv` | Apple stage dates by elevation band (B1 under 1500 m, B2 1500-2000, B3 2000-2500, B4 2500+) and cultivar harvest | {len(cal)} |
| `reference/rules_config.json` | Thresholds: Mills table, rain, rotation, confidence, late-blight rule, alerts | 1 file |
| `reference/advisory_notes.jsonl` | RAG knowledge base: product, rule and disease notes, EN + draft HI | {len(notes)} |
| `reference/hindi_glossary.json` | Crop, stage, disease and active-ingredient names in Hindi (draft) | n/a |
| `farmers.csv` | Fabricated farmers | {len(f)} |
| `mock_zoho/advisory_rows_flat.csv` | Advisory-table rows in the client's columns (+ hidden `_` helper columns) | {len(flat)} |
| `mock_zoho/contacts.json` | Zoho-API-style Contacts with Advisory, Variety_Mix, Nutrition, Notes | {len(f)} contacts |
| `weather/stations.csv`, `weather/weather_hourly_raw.csv` | 12 stations, hourly real weather | {len(st)} stations, 70,560 rows |
| `iot/sensor_readings.csv` | Simulated sensor feed; `_seeded_*.csv` list the planted glitches and outages (for QA) | {len(sr):,} |
| `demo_scenarios.json` | 11 scripted demo stories anchored to real weather events | {len(sc)} |
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
- **Mess is deliberate:** blank cells (about {int(round(100 * flat[flat.row_kind=='self_spray'].Self_Spray_Frac_Group.isna().mean()))}% of FRAC cells), free-typed names, M3 vs M03, out-of-order rows, a mostly empty rainfall column. Clean rows exist only for the scripted scenario farmers.
- **Off-label rows:** Miravis Duo, Meothrin and Trot appear only for farmer F008, copied from the client's real rows.
- **The HP schedule's waiting periods** are the only ones used for apple. Where the table prints "-" the value is blank, and `rules_config.json` says to ask an expert if harvest is within 30 days.
- **Brands:** the HP table lists brands that were *recommended and evaluated*. A brand missing from it is not necessarily unapproved.
- **Sources of doubt:** `confidence` columns use V (verified in source), V-s (secondary), I (inferred). Grape rows are mapped by inference. Streptomycin + tetracycline is excluded.
- **A US poison-control number** (1-800-222-1222) is printed in the HP PDF's safety section. It is not shown anywhere in this data; the client must supply an Indian helpline.

## 5. Demo scenarios

Each scenario is anchored to a real weather event found in the archive (see `facts` in `demo_scenarios.json`; `validate.py` recomputes them).

| ID | Story | Farmer | Station | Demo clock |
|---|---|---|---|---|
{sc_rows}

The demo needs a **configurable clock** because it is October and apple spray stages are not current. The weather after the clock is served from the real archive as a "perfect forecast" with noise.

## 6. Not modelled yet

Zoho Visits, Calls, Messages and Attachments content; field staff workload; the client's real IoT platform schema; per-plot sensors; irrigation (deferred); Pahari or other regional languages; photos (no leaf images are generated: use public datasets, see `docs/research/cv-models.md`).
"""
(ROOT / "README.md").write_text(md, encoding="utf-8")
print("README.md written,", len(md), "chars |", passline)
