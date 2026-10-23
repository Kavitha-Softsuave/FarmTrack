# -*- coding: utf-8 -*-
"""Explore the real 2026 weather to find genuine events for the demo (scab infections, Marssonina weather,
late-blight weather, heavy rain). Prints a summary; build_scenarios.py uses the same functions."""
import pandas as pd
from weather_rules import *

w = load_weather()
st = pd.read_csv(ROOT / "weather" / "stations.csv")
print("NaN per column:", w.isna().sum().to_dict())
print(w.groupby("station_id")[["temp_c", "rh_pct", "rain_mm", "soil_m3m3"]].agg(["min", "max"]).round(1).head(12))

for sid in st["station_id"]:
    ws = w[w.station_id == sid]
    name = st.loc[st.station_id == sid, "village"].iloc[0]
    elev = st.loc[st.station_id == sid, "grid_elevation_m"].iloc[0]
    apr_may = ws[(ws.time_ist >= "2026-03-10") & (ws.time_ist < "2026-06-10")]
    inf = [p for p in scab_infection_periods(apr_may) if p["infection"]]
    md = marssonina_risk_days(ws)
    lb = late_blight_flag(ws)
    heavy = ws.set_index("time_ist")["rain_mm"].resample("D").sum()
    print(f"\n{sid} {name} ({elev:.0f} m): scab infections Mar10-Jun10: {len(inf)} | marssonina-risk days: {int(md['risk'].sum())} "
          f"({md.loc[md['risk'],'time_ist'].min()} .. {md.loc[md['risk'],'time_ist'].max()}) | late-blight flag days: {int(lb['flag'].sum())} "
          f"| days >=10mm: {(heavy>=10).sum()} | >=25mm: {(heavy>=25).sum()} | total rain {heavy.sum():.0f} mm")
    for p in inf[:4]:
        print("   scab:", p["start"], "->", p["end"], f"wet {p['wet_hours']}h need {p['need_hours']}h T={p['mean_temp_c']} rain={p['rain_mm']}")
