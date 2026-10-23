"""Fetch real hourly weather for the 12 demo stations from the Open-Meteo archive API.

Open-Meteo's free tier is NON-COMMERCIAL. This is fine for a demo / internal MVP only.
For production use a commercial plan or another provider (see docs/research/agronomy-data.md sec. 5).

Output: data/weather/stations.csv, data/weather/weather_hourly_raw.csv
"""
import csv, json, time, urllib.request, urllib.parse, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "weather"
OUT.mkdir(exist_ok=True)

START, END = "2026-02-15", sys.argv[1] if len(sys.argv) > 1 else "2026-10-17"

# lat/lon are APPROXIMATE village-centre coordinates (inferred); elevation is taken from the
# Open-Meteo grid cell returned by the API, which can differ from the village's true elevation.
STATIONS = [
    # station_id, village, block/area, district, lat, lon
    ("ST01", "Theog",    "Theog",     "Shimla", 31.12, 77.36),
    ("ST02", "Kotgarh",  "Kotgarh",   "Shimla", 31.31, 77.46),
    ("ST03", "Narkanda", "Narkanda",  "Shimla", 31.26, 77.45),
    ("ST04", "Rohru",    "Rohru",     "Shimla", 31.20, 77.75),
    ("ST05", "Jubbal",   "Jubbal",    "Shimla", 31.12, 77.67),
    ("ST06", "Naggar",   "Naggar",    "Kullu",  32.11, 77.17),
    ("ST07", "Manali",   "Manali",    "Kullu",  32.24, 77.19),
    ("ST08", "Sangla",   "Sangla",    "Kinnaur", 31.42, 78.26),
    ("ST09", "Kalpa",    "Kalpa",     "Kinnaur", 31.54, 78.26),
    ("ST10", "Bharmour", "Bharmour",  "Chamba", 32.44, 76.53),
    ("ST11", "Karsog",   "Karsog",    "Mandi",  31.38, 77.20),
    ("ST12", "Nauni",    "Nauni",     "Solan",  30.86, 77.17),
]
VARS = ["temperature_2m", "relative_humidity_2m", "precipitation", "soil_moisture_0_to_7cm", "dew_point_2m"]

def get(lat, lon):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "start_date": START, "end_date": END,
        "hourly": ",".join(VARS), "timezone": "Asia/Kolkata"})
    url = "https://archive-api.open-meteo.com/v1/archive?" + q
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print("retry", attempt, e)
            time.sleep(5 * (attempt + 1))
    raise SystemExit("failed " + url)

stations_rows, hourly_rows = [], []
for sid, village, block, district, lat, lon in STATIONS:
    d = get(lat, lon)
    h = d["hourly"]
    stations_rows.append([sid, village, block, district, lat, lon, d["latitude"], d["longitude"], d["elevation"]])
    n = len(h["time"])
    for i in range(n):
        hourly_rows.append([sid, h["time"][i]] + [h[v][i] for v in VARS])
    print(sid, village, "grid elev", d["elevation"], "rows", n)
    time.sleep(1.5)

with open(OUT / "stations.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["station_id", "village", "block", "district", "lat_approx", "lon_approx",
                "grid_lat", "grid_lon", "grid_elevation_m"])
    w.writerows(stations_rows)
with open(OUT / "weather_hourly_raw.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["station_id", "time_ist"] + VARS)
    w.writerows(hourly_rows)
print("done", len(hourly_rows), "hourly rows")
