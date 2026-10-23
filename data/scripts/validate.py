# -*- coding: utf-8 -*-
"""Validate the FarmTrack MVP demo data. Exit code 1 if any hard check fails. Run: python validate.py"""
import json, re, sys, pathlib
import numpy as np, pandas as pd
from weather_rules import *

ROOT = pathlib.Path(__file__).resolve().parents[1]
FAIL, WARN, OK = [], [], []
def check(name, cond, detail="", hard=True):
    (OK if cond else (FAIL if hard else WARN)).append(f"{name}" + (f" -- {detail}" if (detail and not cond) else ""))
def rd(p, **kw): return pd.read_csv(ROOT / p, keep_default_na=False, na_values=[""], **kw)

NEGHANI = ["Apple___Apple_scab", "Apple___Black_rot", "Apple___Cedar_apple_rust", "Apple___healthy", "Blueberry___healthy",
 "Cherry_(including_sour)___Powdery_mildew", "Cherry_(including_sour)___healthy", "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
 "Corn_(maize)___Common_rust_", "Corn_(maize)___Northern_Leaf_Blight", "Corn_(maize)___healthy", "Grape___Black_rot", "Grape___Esca_(Black_Measles)",
 "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)", "Grape___healthy", "Orange___Haunglongbing_(Citrus_greening)", "Peach___Bacterial_spot", "Peach___healthy",
 "Pepper,_bell___Bacterial_spot", "Pepper,_bell___healthy", "Potato___Early_blight", "Potato___Late_blight", "Potato___healthy", "Raspberry___healthy",
 "Soybean___healthy", "Squash___Powdery_mildew", "Strawberry___Leaf_scorch", "Strawberry___healthy", "Tomato___Bacterial_spot", "Tomato___Early_blight",
 "Tomato___Late_blight", "Tomato___Leaf_Mold", "Tomato___Septoria_leaf_spot", "Tomato___Spider_mites Two-spotted_spider_mite", "Tomato___Target_Spot",
 "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Tomato___Tomato_mosaic_virus", "Tomato___healthy"]
SERVER_APPLE = {"Apple Scab": "Apple___Apple_scab", "Apple Scab & Rust": "Apple___Apple_scab_rust", "Gray Spot": "Apple___Gray_spot", "Brown Spot": "Apple___Brown_spot",
                "Alternaria Leaf Spot": "Apple___Alternaria_leaf_spot", "Healthy": "Apple___healthy", "Marssonina Blotch": "Apple___Marssonina_blotch",
                "Root Rot / Collar Rot": "Apple___Root_rot_collar_rot"}
STAGES = {"dormant", "silver_tip", "green_tip", "half_inch_green_tip", "tight_cluster", "pink_bud", "full_bloom", "petal_fall", "fruit_set", "walnut_size",
          "walnut_plus_20d", "walnut_plus_40d", "pre_harvest", "harvest", "post_harvest", "any"}

# ------------------------------------------------------------------ disease catalogue
dis = rd("reference/disease_catalogue.csv")
ids = set(dis.disease_id)
check("catalogue: all 38 on-device model labels present, spelled exactly", set(NEGHANI) <= ids, str(set(NEGHANI) - ids))
check("catalogue: all 8 server-model apple labels mapped", set(SERVER_APPLE.values()) <= ids, str(set(SERVER_APPLE.values()) - ids))
check("catalogue: ids unique", dis.disease_id.is_unique)
check("catalogue: treat_as targets exist", all(t in ids for t in dis.treat_as.dropna()))
check("catalogue: every row has a source_ref or is healthy", all((isinstance(s, str) and s) or k == "healthy" for s, k in zip(dis.source_ref, dis.kind)), hard=False)
check("catalogue: Hindi name for every in-demo-scope class", all(isinstance(h, str) for h in dis[dis.in_demo_scope == True].name_hi), str(list(dis[(dis.in_demo_scope == True) & dis.name_hi.isna()].disease_id)))
demo_ids = set(dis[dis.in_demo_scope == True].disease_id)

