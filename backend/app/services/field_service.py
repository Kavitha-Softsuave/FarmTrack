"""'My field': latest sensor readings (with a stale flag), 7-day forecast, weather risks and a spoken summary."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.api.schemas import FieldOut, ForecastDayOut, ReadingsOut, RiskOut, SpokenOut
from app.domain.types import FarmerProfile, LocalizedText, RiskItem, SensorReading, Severity, WeatherSnapshot
from app.services import texts
from app.services.container import Container
from app.services.history import merged_history
from app.services.presenters import ist
from app.services.prompts import PromptBook
from app.services.speech import speak

logger = logging.getLogger(__name__)

HEAVY_RAIN_MM = 10.0        # matches rules_config rain.heavy_rain_mm_default; wording only, the rules decide risks
NO_RAIN_MM = 1.0
_LEVEL_ORDER = {Severity.red: 0, Severity.yellow: 1, Severity.green: 2}


class FieldService:
    def __init__(self, container: Container, db: Session) -> None:
        self.c = container
        self.db = db

    def get(self, farmer: FarmerProfile) -> FieldOut:
        now = self.c.clock.now()
        weather = self._weather(farmer, now)
        reading, sensor_stale = self._sensor(farmer, now)
        stale = sensor_stale or weather is None or weather.stale
        risks = self._risks(farmer, weather, now) if weather else []
        readings = self._readings(reading, weather)
        as_of = reading.time if reading else (weather.as_of if weather else now)
        return FieldOut(
            station_id=farmer.station_id, village=farmer.village, as_of=ist(as_of), stale=stale, readings=readings,
            forecast=[ForecastDayOut(day=d.day, tmin_c=d.tmin_c, tmax_c=d.tmax_c, rain_mm=d.rain_mm)
                      for d in (weather.daily_forecast[:7] if weather else [])],
            risks=[RiskOut(id=r.id, level=r.level, title=r.title, text=r.text) for r in risks],
            spoken=self._spoken(readings, weather, risks, stale))

    # ------------------------------------------------------------------ data (each source may fail on its own)
    def _weather(self, farmer: FarmerProfile, now: datetime) -> WeatherSnapshot | None:
        try:
            return self.c.weather.snapshot(farmer.station_id, farmer.lat, farmer.lon, now)
        except Exception:
            logger.exception("weather unavailable farmer=%s", farmer.id)
            return None

    def _sensor(self, farmer: FarmerProfile, now: datetime) -> tuple[SensorReading | None, bool]:
        if not farmer.station_id:
            return None, False
        try:
            return self.c.iot.latest(farmer.station_id, now), bool(self.c.iot.is_stale(farmer.station_id, now))
        except Exception:
            logger.exception("sensor data unavailable farmer=%s", farmer.id)
            return None, True

    def _risks(self, farmer: FarmerProfile, weather: WeatherSnapshot, now: datetime) -> list[RiskItem]:
        history, _ = merged_history(self.c, self.db, farmer, now)
        try:
            return list(self.c.rules.evaluate_risks(farmer, weather, now, history))
        except Exception:
            logger.exception("risk evaluation failed farmer=%s", farmer.id)
            return []

    @staticmethod
    def _readings(reading: SensorReading | None, weather: WeatherSnapshot | None) -> ReadingsOut | None:
        if reading is not None:
            return ReadingsOut(temp_c=reading.temp_c, rh_pct=reading.rh_pct,
                               rain_24h_mm=weather.rain_last_24h_mm if weather else reading.rain_mm,
                               leaf_wetness_min=reading.leaf_wetness_min, soil_moisture_pct=reading.soil_moisture_pct)
        if weather is not None and (weather.temp_c is not None or weather.rh_pct is not None):
            return ReadingsOut(temp_c=weather.temp_c, rh_pct=weather.rh_pct, rain_24h_mm=weather.rain_last_24h_mm)
        return None

    # ------------------------------------------------------------------ speech
    def _spoken(self, readings: ReadingsOut | None, weather: WeatherSnapshot | None, risks: list[RiskItem],
                stale: bool) -> SpokenOut:
        book = PromptBook(self.c.settings.voice_dir)
        parts: list[LocalizedText] = []
        if stale:
            parts.append(book.get("field_stale", texts.FIELD_STALE_FALLBACK))
        if readings is None and weather is None:
            parts.append(book.get("field_no_data", texts.FIELD_NO_DATA_FALLBACK))
            return speak(self.c.audio, book.join(*parts))
        if readings is not None and readings.temp_c is not None:
            parts.append(texts.FIELD_TEMPERATURE[_temperature_band(readings.temp_c)])
        if weather is not None:
            parts.append(texts.FIELD_RAIN[_rain_band(weather.rain_next_48h_mm)])
        notable = sorted((r for r in risks if r.level != Severity.green), key=lambda r: _LEVEL_ORDER[r.level])[:2]
        if notable:
            parts.append(texts.FIELD_RISK_LEAD)
            parts.extend(r.text for r in notable)
        else:
            parts.append(texts.FIELD_NO_RISK)
        return speak(self.c.audio, book.join(*parts))


def _temperature_band(temp_c: float) -> str:
    if temp_c < 5:
        return "cold"
    if temp_c < 15:
        return "cool"
    if temp_c < 25:
        return "mild"
    if temp_c < 32:
        return "warm"
    return "hot"


def _rain_band(rain_mm: float) -> str:
    if rain_mm < NO_RAIN_MM:
        return "none"
    return "heavy" if rain_mm >= HEAVY_RAIN_MM else "light"
