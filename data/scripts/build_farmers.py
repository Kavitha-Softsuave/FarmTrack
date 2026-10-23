# -*- coding: utf-8 -*-
"""50 FABRICATED farmers in real Himachal villages with real apple varieties. No real person is represented.
Phone numbers are deliberately INVALID (+91 00000 ...)."""
import numpy as np, pandas as pd, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
rng = np.random.default_rng(20261020)

st = pd.read_csv(ROOT / "weather" / "stations.csv")
elev = dict(zip(st.station_id, st.grid_elevation_m))

# farmers per station (sums to 50) and primary-crop plan
PLAN = {"ST01": 6, "ST02": 6, "ST03": 3, "ST04": 6, "ST05": 5, "ST06": 4, "ST07": 4, "ST08": 4, "ST09": 3, "ST10": 2, "ST11": 4, "ST12": 3}
NONAPPLE = ["ST06:Tomato", "ST07:Tomato", "ST11:Tomato", "ST12:Tomato",       # vegetable growers
            "ST07:Potato", "ST10:Potato", "ST09:Potato",
            "ST11:Maize", "ST12:Maize", "ST12:Grape"]
assert sum(PLAN.values()) == 50 and len(NONAPPLE) == 10

MALE = ["Rajesh", "Surender", "Narender", "Dinesh", "Mahesh", "Pawan", "Rakesh", "Anil", "Sunil", "Kuldeep", "Hemraj", "Tikam",
        "Pratap", "Ramesh", "Mohan", "Balbir", "Bhagat", "Kishan", "Lekh Ram", "Ranjit", "Yashwant", "Prakash", "Sanjay", "Vijay",
        "Devender", "Mast Ram", "Gopal", "Narayan", "Roshan", "Tek Chand", "Bhupender", "Hari Singh", "Chet Ram", "Naresh"]
FEMALE = ["Kamla", "Sunita", "Reeta", "Poonam", "Anita", "Meena", "Savita", "Kanta", "Rekha", "Neelam"]
LAST = ["Thakur", "Negi", "Verma", "Sharma", "Rana", "Kanwar", "Bhardwaj", "Mehta", "Kashyap", "Chandel", "Sood", "Panwar", "Rawat",
        "Chauhan", "Mahant", "Dogra", "Bisht", "Sen", "Guleria", "Jaswal", "Kapoor", "Bhatia", "Sankhyan", "Rathore"]
STAFF = ["Aman Verma", "Pooja Thakur", "Ravi Negi", "Deepak Rana", "Sneha Sharma"]   # fabricated field staff (Zoho record owners)

CULT_POP = {  # variety -> share of orchards by band (rough, from docs/research/agronomy-data.md sec. 6)
    "B1": {"Gala": .30, "Scarlet_Spur": .25, "Red_Chief": .20, "Royal_Delicious": .15, "Golden_Delicious": .10},
    "B2": {"Royal_Delicious": .30, "Gala": .25, "Scarlet_Spur": .20, "Red_Chief": .15, "Golden_Delicious": .10},
    "B3": {"Royal_Delicious": .45, "Red_Chief": .15, "Gala": .15, "Golden_Delicious": .10, "Granny_Smith": .10, "Scarlet_Spur": .05},
    "B4": {"Royal_Delicious": .75, "Golden_Delicious": .10, "Granny_Smith": .08, "Red_Chief": .07},
}
def band(e):
    return "B1" if e < 1500 else "B2" if e < 2000 else "B3" if e < 2500 else "B4"

used, rows, k = set(), [], 0
assign = []
for sid, n in PLAN.items():
    assign += [(sid, None)] * n
# put non-apple primary crops at the planned stations
slots = {sid: n for sid, n in PLAN.items()}
na = {}
for item in NONAPPLE:
    sid, crop = item.split(":")
    na.setdefault(sid, []).append(crop)
assign = []
for sid, n in PLAN.items():
    crops = na.get(sid, [])
    assign += [(sid, c) for c in crops] + [(sid, "Apple")] * (n - len(crops))

for sid, crop in assign:
    k += 1
    female = rng.random() < 0.15
    while True:
        fn = rng.choice(FEMALE if female else MALE); ln = rng.choice(LAST)
        nm = f"{fn} {ln}"
        if nm not in used and nm != "Jitender Chauhan":
            used.add(nm); break
    e = float(elev[sid] + rng.normal(0, 60)); b = band(e)
    acres = float(np.clip(rng.lognormal(np.log(2.0), 0.7), 0.4, 12))
    if crop == "Apple":
        pop = CULT_POP[b]; names = list(pop); p = np.array(list(pop.values())); p = p / p.sum()
        nvar = int(rng.choice([1, 2, 3], p=[.25, .5, .25])) if b != "B4" else int(rng.choice([1, 2], p=[.5, .5]))
        chosen = list(rng.choice(names, size=min(nvar, len(names)), replace=False, p=p))
        sh = rng.dirichlet(np.ones(len(chosen)) * 2) * 100
        mix = [{"variety": v, "share_pct": int(round(s))} for v, s in zip(chosen, sh)]
        mix[0]["share_pct"] += 100 - sum(m["share_pct"] for m in mix)
        rootstock = str(rng.choice(["Seedling", "MM106", "M9", "MM111", "M7"], p=[.55, .15, .15, .1, .05]))
        density = int(rng.choice([300, 400, 500]) if rootstock == "Seedling" else rng.choice([600, 800, 1000]))
        primary_variety = max(mix, key=lambda m: m["share_pct"])["variety"]
    else:
        mix, rootstock, density, primary_variety = [], "", 0, ""
    others = []
    if crop == "Apple" and rng.random() < 0.3:
        others = list(rng.choice(["Potato", "Maize", "Tomato"], size=int(rng.choice([1, 2])), replace=False))
    stn = st[st.station_id == sid].iloc[0]
    rows.append(dict(
        farmer_id=f"F{k:03d}", zoho_contact_id=f"9990000000{k:09d}", name=nm, gender="F" if female else "M",
        phone=f"+91 00000 {k:05d}", village=stn.village, block=stn.block, district=stn.district, station_id=sid,
        orchard_elevation_m=int(round(e)), phenology_band=b, orchard_area_acres=round(acres, 1),
        primary_crop=crop, other_crops=";".join(others), variety_mix=json.dumps(mix), primary_variety=primary_variety,
        rootstock=rootstock, plants_per_acre=density,
        preferred_language="hi" if rng.random() < 0.85 else "en",
        digital_literacy=str(rng.choice(["low", "medium", "high"], p=[.45, .4, .15])),
        discipline=str(rng.choice(["diligent", "average", "lax"], p=[.3, .45, .25])),
        field_staff_owner=str(rng.choice(STAFF)), has_smartphone="true",
        app_enrolled_on=str(pd.Timestamp("2026-03-01") + pd.Timedelta(days=int(rng.integers(0, 15)))).split()[0],
        data_origin="FABRICATED_DEMO"))
df = pd.DataFrame(rows)
df.to_csv(ROOT / "farmers.csv", index=False, encoding="utf-8-sig")
print(df.groupby(["district"]).size().to_dict()); print(df.primary_crop.value_counts().to_dict()); print(df.phenology_band.value_counts().to_dict())