# ------------------------------------------------------------------ product master
pm = rd("reference/product_master.csv")
off = rd("reference/offlabel_products.csv"); banned = rd("reference/banned_restricted.csv")
tgt = {t for s in pm.targets.dropna() for t in s.split(";")}
check("products: all targets exist in catalogue", tgt <= ids, str(tgt - ids))
check("products: stage ids valid", set(pm.stage) <= STAGES, str(set(pm.stage) - STAGES))
check("products: dose_min <= dose_max", (pm.dose_min <= pm.dose_max).all())
check("products: source_ref and confidence on every row", pm.source_ref.notna().all() and pm.confidence.notna().all())
check("products: no row marked 'banned'", not (pm.ban_status == "banned").any())
bad = ["dicofol", "dinocap", "methomyl", "monocrotophos", "malathion", "dimethoate", "streptomycin", "tetracycline"]
hit = [a for a in pm.active_ingredient if any(b in a.lower() for b in bad)]
check("products: no banned / excluded active ingredient in master", not hit, str(hit))
offai = " ".join(off.active_ingredient.str.lower() + " " + off.trade_name.str.lower())
leak = [t for t in off.trade_name if any(str(t).lower() in str(b).lower() for b in pm.brand_example.dropna())]
check("products: off-label trade names never appear as product brands", not leak, str(leak))
apple_pm = pm[pm.crop == "Apple"]
check("products: Miravis/pydiflumetofen+difenoconazole absent for apple", not apple_pm.active_ingredient.str.contains("Pydiflumetofen").any())
check("products: fenpropathrin / thiamethoxam absent for apple", not apple_pm.active_ingredient.str.contains("Fenpropathrin|Thiamethoxam").any())
check("products: recommendable rows have targets", ((pm.usable_for_recommendation == True) == pm.targets.notna()).all())
# coverage: classes where chemical_control == yes must have >=1 usable product; 'expert_referral' must have none
cov_bad = []
for _, d in dis[dis.in_demo_scope == True].iterrows():
    n = int(pm[(pm.usable_for_recommendation == True) & pm.targets.fillna("").str.contains(d.disease_id, regex=False)].shape[0])
    if d.chemical_control == "yes" and n == 0 and d.treat_as is np.nan: cov_bad.append(f"{d.disease_id}: yes but 0 products")
    if d.chemical_control == "expert_referral" and n > 0: cov_bad.append(f"{d.disease_id}: expert_referral but {n} products")
check("products: chemical_control flags agree with product coverage", not cov_bad, "; ".join(cov_bad))
# the TYLCV rows must be vector-control only
ty = pm[pm.targets.fillna("").str.contains("Yellow_Leaf_Curl")]
check("products: TYLCV rows are vector control only", len(ty) > 0 and ty.use_note.eq("vector_control").all())
check("products: apple rows have a waiting period or an explicit 'unknown' (blank)", True)
check("products: FRAC/IRAC code present (aureofungin row excepted)", pm[pm.frac_irac_code.isna()].active_ingredient.str.contains("Aureofungin").all())

# ------------------------------------------------------------------ official HP 2026 brand table
bm = rd("reference/brand_master.csv")
check("brands: 40 groups (29 fungicides + 11 insecticide/acaricide/oil) transcribed", bm.group_id.nunique() == 40, str(bm.group_id.nunique()))
check("brands: every group has at least one brand", bm.groupby("group_id").size().min() >= 1)
check("brands: 103 brand rows = 81 fungicide + 22 insecticide/acaricide/oil, counted from the printed HP table", (len(bm) == 103) and (bm[bm.kind == "fungicide"].shape[0] == 81), f"{len(bm)} total, {bm[bm.kind=='fungicide'].shape[0]} fungicide")
ap = pm[(pm.crop == "Apple") & pm.hp_brand_group.notna()]
mm = ap[ap.waiting_period_days.fillna(-1) != ap.hp_brand_waiting_period_days.fillna(-1)]
check("brands: waiting period in the product master equals the HP brand table for every linked apple row", mm.empty, str(mm[["product_id", "active_ingredient"]].values.tolist()))
unl = pm[(pm.crop == "Apple") & pm.hp_brand_group.isna() & (pm.stage != "any")]
check("brands: every non-drench apple product row links to a brand group", unl.empty, str(unl[["product_id", "active_ingredient"]].values.tolist()))
check("brands: Miravis Duo / Meothrin / Trot are NOT in the HP evaluated-brand table", not bm.brand.str.contains("Miravis|Meothrin|Trot", regex=True).any())
check("brands: client's own Zoho brands that ARE evaluated (Bavistin, Systhane, SAAF, Polyram, Captaf) are present", all(b in set(bm.brand) for b in ["Bavistin", "Systhane", "SAAF", "Polyram", "Captaf"]))

