from datetime import datetime

import pytest

from app.clock import IST
from app.domain.types import SprayRecord
from app.integrations.errors import NotConfigured
from app.integrations.factory import build_iot, build_push, build_weather, build_zoho
from app.integrations.iot_mock import MockIoTAdapter
from app.integrations.push import LogPushProvider
from app.integrations.weather_csv import CsvWeatherAdapter
from app.integrations.weather_openmeteo import OpenMeteoAdapter
from app.integrations.zoho_mock import MockZohoAdapter
from app.interfaces import IoTAdapter, PushProvider, WeatherAdapter, ZohoAdapter
from tests.integrations.fakes import make_settings


def test_defaults_build_the_offline_providers(tmp_path):
    s = make_settings(tmp_path)
    zoho, iot, weather, push = build_zoho(s), build_iot(s), build_weather(s), build_push(s)
    assert isinstance(zoho, MockZohoAdapter) and isinstance(zoho, ZohoAdapter)
    assert isinstance(iot, MockIoTAdapter) and isinstance(iot, IoTAdapter)
    assert isinstance(weather, CsvWeatherAdapter) and isinstance(weather, WeatherAdapter)
    assert isinstance(push, LogPushProvider) and isinstance(push, PushProvider)


def test_mock_zoho_stores_writes_under_storage_dir(tmp_path):
    s = make_settings(tmp_path)
    zoho = build_zoho(s)
    assert zoho.write_spray("F001", SprayRecord(sprayed_at=datetime(2026, 5, 12, tzinfo=IST))) is True
    assert (s.storage_dir / "zoho_mock" / "sprays.jsonl").exists()


def test_openmeteo_is_selectable(tmp_path):
    assert isinstance(build_weather(make_settings(tmp_path, weather_provider="openmeteo")), OpenMeteoAdapter)


def test_selection_is_case_insensitive(tmp_path):
    assert isinstance(build_zoho(make_settings(tmp_path, zoho_provider="MOCK")), MockZohoAdapter)


def test_real_zoho_without_credentials_fails_fast(tmp_path, monkeypatch):
    for name in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(NotConfigured, match="ZOHO_CLIENT_ID"):
        build_zoho(make_settings(tmp_path, zoho_provider="real"))


def test_fcm_without_credentials_file_fails_fast(tmp_path):
    with pytest.raises(NotConfigured):
        build_push(make_settings(tmp_path, push_provider="fcm"))


def test_real_iot_is_not_available_yet(tmp_path):
    with pytest.raises(NotConfigured):
        build_iot(make_settings(tmp_path, iot_provider="real"))


@pytest.mark.parametrize("builder,field", [(build_zoho, "zoho_provider"), (build_iot, "iot_provider"),
                                           (build_weather, "weather_provider"), (build_push, "push_provider")])
def test_unknown_provider_names_are_rejected_with_the_allowed_values(tmp_path, builder, field):
    with pytest.raises(ValueError, match="expected one of"):
        builder(make_settings(tmp_path, **{field: "nonsense"}))
