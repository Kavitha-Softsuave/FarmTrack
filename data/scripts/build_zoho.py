# -*- coding: utf-8 -*-
"""Mock Zoho CRM data in the client's REAL shape (columns read from the 16 Oct 2026 screenshot), FABRICATED content.

Outputs
  mock_zoho/advisory_rows_flat.csv   one row per Advisory-table row (client columns + hidden helper columns prefixed '_')
  mock_zoho/contacts.json            Zoho-API-like Contacts with Advisory / Variety_Mix / Nutrition / Notes sub-lists
  demo_scenarios.json                scripted demo stories, anchored to REAL weather events found in the archive

Assumptions (marked I): API field names, the meaning of 'Name' and 'F.T.A Frac Group' (advisor recommendation), mm as the rainfall unit.
Sprays follow the HP 2026 stage calendar and real weather; discipline (diligent/average/lax) drives mess and rotation mistakes.
"""
import json, datetime as dt
import numpy as np, pandas as pd
from weather_rules import *

rng = np.random.default_rng(20261021)
END = pd.Timestamp("2026-10-17 23:00")
STAFF_ID = {"Aman Verma": "8800000001", "Pooja Thakur": "8800000002", "Ravi Negi": "8800000003", "Deepak Rana": "8800000004", "Sneha Sharma": "8800000005"}

farmers = pd.read_csv(ROOT / "farmers.csv")
prod = pd.read_csv(ROOT / "reference" / "product_master.csv")
cal = pd.read_csv(ROOT / "reference" / "stage_calendar.csv")
stations = pd.read_csv(ROOT / "weather" / "stations.csv")
w = load_weather()
WD = {sid: g.sort_values("time_ist").reset_index(drop=True) for sid, g in w.groupby("station_id")}
DRAIN = {sid: g.set_index("time_ist")["rain_mm"].resample("D").sum() for sid, g in WD.items()}

def band_stage_doy(band, stage, cultivar=""):
    r = cal[(cal.band_id == band) & (cal.stage_id == stage) & (cal.cultivar.fillna("") == cultivar)]
    return int(r.iloc[0].typical_doy)
def doy_ts(doy, hour=9):
    return pd.Timestamp("2026-01-01") + pd.Timedelta(days=int(doy) - 1, hours=hour)

APPLE = prod[prod.crop == "Apple"]
def pick_product(crop, stage=None, category=None, active=None, form=None, stages=None):
    q = prod[prod.crop == crop]
    if stage: q = q[q.stage == stage]
    if stages: q = q[q.stage.isin(stages)]
    if category: q = q[q.category == category]
    if active: q = q[q.active_ingredient == active]
    if form: q = q[q.formulation.fillna("").str.contains(form, regex=False)]
    return q

# ---------------------------------------------------------------- formatting helpers (the client's mess)
def chem_text(p, disc):
    ai, fm = p.active_ingredient, (p.formulation if isinstance(p.formulation, str) else "")
    opts = [ai, f"{ai} {fm}".strip(), ai.lower(), f"{ai} {fm}".strip().lower()]
    wts = [.35, .35, .15, .15] if disc != "lax" else [.2, .25, .3, .25]
    return str(rng.choice(opts, p=wts))
def frac_text(p):
    code = p.frac_irac_code if isinstance(p.frac_irac_code, str) else ""
    if not code: return ""
    if p.category in ("insecticide", "acaricide"): return "IRAC " + code
    out = code.replace("+", " + ")
    if rng.random() < .35: out = out.replace("M0", "M")
    return out
def trade_text(p):
    b = p.brand_example if isinstance(p.brand_example, str) else ""
    if "/" in b: b = rng.choice([x.strip() for x in b.split("/")])
    return b
def fmt_date(ts): return ts.strftime("%d/%m/%Y")
def fmt_dt(ts): return ts.strftime("%d/%m/%Y %I:%M %p")

ROWS = []
def add_row(fid, kind, ts, p=None, text=None, frac=None, trade=None, advice_ts=None, scenario="", nutrient=False, disc="average", clean=False):
    """kind: self_spray | advisor. Messiness (blank cells etc.) is applied unless clean=True."""
    miss = 0 if clean else {"diligent": .08, "average": .2, "lax": .38}[disc]
    r = dict(farmer_id=fid, row_kind=kind, Name="", F_T_A_Frac_Group="", Self_Spray_Dt="", Self_Sprayed="", Self_Spray_Frac_Group="",
             Self_Spray_Trade_Name="", Date_Time_1="", Total_Rainfall_Since_Last_Spray="",
             _spray_datetime=ts.isoformat() if ts is not None else "", _product_id=(p.product_id if p is not None else ""),
             _stage=(p.stage if p is not None else ""), _nutrient=str(nutrient).lower(), _scenario=scenario)
    if kind == "self_spray":
        r["Self_Spray_Dt"] = fmt_date(ts) if (rng.random() > (miss * .12) or clean) else ""
        r["Self_Sprayed"] = text if text is not None else chem_text(p, disc)
        fr = frac if frac is not None else (frac_text(p) if p is not None else "")
        r["Self_Spray_Frac_Group"] = fr if (rng.random() > miss or clean) else ""
        tr = trade if trade is not None else (trade_text(p) if p is not None else "")
        r["Self_Spray_Trade_Name"] = tr if (rng.random() > miss * .8 or clean) else ""
    else:  # advisor recommendation row (assumed meaning of Name + F.T.A Frac Group)
        r["Name"] = trade if trade else (p.brand_example.split("/")[0].strip() if isinstance(p.brand_example, str) and p.brand_example else p.active_ingredient)
        r["F_T_A_Frac_Group"] = frac if frac is not None else frac_text(p)
        r["Date_Time_1"] = fmt_dt(advice_ts if advice_ts is not None else ts)
    ROWS.append(r)