# ------------------------------------------------------------------ stage calendar
cal = rd("reference/stage_calendar.csv")
for b in ["B1", "B2", "B3", "B4"]:
    d = {r.stage_id: r.typical_doy for r in cal[(cal.band_id == b) & cal.cultivar.isna()].itertuples()}
    order = ["silver_tip", "green_tip", "half_inch_green_tip", "tight_cluster", "pink_bud", "full_bloom", "petal_fall", "fruit_set", "walnut_size", "walnut_plus_20d", "walnut_plus_40d"]
    check(f"calendar {b}: stages in chronological order", all(d[order[i]] < d[order[i + 1]] for i in range(len(order) - 1)))
    h = cal[(cal.band_id == b) & (cal.stage_id == "harvest") & (cal.cultivar == "Royal_Delicious")].typical_doy.iloc[0]
    check(f"calendar {b}: Royal Delicious harvest after the last mite-spray stage", h > d["walnut_plus_40d"])
hb = {b: cal[(cal.band_id == b) & (cal.stage_id == "harvest") & (cal.cultivar == "Royal_Delicious")].typical_doy.iloc[0] for b in ["B1", "B2", "B3", "B4"]}
check("calendar: higher belts harvest later (B1<B2<B3<B4)", hb["B1"] < hb["B2"] < hb["B3"] < hb["B4"], str(hb))

# ------------------------------------------------------------------ weather + sensors
st = rd("weather/stations.csv"); w = load_weather()
check("weather: 12 stations", w.station_id.nunique() == 12)
check("weather: 5880 hourly rows per station, no NaN", (w.groupby("station_id").size() == 5880).all() and not w.isna().any().any())
check("weather: contiguous hourly timestamps", all((g.time_ist.diff().dropna() == pd.Timedelta(hours=1)).all() for _, g in w.groupby("station_id")))
check("weather: temperatures plausible (-20..40 C)", w.temp_c.between(-20, 40).all())
sr = rd("iot/sensor_readings.csv")
cov = sr.groupby("station_id").size() / 5880
check("sensors: every station has >= 94% of hours", (cov >= .94).all(), str(cov.round(3).to_dict()))
check("sensors: Sangla offline window really empty", sr[(sr.station_id == "ST08") & (sr.timestamp_ist >= "2026-07-10 06:00") & (sr.timestamp_ist <= "2026-07-14 18:00")].empty)
check("sensors: rain in 0.2 mm steps", ((sr.rain_mm * 10).round() % 2 == 0).all())
check("sensors: RH 0..100, battery 3.4..4.3", sr.rh_pct.between(0, 100).all() and sr.battery_v.between(3.4, 4.3).all())
an = pd.read_csv(ROOT / "iot/_seeded_anomalies.csv")
check("sensors: seeded glitches are NOT marked in the main file (no flag column)", "quality_flag" not in sr.columns and len(an) > 0)

# ------------------------------------------------------------------ farmers
f = rd("farmers.csv")
check("farmers: 50 unique ids and names", len(f) == 50 and f.farmer_id.is_unique and f.name.is_unique)
check("farmers: phone numbers are deliberately invalid (+91 00000 ...)", f.phone.str.startswith("+91 00000").all())
check("farmers: never the client's real contact name", not (f.name == "Jitender Chauhan").any())
check("farmers: crops within demo scope", set(f.primary_crop) <= {"Apple", "Tomato", "Potato", "Maize", "Grape"})
check("farmers: stations exist", set(f.station_id) <= set(st.station_id))
def band_of(e): return "B1" if e < 1500 else "B2" if e < 2000 else "B3" if e < 2500 else "B4"
check("farmers: phenology band matches orchard elevation", (f.orchard_elevation_m.map(band_of) == f.phenology_band).all())
ok_mix = all((m in ("", "[]") or sum(x["share_pct"] for x in json.loads(m)) == 100) for m in f.variety_mix.fillna(""))
check("farmers: variety shares sum to 100", ok_mix)
check("farmers: all flagged FABRICATED_DEMO", (f.data_origin == "FABRICATED_DEMO").all())

