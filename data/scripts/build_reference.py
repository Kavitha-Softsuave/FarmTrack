# -*- coding: utf-8 -*-
"""Build data/reference/*: disease catalogue, product master, off-label list, banned list,
stage calendar, rules config, Hindi glossary. All values come from ref_data.py."""
import csv, json, pathlib, datetime
import ref_data as R

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "reference"
OUT.mkdir(exist_ok=True)

def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:   # BOM so Excel shows Hindi correctly
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})

# ---------------------------------------------------------------- disease catalogue
for d in R.D:
    d["name_hi"] = R.DISEASE_HI.get(d["disease_id"], "")
    d["crop_hi"] = R.CROP_HI.get(d["crop"], "")
    d["hi_status"] = "draft_needs_native_review" if d["name_hi"] else "missing"
dfields = ["disease_id", "kind", "crop", "crop_hi", "name_en", "name_hi", "pathogen_or_pest", "in_demo_scope", "detectable_by",
           "chemical_control", "treat_as", "requires_expert_review", "season", "symptoms", "favourable_weather",
           "non_chemical", "note", "source_ref", "confidence", "hi_status"]
write_csv(OUT / "disease_catalogue.csv", R.D, dfields)

# ---------------------------------------------------------------- product master
CONTACT = {"M01", "M02", "M03", "M04", "M05", "U12", "UNM"}
MIXED = {"11"}
def behaviour(code, category):
    if category not in ("fungicide",) or not code:
        return "not_applicable"
    parts = code.split("+")
    if all(p in CONTACT for p in parts):
        return "contact"
    if any(p in MIXED for p in parts) or (any(p in CONTACT for p in parts) and any(p not in CONTACT for p in parts)):
        return "mixed"
    return "systemic"

def moa_class(code):
    parts = code.split("+") if code else []
    tags = []
    for p in parts:
        tags.append({"3": "DMI", "11": "QoI", "7": "SDHI", "1": "MBC"}.get(p, p))
    return "+".join(tags)

def hi_ai(ai):
    if ai in R.AI_HI:
        return R.AI_HI[ai]
    parts = [p.strip() for p in ai.split("+")]
    out = []
    for p in parts:
        out.append(R.AI_HI.get(p, p))
    return " + ".join(out)

for i, p in enumerate(R.P, 1):
    p["product_id"] = f"P{i:03d}"
    p["behaviour"] = behaviour(p["frac_irac_code"], p["category"])
    p["moa_class"] = moa_class(p["frac_irac_code"])
    p["active_ingredient_hi"] = hi_ai(p["active_ingredient"])
    p["usable_for_recommendation"] = "false" if not p["targets"] else "true"
    p["approved_for_crop_status"] = ("label_listed_HP_2026_schedule" if "HP Dept" in p["source_ref"] else
                                     "label_listed_CIBRC" if "CIB&RC" in p["source_ref"] else "state_university_recommendation")
# ---- link the official HP 2026 evaluated-brand table into the product master
brand_rows = []
def _norm(x): return x if isinstance(x, str) else ""
for g_i, (group, kind, m_ai, m_form, wp, brands) in enumerate(R.BRANDS, 1):
    for bn, comp in brands:
        brand_rows.append(dict(group_id=f"B{g_i:02d}", hp_table_item=group, kind=kind, match_active_ingredient=m_ai, hp_waiting_period_days=wp,
                               brand=bn, company=comp, company_listed="true" if comp else "false",
                               source_ref="HP 2026 'Pesticides formulations recommended and evaluated' table (PDF pp. 8-11), read from rendered pages 19 Oct 2026", confidence="V"))