# ---------------------------------------------------------------- baseline generation
POP = {  # stage -> {(active, formulation-substring): weight}
 "green_tip": {("Captan", "50"): 4, ("Dodine", "65"): 1.2, ("Ziram", "27"): 1, ("Fluxapyroxad + Difenoconazole", ""): .3},
 "pink_bud": {("Mancozeb", "75"): 4, ("Propineb", ""): 1.5, ("Difenoconazole", ""): 2, ("Hexaconazole + Zineb", ""): .8},
 "petal_fall": {("Carbendazim", "50"): 3.5, ("Myclobutanil", ""): 3, ("Hexaconazole", "5 EC"): 2, ("Carbendazim + Mancozeb", ""): 3,
                ("Thiophanate-methyl", ""): .8, ("Flusilazole", ""): 1, ("Mancozeb + Pyraclostrobin", ""): .6, ("Metiram", ""): 1.5,
                ("Tebuconazole + Trifloxystrobin", ""): .4, ("Tebuconazole + Captan", ""): .5, ("Boscalid + Pyraclostrobin", ""): .2,
                ("Metrafenone", ""): .2, ("Carbendazim + Flusilazole", ""): .8, ("Chlorothalonil + Difenoconazole", ""): .2},
 "walnut_size": {("Mancozeb", ""): 3, ("Propineb", ""): 1.5, ("Metiram", "70"): 3, ("Metiram + Pyraclostrobin", ""): .8, ("Tebuconazole + Captan", "8%"): 1.2,
                 ("Dodine", ""): .8, ("Hexaconazole + Zineb", ""): 1, ("Fluopyram + Tebuconazole", ""): .4, ("Fluxapyroxad + Pyraclostrobin", ""): .3,
                 ("Tebuconazole + Captan", "6.7"): .4},
 "walnut_plus_20d": {("Metiram", ""): 3, ("Propineb", ""): 2, ("Zineb", ""): 1.5, ("Mancozeb + Pyraclostrobin", ""): .7, ("Carbendazim + Flusilazole", ""): 1,
                     ("Tebuconazole + Trifloxystrobin", ""): .6, ("Chlorothalonil + Difenoconazole", ""): .5},
 "pre_harvest": {("Captan", ""): 3, ("Ziram", ""): 2, ("Metiram + Pyraclostrobin", ""): .6, ("Hexaconazole + Zineb", ""): 1, ("Fluopyram + Tebuconazole", ""): .3},
}
def weighted_choice(cands, stage, last_code, disc, dmi_count):
    wt = []
    for _, p in cands.iterrows():
        base = 1.0
        for (ai, fm), v in POP.get(stage, {}).items():
            if p.active_ingredient == ai and fm in (p.formulation if isinstance(p.formulation, str) else ""):
                base = v; break
        code = p.frac_irac_code if isinstance(p.frac_irac_code, str) else ""
        if last_code and code == last_code and rng.random() < {"diligent": .9, "average": .5, "lax": 0}[disc]: base *= .02
        if disc == "diligent" and dmi_count >= 4 and "3" in code.split("+"): base *= .02
        wt.append(base)
    wt = np.array(wt); wt = wt / wt.sum()
    return cands.iloc[int(rng.choice(len(cands), p=wt))]

def pick_day(sid, base, disc, tries=6):
    mu, sd = {"diligent": (0.5, 1.5), "average": (3, 2.5), "lax": (7, 4)}[disc]
    d = (base + pd.Timedelta(days=int(round(rng.normal(mu, sd))))).normalize()
    for _ in range(tries):
        if disc != "lax" and DRAIN[sid].get(d, 0) >= 3: d += pd.Timedelta(days=1)
        else: break
    return d

