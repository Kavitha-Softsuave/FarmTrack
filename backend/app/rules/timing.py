"""Spray timing from the weather: repeat after heavy rain (HP 2026 rule), wait for rain, or spray now."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.types import TimingAdvice, WeatherSnapshot
from app.rules import messages as msg
from app.rules import weather as wx
from app.rules.data import Product, ReferenceData, cfg
from app.rules.history import Spray, last_of_family

WAIT_IF_RAIN_NEXT_12H_MM = 2.0
DEFAULT_RAINFAST_MODE = "contact"      # the longest dry period, used when a product's behaviour is unknown


def rainfast_hours(ref: ReferenceData, product: Product | None) -> int:
    table = cfg(ref.config, "rain.rainfast_hours", {"contact": 8, "mixed": 4, "systemic": 2})
    mode = product.behaviour if product and product.behaviour in table else DEFAULT_RAINFAST_MODE
    return int(table[mode])


def heavy_rain_after_last_spray(ref: ReferenceData, weather: WeatherSnapshot, sprays: list[Spray], crop: str,
                                now: datetime) -> tuple[Spray, float] | None:
    """The most recent fungicide spray and the rain that fell within the window after it, when that rain was heavy."""
    heavy = float(cfg(ref.config, "rain.heavy_rain_mm_default", 10))
    window = int(cfg(ref.config, "rain.heavy_rain_window_hours", 12))
    days = int(cfg(ref.config, "rain.repeat_spray_within_days", 7))
    last = last_of_family(sprays, "fungicide", crop)
    if last is None or not timedelta(0) <= now - last.at <= timedelta(days=days):
        return None
    seen, _ = wx.rain_after_spray(wx.merged_hours(weather), last.at, now, window)
    return (last, seen) if seen >= heavy else None


def timing_advice(ref: ReferenceData, weather: WeatherSnapshot | None, sprays: list[Spray], crop: str, now: datetime,
                  products: list[Product]) -> TimingAdvice:
    if weather is None:
        return TimingAdvice(action="unknown", reasons=["no_weather_data"], text=msg.text("TIMING_UNKNOWN"))

    repeat_days = int(cfg(ref.config, "rain.repeat_spray_within_days", 7))
    rain_12h = float(weather.rain_next_12h_mm)
    wait = rain_12h >= WAIT_IF_RAIN_NEXT_12H_MM
    washed = heavy_rain_after_last_spray(ref, weather, sprays, crop, now)
    dry_hours = rainfast_hours(ref, products[0] if products else None)

    if washed is not None:
        reasons = ["heavy_rain_after_last_spray"] + (["rain_expected_next_12h"] if wait else [])
        key = "TIMING_REPEAT_WAIT" if wait else "TIMING_REPEAT"
        return TimingAdvice(action="repeat_within_days", reasons=reasons, rain_next_12h_mm=rain_12h, repeat_within_days=repeat_days,
                            text=msg.text(key, days=repeat_days))
    if wait:
        return TimingAdvice(action="wait", reasons=["rain_expected_next_12h"], rain_next_12h_mm=rain_12h,
                            text=msg.text("TIMING_WAIT", rain=round(rain_12h, 1), hours=dry_hours))
    return TimingAdvice(action="spray_now", reasons=["dry_next_12h"], rain_next_12h_mm=rain_12h, text=msg.text("TIMING_SPRAY_NOW"))