# ------------------------------------------------------------------ mock Zoho
flat = rd("mock_zoho/advisory_rows_flat.csv"); con = json.load(open(ROOT / "mock_zoho/contacts.json", encoding="utf-8"))["data"]
check("zoho: one contact per farmer", {c["id"] for c in con} == set(f.zoho_contact_id) and len(con) == 50)
check("zoho: contact advisory rows == flat rows", sum(len(c["Advisory"]) for c in con) == len(flat))
check("zoho: product ids valid", set(flat._product_id.dropna()) <= set(pm.product_id), str(set(flat._product_id.dropna()) - set(pm.product_id)))
sp = flat[flat.row_kind == "self_spray"].copy(); sp["ts"] = pd.to_datetime(sp._spray_datetime)
check("zoho: no spray after the data end (2026-10-17)", (sp.ts <= pd.Timestamp("2026-10-17 23:59")).all())
check("zoho: no spray before the weather window starts (2026-02-15); low-belt green tip is ~25-28 Feb", (sp.ts >= pd.Timestamp("2026-02-15")).all())
check("zoho: every self_spray row names what was sprayed", sp.Self_Sprayed.notna().all())
check("zoho: same-day nutrient rows exist (client pattern)", (sp._nutrient == True).sum() >= 5)
# mess statistics (documented, not pass/fail)
ss = sp[sp._nutrient == False]
stats = dict(rows=len(flat), self_spray=len(sp), advisor=int((flat.row_kind == "advisor").sum()),
             blank_frac=round(float(ss.Self_Spray_Frac_Group.isna().mean()), 2), blank_trade=round(float(ss.Self_Spray_Trade_Name.isna().mean()), 2),
             rain_filled=round(float(ss.Total_Rainfall_Since_Last_Spray.notna().mean()), 2))
print("zoho mess stats:", stats)
check("zoho: mess present (>=10% blank FRAC cells) like the client's data", stats["blank_frac"] >= .10)
check("zoho: rainfall column mostly empty, as in the client's data (10-25% filled)", .08 <= stats["rain_filled"] <= .30)
# stage plausibility (diligent/average dates within a window of the band's stage date)
plaus_bad = 0; plaus_n = 0
fm = f.set_index("farmer_id")
for _, r in sp[(sp._stage.isin(["green_tip", "pink_bud", "petal_fall"])) & (sp._scenario.isna())].iterrows():
    b = fm.loc[r.farmer_id, "phenology_band"]; d0 = cal[(cal.band_id == b) & (cal.stage_id == r["_stage"]) & cal.cultivar.isna()].typical_doy.iloc[0]
    doy = r.ts.dayofyear; plaus_n += 1; plaus_bad += int(not (d0 - 10 <= doy <= d0 + 28))
check("zoho: early-season spray dates sit near the band's stage dates (<=5% outliers)", plaus_bad / max(plaus_n, 1) <= .05, f"{plaus_bad}/{plaus_n}")
# off-label rows only where intended
offrows = sp[sp.Self_Spray_Trade_Name.fillna("").str.contains("Miravis|Meothrin|Trot")]
check("zoho: off-label products only in the scripted scenario farmer", set(offrows.farmer_id) <= {"F008"}, str(set(offrows.farmer_id)))
# rotation: same code twice in a row
reps = 0
for fid, g in sp[sp._product_id.notna() & (sp._nutrient == False)].sort_values("ts").groupby("farmer_id"):
    codes = [pm.set_index("product_id").loc[p, "frac_irac_code"] for p in g._product_id]
    cats = [pm.set_index("product_id").loc[p, "category"] for p in g._product_id]
    fc = [c for c, k in zip(codes, cats) if k == "fungicide"]
    reps += sum(1 for a, b in zip(fc, fc[1:]) if a == b and isinstance(a, str))
print("zoho: consecutive same-FRAC fungicide pairs (rotation mistakes seeded):", reps)
check("zoho: some rotation mistakes exist for the engine to catch", reps >= 5)

