# -*- coding: utf-8 -*-
"""Simulated IoT station feed, derived from REAL Open-Meteo hourly weather.

Adds what real field sensors have: per-device bias, noise, rain-gauge resolution, outages, battery drift and a few
unflagged glitches. One station per village (assumption - the client has not said whether devices are per farmer or per plot).
Seeded anomalies are listed separately in iot/_seeded_anomalies.csv for QA.
"""
import numpy as np, pandas as pd, pathlib
from weather_rules import load_weather, ROOT

OUT = ROOT / "iot"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(20261019)

w = load_weather()
rows, anomalies, outages = [], [], []
for sid, ws in w.groupby("station_id"):
    ws = ws.sort_values("time_ist").reset_index(drop=True)
    n = len(ws)
    t_bias, rh_bias, sm_bias = rng.normal(0, 0.35), rng.normal(0, 1.8), rng.normal(0, 1.0)
    temp = ws["temp_c"].values + t_bias + rng.normal(0, 0.3, n)
    rh = np.clip(ws["rh_pct"].values + rh_bias + rng.normal(0, 1.5, n), 5, 100)
    rain = np.round(ws["rain_mm"].values / 0.2) * 0.2                  # tipping-bucket 0.2 mm resolution
    sm = np.clip((ws["soil_m3m3"].values * 100) + sm_bias + rng.normal(0, 0.4, n), 1, 60)
    lw = np.where(ws["rain_mm"].values >= 0.1, 60, np.where(rh >= 95, 60, np.where(rh >= 90, 35, 0)))   # wet minutes in the hour (proxy)
    day = (ws["time_ist"] - ws["time_ist"].iloc[0]).dt.total_seconds().values / 86400
    batt = 4.15 - 0.40 * (day / day.max()) + 0.04 * np.sin(day * 2 * np.pi)      # slow drain + daily solar ripple
    keep = np.ones(n, bool)

    # seeded glitches (not flagged in the data, like a real sensor)
    for k in rng.choice(np.arange(200, n - 50), 6, replace=False):
        d = float(rng.choice([-15.0, 15.0, 25.0]))
        anomalies.append(dict(station_id=sid, time_ist=ws["time_ist"].iloc[k], field="temp_c", true_value=round(float(temp[k]), 1), reported_value=round(float(temp[k] + d), 1)))
        temp[k] += d

    # outages
    for _ in range(int(rng.integers(4, 9))):
        a = int(rng.integers(100, n - 60)); dur = int(np.exp(rng.uniform(np.log(3), np.log(36))))
        keep[a:a + dur] = False
        outages.append(dict(station_id=sid, start=ws["time_ist"].iloc[a], hours=dur, reason="random_outage"))
    keep &= rng.random(n) > 0.004                                         # occasional single missing hour
    if sid == "ST08":                                                     # scripted: Sangla offline for a stretch (stale-sensor scenario)
        m = (ws["time_ist"] >= "2026-07-10 06:00") & (ws["time_ist"] <= "2026-07-14 18:00")
        keep[m.values] = False
        outages.append(dict(station_id=sid, start="2026-07-10 06:00", hours=109, reason="scripted_offline_demo"))

    df = pd.DataFrame({"sensor_id": f"SN-{sid}-01", "station_id": sid, "timestamp_ist": ws["time_ist"],
                       "temp_c": np.round(temp, 1), "rh_pct": np.round(rh, 0).astype(int), "rain_mm": np.round(rain, 1),
                       "leaf_wetness_min": lw.astype(int), "soil_moisture_pct": np.round(sm, 1), "battery_v": np.round(batt, 2)})
    rows.append(df[keep])

out = pd.concat(rows, ignore_index=True)
out.to_csv(OUT / "sensor_readings.csv", index=False, encoding="utf-8")
pd.DataFrame(anomalies).to_csv(OUT / "_seeded_anomalies.csv", index=False)
pd.DataFrame(outages).to_csv(OUT / "_seeded_outages.csv", index=False)
print("sensor rows", len(out), "of", len(w), "=", f"{100*len(out)/len(w):.1f}% kept; glitches", len(anomalies), "outage windows", len(outages))