def apple_history(f):
    sid, band, disc, cv = f.station_id, f.phenology_band, f.discipline, f.primary_variety
    jit = int(round(rng.normal(0, 2.5)))
    p_stage = {"diligent": .95, "average": .75, "lax": .5}[disc]
    events, last_code, dmi = [], "", 0
    seq = [("green_tip", band_stage_doy(band, "green_tip")), ("pink_bud", band_stage_doy(band, "pink_bud")),
           ("petal_fall", band_stage_doy(band, "petal_fall")), ("walnut_size", band_stage_doy(band, "walnut_size")),
           ("walnut_plus_20d", band_stage_doy(band, "walnut_plus_20d"))]
    harvest_doy = band_stage_doy(band, "harvest", cv) + jit
    # rainy-season extras (Marssonina/Alternaria protectants) in Jul-Aug for mid/low belts
    if band != "B4":
        d0 = band_stage_doy(band, "walnut_plus_20d") + int(rng.integers(14, 22))
        while d0 < harvest_doy - 30:
            seq.append(("rainy_extra", d0)); d0 += int(rng.integers(14, 22 if disc == "diligent" else 30))
    seq.append(("pre_harvest", harvest_doy - 22))
    for stage, doy in seq:
        if rng.random() > p_stage and stage not in ("green_tip",): continue
        ts = doy_ts(doy + jit, hour=int(rng.integers(7, 16)))
        d = pick_day(sid, ts, disc)
        if d + pd.Timedelta(hours=8) > END: continue
        ts = d + pd.Timedelta(hours=int(rng.integers(7, 16)), minutes=int(rng.integers(0, 60)))
        use_stage = "walnut_size" if stage == "rainy_extra" else stage
        c = pick_product("Apple", stage=use_stage, category="fungicide")
        c = c[c.usable_for_recommendation == True]
        if stage == "rainy_extra":
            c = c[c.targets.str.contains("Marssonina|Alternaria")]
        if len(c) == 0: continue
        p = weighted_choice(c, use_stage, last_code, disc, dmi)
        code = p.frac_irac_code if isinstance(p.frac_irac_code, str) else ""
        last_code = code; dmi += int("3" in code.split("+"))
        events.append((ts, p, stage))
    # insecticide / acaricide (diligent farmers follow the oil/mite sprays; lax rarely)
    pi = {"diligent": .7, "average": .4, "lax": .1}[disc]
    for stage, doy_off in (("half_inch_green_tip", 0), ("petal_fall", 3), ("walnut_size", 3), ("walnut_plus_20d", 3), ("pre_harvest", 2)):
        if rng.random() > (pi if stage != "half_inch_green_tip" else pi * .7) * (.25 if stage == "pre_harvest" else 1): continue
        doy = band_stage_doy(band, stage) if stage != "pre_harvest" else harvest_doy - 22
        ts = doy_ts(doy + jit + doy_off, hour=int(rng.integers(7, 16)))
        d = pick_day(sid, ts, disc)
        if d + pd.Timedelta(hours=8) > END: continue
        c = prod[(prod.crop == "Apple") & (prod.stage == stage) & (prod.category.isin(["insecticide", "acaricide", "oil"]))]
        if len(c) == 0: continue
        p = c.iloc[int(rng.integers(0, len(c)))]
        events.append((d + pd.Timedelta(hours=int(rng.integers(7, 16))), p, stage))
    # post harvest copper + mancozeb
    ph = doy_ts(harvest_doy + 7 + jit, 10)
    if ph < END and rng.random() < {"diligent": .6, "average": .3, "lax": .05}[disc]:
        p = pick_product("Apple", stage="post_harvest", category="fungicide").iloc[0]
        events.append((ph, p, "post_harvest"))
    return sorted(events, key=lambda e: e[0])

NUTRIENTS = ["Zinc, Boron", "12.61.00", "Calcium nitrate", "Urea", "Boron"]
for _, f in farmers.iterrows():
    sid, disc = f.station_id, f.discipline
    if f.primary_crop == "Apple":
        ev = apple_history(f)
        for ts, p, stage in ev:
            add_row(f.farmer_id, "self_spray", ts, p, disc=disc)
            if rng.random() < {"diligent": .55, "average": .35, "lax": .1}[disc] and p.category == "fungicide":
                a_ts = ts - pd.Timedelta(days=int(rng.integers(0, 3)), hours=int(rng.integers(0, 5)))
                add_row(f.farmer_id, "advisor", ts, p, advice_ts=a_ts, disc=disc)
            # nutrient entries the same day (client pattern: Zinc, Boron and 12.61.00 on the same date as a fungicide)
            if p.category == "fungicide" and stage in ("pink_bud", "petal_fall") and rng.random() < .22:
                for nut in rng.choice(NUTRIENTS, size=int(rng.integers(1, 3)), replace=False):
                    add_row(f.farmer_id, "self_spray", ts, None, text=str(nut), frac="", trade="", nutrient=True, disc=disc)
    else:
        crop = f.primary_crop
        season = {"Tomato": ("2026-04-28", "2026-09-20"), "Potato": ("2026-04-10", "2026-07-31"), "Maize": ("2026-06-20", "2026-09-05"), "Grape": ("2026-04-12", "2026-08-25")}[crop]
        cands = prod[(prod.crop == crop) & (prod.category.isin(["fungicide", "acaricide", "insecticide"]))]
        d = pd.Timestamp(season[0]) + pd.Timedelta(days=int(rng.integers(0, 14)))
        step = {"diligent": (9, 13), "average": (12, 19), "lax": (16, 30)}[disc]
        if crop == "Maize": step = (14, 25)
        while d < pd.Timestamp(season[1]):
            p = cands.iloc[int(rng.integers(0, len(cands)))]
            ts = d + pd.Timedelta(hours=int(rng.integers(7, 16)))
            if ts < END: add_row(f.farmer_id, "self_spray", ts, p, disc=disc)
            d += pd.Timedelta(days=int(rng.integers(*step)))

ROWS_BASE = len(ROWS)
print("baseline advisory rows:", ROWS_BASE)

# ================================================================================ scenarios
SC = []
def fa(sid, crop="Apple", k=0, disc=None, band=None):
    q = farmers[(farmers.station_id == sid) & (farmers.primary_crop == crop)]
    if disc: q = q[q.discipline == disc]
    if band: q = q[q.phenology_band == band]
    return q.iloc[k]