write_csv(OUT / "brand_master.csv", brand_rows, ["group_id", "hp_table_item", "kind", "match_active_ingredient", "hp_waiting_period_days", "brand", "company", "company_listed", "source_ref", "confidence"])
def link_brands(p):
    if p["crop"] != "Apple" or "drench" in _norm(p["formulation"]) or p["stage"] == "any":
        return None
    for g_i, (group, kind, m_ai, m_form, wp, brands) in enumerate(R.BRANDS, 1):
        if p["active_ingredient"] == m_ai and (m_form == "" or m_form in _norm(p["formulation"])):
            return f"B{g_i:02d}", wp, brands
    return None
for p in R.P:
    lk = link_brands(p)
    if lk:
        gid, wp, brands = lk
        p["hp_brand_group"] = gid
        p["hp_brand_waiting_period_days"] = wp
        p["hp_evaluated_brands"] = "; ".join(f"{b} ({c})" if c else b for b, c in brands)
        if not (isinstance(p["brand_example"], str) and p["brand_example"]):
            named = [b for b, c in brands if c]
            p["brand_example"] = (named or [b for b, c in brands])[0]
    else:
        p["hp_brand_group"] = p["hp_brand_waiting_period_days"] = p["hp_evaluated_brands"] = None
pfields = ["product_id", "crop", "active_ingredient", "active_ingredient_hi", "formulation", "brand_example", "category",
           "frac_irac_code", "moa_class", "behaviour", "targets", "stage", "dose_min", "dose_max", "dose_unit",
           "waiting_period_days", "ban_status", "use_note", "usable_for_recommendation", "approved_for_crop_status",
           "hp_brand_group", "hp_brand_waiting_period_days", "hp_evaluated_brands", "source_ref", "confidence", "note"]
write_csv(OUT / "product_master.csv", R.P, pfields)

write_csv(OUT / "offlabel_products.csv", R.OFFLABEL,
          ["trade_name", "active_ingredient", "frac_irac_code", "formulation", "approved_crops", "apple_status", "evidence", "source_ref", "confidence"])
write_csv(OUT / "banned_restricted.csv",
          [dict(active_ingredient=a, status=s, source_ref=src) for a, s, src in R.BANNED],
          ["active_ingredient", "status", "source_ref"])

# ---------------------------------------------------------------- stage calendar (ESTIMATE)
# Anchors: Priyanka et al. 2021 (IJCMAS 10(1):686-692), Julian-day flowering means:
#   1500-2000 m ~99.7 ; 2000-2500 m ~114-115 ; 2500-3000 m ~118.3 (2016-17, Kullu/Shimla/Kinnaur).
#   <1500 m is EXTRAPOLATED (-8 days vs the 1500-2000 band) - inferred.
# Offsets from full bloom are inferred from the paper's bud-development (~F-38 d) and inflorescence
# emergence (~F-18 d) means plus standard pome-fruit phenology; later stages inferred from the HP schedule order.
BANDS = [("B1", 0, 1500, 92), ("B2", 1500, 2000, 100), ("B3", 2000, 2500, 114), ("B4", 2500, 3600, 119)]
OFFSETS = [("silver_tip", -45), ("green_tip", -38), ("half_inch_green_tip", -30), ("tight_cluster", -18), ("pink_bud", -8),
           ("full_bloom", 0), ("petal_fall", 12), ("fruit_set", 20), ("walnut_size", 45), ("walnut_plus_20d", 65), ("walnut_plus_40d", 85)]
CULTIVAR_HARVEST = {"Gala": 120, "Scarlet_Spur": 130, "Red_Chief": 128, "Golden_Delicious": 130,
                    "Royal_Delicious": 138, "Red_Delicious": 138, "Granny_Smith": 165}
HIGH_BAND_EXTRA_DAYS = 5   # B4 harvest is later (Kinnaur season starts ~a month after Kullu/Shimla)

def doy_to_date(doy, year=2026):
    return (datetime.date(year, 1, 1) + datetime.timedelta(days=int(doy) - 1)).isoformat()