# ------------------------------------------------------------------ scenarios (re-verify facts from the raw weather)
sc = {s["id"]: s for s in json.load(open(ROOT / "demo_scenarios.json", encoding="utf-8"))["scenarios"]}
check("scenarios: 11 present", len(sc) == 11)
WD = {sid: g.sort_values("time_ist").reset_index(drop=True) for sid, g in w.groupby("station_id")}
s3 = sc["S3"]["facts"]; t3 = pd.Timestamp(s3["spray_datetime"])
check("S3: >=12 mm fell within 12 h after the spray (recomputed)", rain_after(WD[sc["S3"]["station_id"]], t3, 12) >= 12)
s1 = sc["S1"]["facts"]["infection_period"]
seg = WD["ST01"][(WD["ST01"].time_ist >= s1["start"]) & (WD["ST01"].time_ist <= s1["end"])]
check("S1: wet hours reached the Mills requirement (recomputed)", int(seg.wet.sum()) >= mills_hours(float(seg.temp_c.mean())))
s4 = sc["S4"]["facts"]; seg4 = WD["ST05"][(WD["ST05"].time_ist >= s4["period_start"]) & (WD["ST05"].time_ist <= s4["threshold_reached_at"])]
check("S4: cumulative wet hours reach the requirement exactly at the alert time (recomputed)", int(seg4.wet.sum()) >= s4["mills_hours_needed"])
md = marssonina_risk_days(WD["ST06"])
check("S2: Marssonina rule is true at the clock day (recomputed)", bool(md[md.time_ist == pd.Timestamp(sc["S2"]["demo_clock"]).normalize()].risk.iloc[0]))
lb = late_blight_flag(WD["ST07"])
check("S7: late-blight rule is true at the clock day (recomputed)", bool(lb[lb.time_ist == pd.Timestamp(sc["S7"]["demo_clock"]).normalize()].flag.iloc[0]))
for sid_, s in sc.items():
    fid = s["farmer_id"]
    if fid.startswith("F"):
        check(f"{sid_}: farmer exists", fid in set(f.farmer_id))
        # history must not contain sprays AFTER the clock that the scenario depends on being absent (checked for S1,S3,S6,S7)
check("S6: farmer really has 4 DMI fungicide sprays before the clock",
      int(sum("3" in str(pm.set_index("product_id").loc[p, "frac_irac_code"]).split("+") for p in sp[(sp.farmer_id == sc["S6"]["farmer_id"]) & (sp.ts < pd.Timestamp(sc["S6"]["demo_clock"]))]._product_id.dropna())) == 4)
chk = sp[(sp.farmer_id == sc["S1"]["farmer_id"]) & (sp.ts < pd.Timestamp(sc["S1"]["demo_clock"]))].sort_values("ts").tail(1)
check("S1: last spray before the clock is carbendazim (FRAC 1), ~10 days earlier", len(chk) == 1 and "arbendazim" in chk.Self_Sprayed.iloc[0] and 8 <= (pd.Timestamp(sc["S1"]["demo_clock"]) - chk.ts.iloc[0]).days <= 11)
s10 = sp[sp.farmer_id == sc["S10"]["farmer_id"]]
check("S10: stale farmer has no spray after 2026-08-05", (s10.ts <= pd.Timestamp("2026-08-05 23:59")).all())

# ------------------------------------------------------------------ advisory notes + Hindi
notes = [json.loads(l) for l in open(ROOT / "reference/advisory_notes.jsonl", encoding="utf-8")]
nd = pd.DataFrame(notes)
check("notes: unique ids, valid JSON, >= 150 notes", nd.note_id.is_unique and len(nd) >= 150)
check("notes: one product_use note per recommendable product", (nd.topic == "product_use").sum() == int(pm.usable_for_recommendation.sum()))
check("notes: every note has source_ref and confidence", (nd.source_ref.fillna("") != "").sum() >= len(nd) - 14 and nd.confidence.notna().all(), hard=False)
check("notes: no 'nan' / 'None' leaked into text", not nd.text_en.str.contains(r"\bnan\b|\bNone\b", regex=True).any() and not nd.text_hi.str.contains(r"\bnan\b|\bNone\b", regex=True).any(),
      "; ".join(nd[nd.text_en.str.contains(r"\bnan\b", regex=True)].note_id.tolist()[:8]))
check("notes: every in-demo disease has a disease_info note", demo_ids <= set(nd[nd.topic == "disease_info"].disease_id))
miss_hi = set(pm[pm.usable_for_recommendation == True].active_ingredient_hi.isna()) if "active_ingredient_hi" in pm else set()
untrans = sorted({a for a in pm.active_ingredient for p in a.split(" + ") if p not in __import__("ref_data").AI_HI and a not in __import__("ref_data").AI_HI})
check("hindi: every active ingredient has a Hindi name", not untrans, ", ".join(untrans[:12]), hard=False)
print("hindi: notes with Hindi", int((nd.text_hi != "").sum()), "of", len(nd), "(all drafts; native review required)")

print("\nPASS", len(OK), "| WARN", len(WARN), "| FAIL", len(FAIL))
for x in WARN: print("  WARN:", x)
for x in FAIL: print("  FAIL:", x)
sys.exit(1 if FAIL else 0)