def drop_farmer_rows(fid):
    global ROWS
    ROWS = [r for r in ROWS if r["farmer_id"] != fid]
def sp(fid, ts, active=None, form=None, stage=None, crop="Apple", text=None, frac=None, trade=None, tag="", nutrient=False, category=None):
    p = None
    if active:
        q = pick_product(crop, stage=stage, active=active, form=form, category=category)
        if len(q) == 0: raise SystemExit(f"no product {active} {form} {stage} {crop}")
        p = q.iloc[0]
    add_row(fid, "self_spray", pd.Timestamp(ts), p, text=text, frac=frac, trade=trade, scenario=tag, nutrient=nutrient, clean=True)
def facts_wx(sid, t0, hours_back=0, hours_ahead=12):
    ws = WD[sid]
    return dict(rain_next_12h_mm=round(rain_after(ws, t0, 12), 1), rain_next_48h_mm=round(rain_after(ws, t0, 48), 1),
                rain_prev_24h_mm=round(rain_between(ws, t0 - pd.Timedelta(hours=24), t0), 1))

# ---- S1: scab at petal fall, offline scan; carbendazim (FRAC 1) sprayed 10 days earlier ------------------------------
f1 = fa("ST01", k=0); fid = f1.farmer_id; drop_farmer_rows(fid)
pf = doy_ts(band_stage_doy(f1.phenology_band, "petal_fall"), 0)
cands = [p for p in scab_infection_periods(WD["ST01"][(WD["ST01"].time_ist >= pf - pd.Timedelta(days=2)) & (WD["ST01"].time_ist <= pf + pd.Timedelta(days=16))]) if p["infection"]]
best = max(cands, key=lambda p: p["wet_hours"] - (p["need_hours"] or 0))
clock1 = (best["end"] + pd.Timedelta(hours=1)).replace(minute=0)
sp(fid, doy_ts(band_stage_doy("B3", "green_tip") + 2, 10), "Captan", "50", "green_tip", trade="Captaf", tag="S1")
sp(fid, doy_ts(band_stage_doy("B3", "pink_bud") + 1, 11), "Mancozeb", "75", "pink_bud", trade="Indofil M-45", tag="S1")
sp(fid, clock1 - pd.Timedelta(days=10, hours=-1), "Carbendazim", "50", "petal_fall", text="Carbendazim", frac="1", trade="Bavistin", tag="S1")
SC.append(dict(id="S1", title="Scab at petal fall, scanned offline, carbendazim used 10 days ago", farmer_id=fid, station_id="ST01", crop="Apple",
    demo_clock=str(clock1), diagnosis_expected="Apple___Apple_scab (on-device model; works offline)", photo_note="Any public apple-scab leaf (PlantDoc 'Apple Scab Leaf' CC-BY-4.0 or PlantVillage).",
    facts=dict(infection_period=dict(start=str(best["start"]), end=str(best["end"]), wet_hours=best["wet_hours"], mills_hours_needed=best["need_hours"], mean_temp_c=best["mean_temp_c"], rain_mm=best["rain_mm"]),
               last_spray="Carbendazim (Bavistin), FRAC 1, 10 days before the clock", **facts_wx("ST01", clock1)),
    expected_behaviour=["Offline: on-device result + cached basic advice card for scab", "Online: recommend a petal-fall scab product that is NOT FRAC 1 (e.g. myclobutanil 80 g/200 L, waiting period 21 days)",
                        "Show waiting period vs days to harvest; spray-timing advice from the next-12h rain figure above"]))

# ---- S2: Marssonina weather, July, Kullu --------------------------------------------------------------------------------
md = marssonina_risk_days(WD["ST06"]); first = md.loc[md.risk, "time_ist"].min()
f2 = fa("ST06", k=0); fid = f2.farmer_id; drop_farmer_rows(fid)
clock2 = (first + pd.Timedelta(days=2, hours=8))
sp(fid, doy_ts(band_stage_doy(f2.phenology_band, "petal_fall"), 10), "Myclobutanil", "", "petal_fall", trade="Systhane", tag="S2")
sp(fid, doy_ts(band_stage_doy(f2.phenology_band, "walnut_size"), 10), "Mancozeb", "75", "walnut_size", trade="Dithane M-45", tag="S2")
sp(fid, clock2 - pd.Timedelta(days=15, hours=-1), "Propineb", "70", "walnut_size", tag="S2")
mdc = md[md.time_ist <= clock2.normalize()].tail(5)
SC.append(dict(id="S2", title="Marssonina blotch weather in July: the on-device model has no Marssonina class, so the server apple model is needed", farmer_id=fid, station_id="ST06", crop="Apple",
    demo_clock=str(clock2), diagnosis_expected="Apple___Marssonina_blotch (server model ixrbhii/apple-disease-convnext only)",
    photo_note="NO openly downloadable Marssonina photo set exists (Khan et al. 2020 not public). Ask the client for Marssonina photos; until then demo with a model-card example.",
    facts=dict(marssonina_rule_first_true_day=str(first.date()), last_5_days=[dict(day=str(r.time_ist.date()), mean_temp_c=round(r.temp, 1), mean_rh_pct=round(r.rh, 0), rain_mm=round(r.rain, 1)) for r in mdc.itertuples()],
               **facts_wx("ST06", clock2)),
    expected_behaviour=["On-device model cannot name Marssonina (no such class): expect a wrong class or low confidence -> 'not sure, checking online'", "Server model (untested on field photos): if it returns Marssonina -> advice from Nauni July 2026 advisory (metiram 600 g/200 L protectant)",
                        "Weather-risk badge 'Marssonina/Alternaria weather' is red"]))

