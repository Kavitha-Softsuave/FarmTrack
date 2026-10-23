# -*- coding: utf-8 -*-
"""Weather-derived risk calculations used by the data builders (and later by the real rules engine).
Implements the thresholds in reference/rules_config.json."""
import json, pathlib
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "reference" / "rules_config.json").read_text(encoding="utf-8"))

def load_weather():
    w = pd.read_csv(ROOT / "weather" / "weather_hourly_raw.csv", parse_dates=["time_ist"])
    w = w.rename(columns={"temperature_2m": "temp_c", "relative_humidity_2m": "rh_pct", "precipitation": "rain_mm",
                          "soil_moisture_0_to_7cm": "soil_m3m3", "dew_point_2m": "dew_c"})
    w["wet"] = ((w["rain_mm"] >= 0.1) | (w["rh_pct"] >= 90)).astype(int)      # leaf-wetness proxy
    return w

MILLS_ROWS = CFG["apple_scab_mills_table"]["rows"]
def mills_hours(mean_temp_c):
    """Minimum wet hours for a scab infection at the given mean temperature (None = no infection / outside table)."""
    if mean_temp_c < MILLS_ROWS[0]["t_c_from"]:
        return None
    h = None
    for r in MILLS_ROWS:
        if mean_temp_c >= r["t_c_from"]:
            h = r["min_wet_hours"]
    return h

def scab_infection_periods(ws, gap_hours=8):
    """ws: hourly frame for ONE station (sorted). Returns list of infection periods: wet runs joined when gaps < gap_hours."""
    ws = ws.sort_values("time_ist").reset_index(drop=True)
    wet = ws["wet"].values
    runs, i, n = [], 0, len(ws)
    while i < n:
        if wet[i]:
            j = i
            while j + 1 < n and wet[j + 1]:
                j += 1
            runs.append([i, j]); i = j + 1
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and (r[0] - merged[-1][1] - 1) < gap_hours:
            merged[-1][1] = r[1]
        else:
            merged.append(r[:])
    out = []
    for a, b in merged:
        seg = ws.iloc[a:b + 1]
        hours = int(seg["wet"].sum())
        mean_t = float(seg["temp_c"].mean())
        need = mills_hours(mean_t)
        out.append(dict(start=seg["time_ist"].iloc[0], end=seg["time_ist"].iloc[-1], wet_hours=hours,
                        span_hours=b - a + 1, mean_temp_c=round(mean_t, 1), need_hours=need,
                        infection=bool(need is not None and hours >= need), rain_mm=round(float(seg["rain_mm"].sum()), 1)))
    return out

def marssonina_risk_days(ws):
    """Daily flag: mean temp > 20 and mean RH >= 70, from 1 June. Returns daily frame with 5-day consecutive run flag."""
    d = ws.set_index("time_ist").resample("D").agg(temp=("temp_c", "mean"), rh=("rh_pct", "mean"), rain=("rain_mm", "sum"),
                                                   wet=("wet", "sum")).reset_index()
    c = CFG["marssonina_alternaria_weather"]
    d["cond"] = (d["temp"] > c["mean_temp_c_min"]) & (d["rh"] >= c["mean_rh_pct_min"]) & (d["time_ist"].dt.month >= 6)
    run = 0; flags = []
    for v in d["cond"]:
        run = run + 1 if v else 0
        flags.append(run >= c["consecutive_days"])
    d["risk"] = flags
    return d

def late_blight_flag(ws):
    """NIPHM 7-day rule evaluated at each day end. Returns daily frame with flag."""
    c = CFG["late_blight_niphm"]
    lo, hi = c["hours_temp_between_c"]
    s = ws.sort_values("time_ist").set_index("time_ist")
    a = ((s["temp_c"] >= lo) & (s["temp_c"] <= hi)).astype(int).rolling(24 * c["window_days"]).sum()
    b = (s["rh_pct"] > c["hours_rh_above_pct"]).astype(int).rolling(24 * c["window_days"]).sum()
    f = ((a >= c["hours_temp_min_total"]) & (b >= c["hours_rh_min_total"]))
    d = pd.DataFrame({"hrs_temp": a, "hrs_rh": b, "flag": f}).resample("D").last().reset_index()
    return d

def rain_after(ws, t0, hours):
    """mm of rain in [t0, t0+hours) for a station frame."""
    m = (ws["time_ist"] >= t0) & (ws["time_ist"] < t0 + pd.Timedelta(hours=hours))
    return float(ws.loc[m, "rain_mm"].sum())

def rain_between(ws, t0, t1):
    m = (ws["time_ist"] >= t0) & (ws["time_ist"] < t1)
    return float(ws.loc[m, "rain_mm"].sum())
