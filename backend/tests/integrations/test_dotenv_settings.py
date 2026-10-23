"""ZOHO_* and OPEN_METEO_API_KEY are Settings fields: a .env file works, not only the process environment (review finding)."""
import httpx
import pytest

from app.config import Settings
from app.integrations.errors import NotConfigured
from app.integrations.factory import build_weather, build_zoho
from app.integrations.weather_openmeteo import CUSTOMER_URL, FREE_URL, OpenMeteoAdapter
from app.integrations.zoho_real import RealZohoAdapter, ZohoConfig
from tests.integrations.test_weather_openmeteo import DATA, NOW, Recorder

NAMES = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN", "ZOHO_ACCOUNTS_URL", "ZOHO_API_BASE", "OPEN_METEO_API_KEY")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def env_file(tmp_path, text):
    path = tmp_path / "test.env"
    path.write_text(text, encoding="utf-8")
    return path


def test_zoho_credentials_come_from_a_dotenv_file(tmp_path):
    path = env_file(tmp_path, "ZOHO_CLIENT_ID=cid\nZOHO_CLIENT_SECRET=csecret\nZOHO_REFRESH_TOKEN=rtoken\n"
                              "ZOHO_API_BASE=https://example.test/crm/v6/\n")
    settings = Settings(_env_file=path, zoho_provider="real")
    cfg = ZohoConfig.from_settings(settings)
    assert (cfg.client_id, cfg.client_secret, cfg.refresh_token) == ("cid", "csecret", "rtoken")
    assert cfg.api_base == "https://example.test/crm/v6" and cfg.accounts_url == "https://accounts.zoho.in"
    assert isinstance(build_zoho(settings), RealZohoAdapter)


def test_zoho_credentials_still_work_from_the_process_environment(monkeypatch):
    for name, value in (("ZOHO_CLIENT_ID", "cid"), ("ZOHO_CLIENT_SECRET", "s"), ("ZOHO_REFRESH_TOKEN", "r")):
        monkeypatch.setenv(name, value)
    assert ZohoConfig.from_env().client_id == "cid"
    assert ZohoConfig.from_settings(Settings(_env_file=None)).refresh_token == "r"


def test_real_zoho_without_credentials_names_every_missing_variable(tmp_path):
    path = env_file(tmp_path, "ZOHO_CLIENT_ID=cid\nZOHO_CLIENT_SECRET=\n")
    with pytest.raises(NotConfigured) as caught:
        build_zoho(Settings(_env_file=path, zoho_provider="real"))
    assert "ZOHO_CLIENT_SECRET" in str(caught.value) and "ZOHO_REFRESH_TOKEN" in str(caught.value)
    assert "cid" not in str(caught.value)


def test_open_meteo_key_comes_from_a_dotenv_file(tmp_path):
    settings = Settings(_env_file=env_file(tmp_path, "OPEN_METEO_API_KEY=k-from-dotenv\n"), weather_provider="openmeteo")
    adapter = build_weather(settings)
    assert isinstance(adapter, OpenMeteoAdapter)
    recorder = Recorder()
    OpenMeteoAdapter(DATA, client=httpx.Client(transport=httpx.MockTransport(recorder)),
                     api_key=settings.open_meteo_api_key).snapshot(None, 31.12, 77.36, NOW)
    assert str(recorder.requests[0].url).startswith(CUSTOMER_URL)
    assert recorder.requests[0].url.params["apikey"] == "k-from-dotenv"


def test_open_meteo_without_a_key_uses_the_free_endpoint():
    recorder = Recorder()
    OpenMeteoAdapter(DATA, client=httpx.Client(transport=httpx.MockTransport(recorder)),
                     api_key=Settings(_env_file=None).open_meteo_api_key).snapshot(None, 31.12, 77.36, NOW)
    assert str(recorder.requests[0].url).startswith(FREE_URL) and "apikey" not in recorder.requests[0].url.params
