"""Provider builders used by app.services.container.build_container (the factory contract).

Selection comes from Settings: zoho_provider (mock|real), iot_provider (mock), weather_provider (csv|openmeteo),
push_provider (log|fcm). Choosing a real provider whose credentials are missing raises NotConfigured at start-up (fail fast).
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.config import Settings
from app.domain.types import WeatherSnapshot
from app.integrations.errors import NotConfigured, WeatherUnavailable
from app.integrations.iot_mock import MockIoTAdapter
from app.integrations.push import FcmPushProvider, LogPushProvider
from app.integrations.weather_csv import CsvWeatherAdapter
from app.integrations.weather_openmeteo import OpenMeteoAdapter
from app.integrations.zoho_mock import MockZohoAdapter
from app.integrations.zoho_real import RealZohoAdapter, ZohoConfig
from app.interfaces import IoTAdapter, PushProvider, WeatherAdapter, ZohoAdapter

log = logging.getLogger(__name__)


def _unknown(kind: str, value: str, allowed: str) -> ValueError:
    return ValueError(f"unknown {kind} provider {value!r}; expected one of: {allowed}")


def build_zoho(settings: Settings) -> ZohoAdapter:
    provider = settings.zoho_provider.lower()
    if provider == "mock":
        return MockZohoAdapter(settings.data_dir, settings.storage_dir / "zoho_mock")
    if provider == "real":
        return RealZohoAdapter(ZohoConfig.from_settings(settings), settings.data_dir)
    raise _unknown("zoho", provider, "mock, real")


def build_iot(settings: Settings) -> IoTAdapter:
    provider = settings.iot_provider.lower()
    if provider == "mock":
        return MockIoTAdapter(settings.data_dir)
    if provider == "real":
        raise NotConfigured("there is no real IoT adapter yet: the client's sensor platform is not known")
    raise _unknown("iot", provider, "mock")


class DisabledWeatherAdapter:
    """WEATHER_ENABLED=false: nothing is looked up. The callers check the flag first; this is the second line of defence."""

    def snapshot(self, station_id: str | None, lat: float | None, lon: float | None, now: datetime) -> WeatherSnapshot:
        raise WeatherUnavailable("weather is switched off (WEATHER_ENABLED=false)")


def build_weather(settings: Settings) -> WeatherAdapter:
    if not settings.weather_enabled:
        return DisabledWeatherAdapter()
    provider = settings.weather_provider.lower()
    if provider == "csv":
        return CsvWeatherAdapter(settings.data_dir)
    if provider == "openmeteo":
        if settings.is_prod:
            log.warning("the free Open-Meteo endpoint is non-commercial; set OPEN_METEO_API_KEY (paid plan) for production use")
        return OpenMeteoAdapter(settings.data_dir, api_key=settings.open_meteo_api_key)
    raise _unknown("weather", provider, "csv, openmeteo")


def build_push(settings: Settings) -> PushProvider:
    provider = settings.push_provider.lower()
    if provider == "log":
        return LogPushProvider()
    if provider == "fcm":
        return FcmPushProvider(settings.fcm_credentials_file)
    raise _unknown("push", provider, "log, fcm")