cal = []
for band, lo, hi, F in BANDS:
    for stage, off in OFFSETS:
        cal.append(dict(band_id=band, elev_min_m=lo, elev_max_m=hi, stage_id=stage, cultivar="", offset_from_full_bloom_days=off,
                        typical_doy=F + off, typical_date_2026=doy_to_date(F + off), confidence="I",
                        source_ref="Anchors: Priyanka et al. 2021 IJCMAS 10(1):686-692; offsets inferred"))
    for cv, days in CULTIVAR_HARVEST.items():
        h = F + days + (HIGH_BAND_EXTRA_DAYS if band == "B4" else 0)
        for stage, off in (("pre_harvest", -22), ("harvest", 0), ("post_harvest", 7)):
            cal.append(dict(band_id=band, elev_min_m=lo, elev_max_m=hi, stage_id=stage, cultivar=cv,
                            offset_from_full_bloom_days=h - F + off, typical_doy=h + off, typical_date_2026=doy_to_date(h + off),
                            confidence="I", source_ref="Harvest windows from farm/travel sources (secondary) + FAO-type maturity of 130-150 d after full bloom"))
write_csv(OUT / "stage_calendar.csv", cal,
          ["band_id", "elev_min_m", "elev_max_m", "stage_id", "cultivar", "offset_from_full_bloom_days", "typical_doy", "typical_date_2026", "confidence", "source_ref"])

# ---------------------------------------------------------------- rules config
MILLS = [  # revised Mills table (MacHardy & Gadoury 1989) via Penn State; F->C conversion by us
    (1.1, 41), (2.2, 35), (2.8, 30), (3.9, 28), (5.0, 21), (6.1, 18), (7.2, 15), (7.8, 13), (8.9, 12), (10.0, 11),
    (11.1, 9), (12.2, 8), (13.9, 7), (16.1, 6), (25.0, 8), (26.1, 11)]