# ---- S3: rain wash-off ---------------------------------------------------------------------------------------------------
# Search real weather for a dry morning spray followed by >=12 mm within 12 h, inside a window where a mancozeb spray is a
# recognised HP-2026 stage for that farmer's band (pink bud or walnut size), so the stage label is truthful.
found = None
for sid in ["ST01", "ST02", "ST04", "ST05", "ST11", "ST12", "ST06"]:
    for _, cand in farmers[(farmers.station_id == sid) & (farmers.primary_crop == "Apple")].iterrows():
        b = cand.phenology_band
        wins = [("pink_bud", band_stage_doy(b, "pink_bud")), ("walnut_size", band_stage_doy(b, "walnut_size"))]
        ws = WD[sid]
        for stg, d0 in wins:
            for day in pd.date_range(doy_ts(d0 - 5, 0), doy_ts(d0 + 14, 0)):
                for hr in range(8, 15):
                    t = day + pd.Timedelta(hours=hr)
                    if rain_after(ws, t, 12) >= 12 and rain_between(ws, t - pd.Timedelta(hours=12), t) < 1 and rain_after(ws, t, 2) < 0.5:
                        found = (sid, t, cand.farmer_id, stg); break
                if found: break
            if found: break
        if found: break
    if found: break
sid3, t3, fid, stg3 = found; f3 = farmers[farmers.farmer_id == fid].iloc[0]; drop_farmer_rows(fid)
b3 = f3.phenology_band
sp(fid, doy_ts(band_stage_doy(b3, "green_tip") + 2, 10), "Captan", "50", "green_tip", tag="S3")
if stg3 == "walnut_size":
    sp(fid, doy_ts(band_stage_doy(b3, "pink_bud") + 1, 10), "Mancozeb", "75", "pink_bud", trade="Indofil M-45", tag="S3")
    sp(fid, doy_ts(band_stage_doy(b3, "petal_fall") + 1, 10), "Myclobutanil", "", "petal_fall", trade="Systhane", tag="S3")
sp(fid, t3, "Mancozeb", "75", stg3, trade="Indofil M-45", tag="S3")
rain12 = rain_after(WD[sid3], t3, 12)
SC.append(dict(id="S3", title="Heavy rain right after a mancozeb spray -> automatic 're-spray within 7 days' alert", farmer_id=fid, station_id=sid3, crop="Apple",
    demo_clock=str(t3 + pd.Timedelta(hours=12)), diagnosis_expected="(no scan; automatic alert)", photo_note="n/a",
    facts=dict(spray_datetime=str(t3), spray_stage=stg3, rain_in_12h_after_spray_mm=round(rain12, 1), rain_first_2h_mm=round(rain_after(WD[sid3], t3, 2), 1), heavy_rain_threshold_mm_config=10),
    expected_behaviour=["Push alert at the clock time: heavy rain within 12 h of spraying -> repeat the spray within 7 days (HP 2026 rule)", "Mark the spray as 'washed off' in the diary and write the note back to Zoho"]))

# ---- S4: scab infection alert for a whole block --------------------------------------------------------------------------
ws = WD["ST05"]; fl = doy_ts(band_stage_doy("B3", "pink_bud"), 0); fe = doy_ts(band_stage_doy("B3", "petal_fall") + 21, 0)
inf = [p for p in scab_infection_periods(ws[(ws.time_ist >= fl) & (ws.time_ist <= fe)]) if p["infection"]]
b4 = max(inf, key=lambda p: p["wet_hours"] - (p["need_hours"] or 0) + 0.2 * p["rain_mm"])
seg = ws[(ws.time_ist >= b4["start"]) & (ws.time_ist <= b4["end"])].reset_index(drop=True)
cum = seg.wet.cumsum(); need = b4["need_hours"]; hit = seg.time_ist[cum >= need].iloc[0]
n_ap = int(((farmers.station_id == "ST05") & (farmers.primary_crop == "Apple")).sum())
SC.append(dict(id="S4", title="Scab infection period reached the Mills threshold -> automatic alert to every apple farmer in the Jubbal block", farmer_id="(all apple farmers at ST05)", station_id="ST05", crop="Apple",
    demo_clock=str(hit), diagnosis_expected="(no scan; automatic alert)", photo_note="n/a",
    facts=dict(period_start=str(b4["start"]), period_end=str(b4["end"]), wet_hours_total=b4["wet_hours"], mills_hours_needed=need, mean_temp_c=b4["mean_temp_c"], rain_mm=b4["rain_mm"],
               threshold_reached_at=str(hit), apple_farmers_alerted=n_ap),
    expected_behaviour=["Alert fires at the moment cumulative leaf-wetness hours reach the Mills requirement", "Each farmer's message names their own last spray and avoids repeating its chemical group"]))

# ---- S5: off-label products from the client's real Zoho rows ------------------------------------------------------------
f5 = fa("ST02", k=0, band="B1"); fid5 = f5.farmer_id; f9 = fa("ST02", k=1, band="B1"); fid9 = f9.farmer_id
drop_farmer_rows(fid5)
sp(fid5, "2026-04-14 10:30", "Carbendazim", "50", "petal_fall", text="Carbendazim", frac="1", trade="Bavistin", tag="S5")
sp(fid5, "2026-05-30 11:00", None, text="Fenpropathrin 30% EC", frac="IRAC 3A", trade="Meothrin", tag="S5")
sp(fid5, "2026-06-06 10:00", "Carbendazim + Mancozeb", "12%", "petal_fall", text="Carbendazim 12% + Mancozeb 63% WP", frac="1 + M03", trade="SAAF", tag="S5")
sp(fid5, "2026-06-17 10:00", "Myclobutanil", "", "petal_fall", text="Myclobutanil", frac="3", trade="Systhane", tag="S5")
sp(fid5, "2026-06-28 09:30", None, text="Pydiflumetofen 6.89% SC Difenoconazole 11.49% SC", frac="7 + 3", trade="Syngenta Miravis Duo", tag="S5")
sp(fid5, "2026-07-26 10:00", None, text="Thiamethoxam 30% FS", frac="IRAC 4A", trade="Trot", tag="S5")
SC.append(dict(id="S5", title="Off-label products found in the farmer's Zoho history (copied from the client's real rows)", farmer_id=fid5, station_id="ST02", crop="Apple",
    demo_clock="2026-07-27 09:00", diagnosis_expected="(admin dashboard / history review)", photo_note="n/a",
    facts=dict(flagged=["Syngenta Miravis Duo (not approved for apple: tomato, chilli, groundnut, grape)", "Meothrin / fenpropathrin 30% EC (no apple label claim)", "Trot / thiamethoxam 30% FS (seed treatment, not a foliar spray)"]),
    expected_behaviour=["Admin 'data quality' view flags the three rows as off-label for apple", "The recommendation engine never proposes them; farmer sees a gentle warning"]))

# ---- S9: client's same-day pattern: carbendazim + Zinc/Boron + 12.61.00 on 14/04/2026 ---------------------------------------
drop_farmer_rows(fid9)
sp(fid9, "2026-04-14 10:00", "Carbendazim", "50", "petal_fall", text="Carbendazim", frac="1", trade="Bavistin", tag="S9")
sp(fid9, "2026-04-14 10:05", None, text="Zinc, Boron", frac="", trade="", tag="S9", nutrient=True)
sp(fid9, "2026-04-14 10:10", None, text="12.61.00", frac="", trade="", tag="S9", nutrient=True)
sp(fid9, "2026-05-03 10:00", "Myclobutanil", "", "petal_fall", text="Myclobutanil", frac="3", trade="Systhane", tag="S9")
SC.append(dict(id="S9", title="Micronutrients logged the same day as a fungicide (the client's own 14/04/2026 pattern)", farmer_id=fid9, station_id="ST02", crop="Apple",
    demo_clock="2026-04-15 09:00", diagnosis_expected="(spray-diary check)", photo_note="n/a",
    facts=dict(same_day_rows=["Carbendazim (FRAC 1)", "Zinc, Boron", "12.61.00"], hp2026_rule="HP 2026 point 7: do not mix any other pesticide/chemical/micro-nutrient/growth regulator/hormone with the recommended pesticides (russeting and other disorders); spray separately when necessary"),
    expected_behaviour=["Diary shows an amber note: 'Zinc/Boron and 12-61-00 were logged with a fungicide the same day. HP 2026 says to spray micronutrients separately, not mixed with the recommended pesticides.' (the data cannot tell a tank-mix from separate sprays)"]))

# ---- S6: DMI limit reached ---------------------------------------------------------------------------------------------------
f6 = fa("ST04", k=0, band="B2"); fid = f6.farmer_id; drop_farmer_rows(fid)
sp(fid, doy_ts(band_stage_doy("B2", "pink_bud"), 10), "Difenoconazole", "25", "pink_bud", trade="Score", tag="S6")
sp(fid, doy_ts(band_stage_doy("B2", "petal_fall"), 10), "Myclobutanil", "", "petal_fall", trade="Systhane", tag="S6")
sp(fid, doy_ts(band_stage_doy("B2", "petal_fall") + 8, 10), "Flusilazole", "", "petal_fall", tag="S6")
sp(fid, doy_ts(band_stage_doy("B2", "walnut_size"), 10), "Tebuconazole + Captan", "8%", "walnut_size", trade="Shamir", tag="S6")
clock6 = doy_ts(band_stage_doy("B2", "walnut_plus_20d") - 3, 8)
SC.append(dict(id="S6", title="Four DMI (FRAC 3) sprays already used -> next recommendation must avoid DMI", farmer_id=fid, station_id="ST04", crop="Apple",
    demo_clock=str(clock6), diagnosis_expected="Apple___Marssonina_blotch or Apple___Alternaria_leaf_spot", photo_note="Server apple model only.",
    facts=dict(dmi_sprays_so_far=4, products=["difenoconazole", "myclobutanil", "flusilazole", "tebuconazole + captan"], frac_limit="DMI <= 4 per season, alone or in mixture (FRAC pome-fruit guidance)", **facts_wx("ST04", clock6)),
    expected_behaviour=["Engine excludes every product containing FRAC 3 (incl. mixtures)", "Offers non-DMI options such as propineb / metiram, or metiram + pyraclostrobin (QoI count still 0)"]))