rules = {
    "_comment": "Thresholds marked [V] come from sources in docs/research/agronomy-data.md; [I] are inferred defaults to be confirmed by the client agronomist.",
    "confidence_policy": {  # [I] to be calibrated on field-like photos
        "min_confidence_to_show_result": 0.45,     # ixrbhii model card suggests asking for a better photo below ~45 %
        "min_confidence_for_auto_advice": 0.65,
        "below_threshold_action": "show_not_sure_with_top3_and_send_to_agronomist_queue",
        "crop_must_be_selected_first": True,
        "route_to_expert_when_requires_expert_review": True,
    },
    "rain": {
        "heavy_rain_window_hours": 12,             # [V] HP 2026: heavy rain within 12 h of spray
        "repeat_spray_within_days": 7,             # [V] HP 2026
        "heavy_rain_mm_default": 10,               # [I] 'heavy' is not defined in mm by the schedule
        "shorten_interval_cumulative_mm": 25,      # [I]
        "treat_as_unprotected_cumulative_mm": 50,  # [I] (NC State: ~2 inches reapply guidance for captan)
        "rainfast_hours": {"contact": 8, "mixed": 4, "systemic": 2},  # [I] Purdue / NC State guidance
    },
    "rotation": {                                   # [V] HP 2026 + FRAC pome-fruit guidance
        "never_repeat_same_chemical": True,
        "frac_group_alternation": True,
        "max_per_season": {"DMI": 4, "QoI": 3, "QoI_if_12_or_more_sprays": 4},
        "SDHI_max_consecutive": 2,
        "qoi_only_in_mixture": True,
    },
    "product_constraints": {
        "dodine_max_air_temp_c": 30,               # [V] HP 2026
        "dodine_no_tank_mix": True,
        "captan_oil_gap_days": 15,                 # [V] HP 2026
        "no_mixing_with_any_other_chemical": True,  # [V] HP 2026 point 7: do not mix any other pesticide/chemical/micro-nutrient/growth regulator/hormone with the recommended pesticides (russeting); spray separately if needed. Co-formulated products are listed as single products.
        "min_days_between_insecticide_and_fungicide": 3,   # [V-s] SKUAST-K 2026
        "stop_sprays_before_harvest_days": 21,     # [V-s] SKUAST-K: 3-4 weeks
        "unknown_waiting_period_policy": "expert_check_if_harvest_within_30_days",  # [I]
        "excluded_from_mvp": ["Streptomycin + Tetracycline"],
        "ban_status_values": {"banned": "never recommend",
                              "proposed_ban_2020_draft_still_registered": "recommend with warning flag; admin can disable"},
    },
    "apple_scab_mills_table": {
        "source": "Revised Mills table (MacHardy & Gadoury 1989) via Penn State Extension [V]; deg C by conversion",
        "usage": "Use mean of min and max air temperature during the wet period; join wet periods separated by <8 h; "
                 "pick the row with the greatest t_c_from <= mean temp; below 1.1 C no infection in the table; above ~26 C infection is rare.",
        "rows": [{"t_c_from": t, "min_wet_hours": h} for t, h in MILLS],
        "primary_season": {"from_stage": "green_tip", "to": "petal_fall + 21 days"},
        "lesions_visible_days_after_infection": "9-17",
    },
    "marssonina_alternaria_weather": {          # [V-s] ICAR Indian Phytopathology abstracts; no validated HP model
        "active_from_date_mmdd": "06-01",
        "risk_if": "mean_temp_c > 20 AND mean_rh_pct >= 70 for >= 5 consecutive days, with >= 6 h leaf wetness on rain days",
        "mean_temp_c_min": 20, "mean_rh_pct_min": 70, "consecutive_days": 5, "min_wetness_hours_per_infection": 6,
    },
    "late_blight_niphm": {                      # [V] NIPHM Potato package p.17
        "applies_to": ["Potato", "Tomato"],
        "window_days": 7,
        "hours_temp_between_c": [7.2, 26.6], "hours_temp_min_total": 115,
        "hours_rh_above_pct": 85, "hours_rh_min_total": 90,
        "outcome": "late_blight_expected_within_10_days",
    },
    "leaf_wetness_proxy": {                     # derived because the weather API has no hourly leaf wetness
        "wet_if": "precipitation_mm >= 0.1 OR relative_humidity_pct >= 90",
        "note": "Proxy only. Real leaf-wetness sensors report wet minutes per hour.",
    },
    "alerts": [
        {"id": "scab_infection_risk", "when": "Mills threshold reached during primary scab season", "audience": "apple farmers in the station block"},
        {"id": "marssonina_alternaria_risk", "when": "marssonina_alternaria_weather rule true", "audience": "apple farmers from 1 June"},
        {"id": "late_blight_risk", "when": "late_blight_niphm rule true", "audience": "potato/tomato farmers"},
        {"id": "rain_washoff_respray", "when": "heavy rain within 12 h after a logged spray", "audience": "that farmer"},
        {"id": "waiting_period_reminder", "when": "days to harvest < product waiting period", "audience": "that farmer"},
        {"id": "rotation_limit_warning", "when": "DMI >= 4, QoI >= 3, SDHI consecutive >= 2, or same product repeated", "audience": "that farmer"},
    ],
    "demo": {"clock_is_configurable": True,
             "note": "It is October, so apple spray stages are not current. The demo runs on a simulated clock; weather after the clock is served from the real archive as a 'perfect forecast' with noise."},
}
(OUT / "rules_config.json").write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")

glossary = {"_status": "Hindi is a DRAFT written by the assistant. A native-speaker agronomy reviewer must approve it before any client demo.",
            "crops": R.CROP_HI, "stages": {k: {"en": R.STAGE_EN[k], "hi": R.STAGE_HI[k]} for k in R.STAGE_EN},
            "diseases": R.DISEASE_HI, "active_ingredients": R.AI_HI}
(OUT / "hindi_glossary.json").write_text(json.dumps(glossary, indent=2, ensure_ascii=False), encoding="utf-8")

print("diseases", len(R.D), "| products", len(R.P), "| offlabel", len(R.OFFLABEL), "| calendar rows", len(cal))