# ---- S7: potato late blight, NIPHM rule ----------------------------------------------------------------------------------------
f7 = fa("ST07", crop="Potato", k=0); fid = f7.farmer_id; drop_farmer_rows(fid)
lb = late_blight_flag(WD["ST07"]); lb = lb[(lb.time_ist >= "2026-06-15") & (lb.time_ist <= "2026-08-20")].reset_index(drop=True)
on = None
for i in range(3, len(lb)):
    if lb.flag[i] and not lb.flag[i - 1] and not lb.flag[i - 2] and not lb.flag[i - 3]: on = lb.time_ist[i]; break
if on is None: on = lb.time_ist[lb.flag.idxmax()]
clock7 = on + pd.Timedelta(hours=8)
pm = prod[(prod.crop == "Potato") & (prod.active_ingredient == "Mancozeb") & (prod.targets.str.contains("Late_blight"))].iloc[0]
for off in (-44, -29, -13):
    add_row(fid, "self_spray", (clock7 + pd.Timedelta(days=off)).replace(hour=10), pm, scenario="S7", clean=True)
r = lb[lb.time_ist == on].iloc[0]
SC.append(dict(id="S7", title="Potato late-blight weather (NIPHM 7-day rule) turns true -> automatic alert and advice", farmer_id=fid, station_id="ST07", crop="Potato",
    demo_clock=str(clock7), diagnosis_expected="Potato___Late_blight (on-device model) or alert only", photo_note="PlantVillage / PlantDoc potato late blight image.",
    facts=dict(rule_turned_true_on=str(on.date()), hours_temp_7p2_to_26p6_last7d=int(r.hrs_temp), hours_rh_gt85_last7d=int(r.hrs_rh), thresholds=dict(temp_hours=115, rh_hours=90), last_spray="mancozeb 13 days earlier"),
    expected_behaviour=["Alert: late blight expected within 10 days", "Advice: mancozeb 2 kg/ha in 1000 L as protectant (every ~10 days); cymoxanil + mancozeb 3 kg/ha only if symptoms are already visible"]))

# ---- S8: tomato yellow leaf curl virus -> no cure -------------------------------------------------------------------------------------------
f8 = fa("ST11", crop="Tomato", k=0); fid = f8.farmer_id
clock8 = pd.Timestamp("2026-06-24 08:00")
SC.append(dict(id="S8", title="Tomato yellow leaf curl virus: no cure, only vector control + roguing", farmer_id=fid, station_id="ST11", crop="Tomato",
    demo_clock=str(clock8), diagnosis_expected="Tomato___Tomato_Yellow_Leaf_Curl_Virus (on-device)", photo_note="PlantVillage tomato YLCV image.",
    facts=dict(weather_at_clock=facts_wx("ST11", clock8)),
    expected_behaviour=["Card says 'no cure' in plain words; NO fungicide is offered", "Shows whitefly control (imidacloprid 150-175 ml/ha, waiting period 3 d) and roguing, yellow traps (10 per acre), net nursery"]))

# ---- S10: stale record ------------------------------------------------------------------------------------------------------------------------
f10 = fa("ST03", k=0, disc="lax") if len(farmers[(farmers.station_id == "ST03") & (farmers.discipline == "lax")]) else fa("ST03", k=0)
fid = f10.farmer_id
ROWS = [r for r in ROWS if not (r["farmer_id"] == fid and r["_spray_datetime"] and pd.Timestamp(r["_spray_datetime"]) > pd.Timestamp("2026-08-05"))]
SC.append(dict(id="S10", title="Stale Zoho record (last update > 60 days) -> advice asks the farmer to confirm recent sprays", farmer_id=fid, station_id="ST03", crop="Apple",
    demo_clock="2026-10-17 09:00", diagnosis_expected="(any scan)", photo_note="n/a", facts=dict(last_spray_on_or_before="2026-08-05", days_stale_at_clock=73),
    expected_behaviour=["Before recommending, the app asks 'Did you spray after 5 Aug?' (checkbox) so rotation and waiting-period logic uses current data"]))

# ---- S11: station offline -----------------------------------------------------------------------------------------------------------------------
SC.append(dict(id="S11", title="Sensor station offline: 'My field' shows a stale-data warning, alerts are marked 'based on forecast only'", farmer_id="(all farmers at ST08, Sangla)", station_id="ST08", crop="Apple",
    demo_clock="2026-07-12 09:00", diagnosis_expected="(no scan)", photo_note="n/a", facts=dict(offline_from="2026-07-10 06:00", offline_until="2026-07-14 18:00", hours=109),
    expected_behaviour=["Last reading is >48 h old -> amber 'sensor offline since 10 Jul' banner", "Automatic alerts fall back to the weather-API forecast and say so"]))

# ================================================================================ finalise
df = pd.DataFrame(ROWS)
df["_ts"] = pd.to_datetime(df["_spray_datetime"], errors="coerce")

# rainfall since each fungicide spray (until the next fungicide spray / season end), filled for ~15% of rows (field staff rarely fill it)
st_of = dict(zip(farmers.farmer_id, farmers.station_id))
for fid, g in df[(df.row_kind == "self_spray") & (df._nutrient == "false") & (df._product_id != "")].groupby("farmer_id"):
    g = g.sort_values("_ts"); ts = list(g._ts); idx = list(g.index)
    for i, ix in enumerate(idx):
        nxt = ts[i + 1] if i + 1 < len(ts) else END
        if rng.random() < .15 or df.at[ix, "_scenario"] in ("S3",):
            df.at[ix, "Total_Rainfall_Since_Last_Spray"] = str(round(rain_between(WD[st_of[fid]], ts[i], nxt), 1))

# partial out-of-date-order rows: shuffle ~35% of farmers' rows
parts = []
for fid, g in df.groupby("farmer_id", sort=False):
    g = g.sort_values("_ts", na_position="last")
    if rng.random() < .35: g = g.sample(frac=1, random_state=int(rng.integers(0, 1_000_000)))
    parts.append(g)
df = pd.concat(parts).drop(columns=["_ts"]).reset_index(drop=True)
(ROOT / "mock_zoho").mkdir(exist_ok=True)
cols = ["farmer_id", "row_kind", "Name", "F_T_A_Frac_Group", "Self_Spray_Dt", "Self_Sprayed", "Self_Spray_Frac_Group", "Self_Spray_Trade_Name",
        "Date_Time_1", "Total_Rainfall_Since_Last_Spray", "_spray_datetime", "_product_id", "_stage", "_nutrient", "_scenario"]
df[cols].to_csv(ROOT / "mock_zoho" / "advisory_rows_flat.csv", index=False, encoding="utf-8-sig")

# ---- contacts.json (Zoho-API-like)
NOTE_TPL = ["Called farmer, scab seen on lower leaves. Advised spray.", "Visited orchard. Leaf drop starting, sent photos.", "Farmer asked about rain and re-spray.",
            "Reminded to avoid mixing micronutrients with fungicide.", "Checked sprayer calibration, 200 L tank used.", "Farmer reports hail on one block.",
            "Advised sanitation: collect fallen leaves.", "Asked farmer to send photos of affected leaves on WhatsApp."]
contacts = []
for _, f in farmers.iterrows():
    g = df[df.farmer_id == f.farmer_id]
    first, last = f["name"].split(" ", 1)[0], f["name"].split(" ", 1)[1]
    last_ts = pd.to_datetime(g["_spray_datetime"], errors="coerce").max()
    mod = last_ts + pd.Timedelta(days=int(rng.integers(0, 4))) if pd.notna(last_ts) else pd.Timestamp("2026-03-20")
    nut = []
    for _ in range(int(rng.integers(1, 4))):
        nut.append(dict(Date=str((pd.Timestamp("2026-03-10") + pd.Timedelta(days=int(rng.integers(0, 190)))).date()),
                        Input=str(rng.choice(["Urea 5% floor spray", "Calcium nitrate", "Boron", "12-61-00", "Zinc sulphate", "FYM (organic)"])), Note=""))
    notes = [dict(Created=str((pd.Timestamp("2026-03-12") + pd.Timedelta(days=int(rng.integers(0, 200)))).date()), Owner=f.field_staff_owner, Text=str(rng.choice(NOTE_TPL)))
             for _ in range(int(rng.integers(2, 7)))]
    contacts.append(dict(
        id=f.zoho_contact_id, First_Name=first, Last_Name=last, Full_Name=f["name"], Mobile=f.phone, Mailing_City=f.village, Mailing_State="Himachal Pradesh",
        District=f.district, Owner=dict(name=f.field_staff_owner, id=STAFF_ID[f.field_staff_owner]), Created_Time=f"2026-03-0{1 + int(f.farmer_id[1:]) % 9}T10:00:00+05:30",
        Modified_Time=str(mod), Primary_Crop=f.primary_crop, Variety_Mix=json.loads(f.variety_mix), Orchard_Area_Acres=f.orchard_area_acres,
        Advisory=[{k: ("" if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items() if not k.startswith("_") and k not in ("farmer_id", "row_kind")}
                  for r in g.to_dict("records")],
        Nutrition=nut, Notes=notes, Attachments_Count=int(rng.integers(0, 9)), _data_origin="FABRICATED_DEMO"))
(ROOT / "mock_zoho" / "contacts.json").write_text(json.dumps(dict(data=contacts, info=dict(count=len(contacts), more_records=False,
    note="Mock of GET /crm/v?/Contacts with a custom 'Advisory' sub-list. Field API names are ASSUMED.")), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
(ROOT / "demo_scenarios.json").write_text(json.dumps(dict(
    _note="Scenarios are anchored to REAL weather found in weather/weather_hourly_raw.csv. 'expected_behaviour' is what the finished app should show; 'facts' are computed from the data.",
    scenarios=SC), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print("total advisory rows:", len(df), "| self_spray:", int((df.row_kind == "self_spray").sum()), "| advisor:", int((df.row_kind == "advisor").sum()), "| scenarios:", len(SC))
for s in SC: print(s["id"], s["farmer_id"], s["station_id"], s["demo_clock"])
