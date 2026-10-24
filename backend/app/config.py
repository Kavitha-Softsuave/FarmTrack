"""Application settings. Values come from environment variables or the shared FarmTrack/.env file.

NOTE: the repo-root .env holds the user's real secrets (OPENAI_API_KEY ...). Tests must never depend on it:
tests build Settings(...) explicitly or set env vars and call get_settings.cache_clear().
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]          # .../FarmTrack
BACKEND_ROOT = Path(__file__).resolve().parents[1]       # .../FarmTrack/backend


_ENV_ALIASES = {"production": "prod", "prd": "prod", "staging": "prod", "stage": "prod", "preprod": "prod", "uat": "prod",
                "development": "dev", "local": "dev", "testing": "test"}


def _is_placeholder(value: str | None) -> bool:
    return (not value) or value.startswith("your-") or "here" in value.lower()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    # --- general
    env: str = "dev"                                   # dev | test | prod ("production", "staging" ... are read as prod)
    app_version: str = "0.1.0"
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'farmtrack.db').as_posix()}"
    secret_key: str = "dev-only-change-me"  # noqa: S105  JWT signing; prod startup must refuse this default
    access_token_minutes: int = 60
    refresh_token_days: int = 30
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    max_upload_mb: int = 8
    max_photos_per_scan: int = 4
    photo_retention_days: int = 365

    # --- paths
    data_dir: Path = REPO_ROOT / "data"                # reference data, mock zoho, weather, iot
    storage_dir: Path = BACKEND_ROOT / "storage"       # photos, audio cache
    voice_dir: Path = REPO_ROOT / "voice"              # prompt catalogue (+ generated audio)
    # Admin "Training photos" page: "Write into the training folder" copies labelled photos to <dir>/<class>/ (+ sources.csv).
    training_export_dir: Path = REPO_ROOT / "data" / "training" / "photos"

    # --- auth. MVP login = username + password (POST /v1/auth/login). The OTP code is kept but switched off: when OTP_LOGIN_ENABLED
    # is false the two OTP routes answer 404.
    otp_login_enabled: bool = False
    demo_password: str = "farm1234"  # noqa: S105  password of the seeded demo farmers (f001 ... f050); only seeded in dev/test or SEED_DEMO=1
    dev_fixed_otp: str | None = "123456"               # only honoured when env != prod
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5
    admin_api_key: str = "dev-admin-key"               # X-Admin-Key for /admin; MUST be overridden in prod

    # --- demo clock (the demo season is Mar-Oct 2026; today is outside apple season)
    demo_clock: str | None = "2026-05-12T08:00:00+05:30"   # None = use the real clock; in prod the default is the real clock
    allow_demo_clock_in_prod: bool = False             # prod normally refuses a frozen clock (wrong season for every farmer)

    # --- providers (all swappable; defaults run fully offline)
    llm_provider: str = "mock"                         # mock | openai
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"                  # shuts down 14 Jan 2027 -> gpt-6-luna
    openai_image_detail: str = "high"
    openai_temperature: str = "0"
    openai_max_output_tokens: int = 1200

    tts_provider: str = "null"                         # null | google
    google_tts_api_key: str | None = None
    tts_voice_hi: str = "hi-IN-Neural2-A"              # unverified default; chosen after the listening test
    tts_voice_en: str = "en-IN-Neural2-A"

    embeddings_provider: str = "hash"                  # hash (offline, tests/dev) | openai
    embeddings_model: str = "text-embedding-3-small"
    vector_store: str = "memory"                       # memory | pgvector

    crop_id_provider: str = "stub"                     # stub | model
    disease_provider: str = "stub"                     # stub | model
    # Folder with a locally trained apple leaf model (model.safetensors + config.json, made by data/training/train_apple.py).
    # With DISEASE_PROVIDER=model it answers for apple INSTEAD of the downloaded model A+B mix. Unset = the downloaded models.
    disease_model_dir: str | None = None
    # Offline demos only: force the stub disease classifier, e.g. "Apple=Apple___Apple_scab:0.9;Tomato=Tomato___Late_blight"
    # (format and rules in app/vision/hints.py). Ignored by the factory and refused at start-up when ENV=prod.
    demo_disease_hints: str | None = None
    zoho_provider: str = "mock"                        # mock | real
    iot_provider: str = "mock"
    weather_provider: str = "csv"                      # csv (demo archive) | openmeteo
    # WEATHER_ENABLED=false switches weather OFF everywhere: no weather lookup or network call, no weather risks or alerts,
    # no forecast card, no repeat-after-rain timing; advice says nothing about weather. /v1/meta reports it so the app can hide the UI.
    weather_enabled: bool = False
    push_provider: str = "log"                         # log | fcm
    fcm_credentials_file: str | None = None
    # Zoho CRM self-client (ZOHO_PROVIDER=real) and the optional Open-Meteo customer key: read through Settings so a .env file works too.
    zoho_client_id: str | None = None
    zoho_client_secret: str | None = None
    zoho_refresh_token: str | None = None
    zoho_accounts_url: str = "https://accounts.zoho.in"
    zoho_api_base: str = "https://www.zohoapis.in/crm/v6"
    open_meteo_api_key: str | None = None

    # --- rules policy: diseases that may get automatic medicine advice (comma list, '*' = all with chemical control).
    # Owner decision (19 Oct 2026): '*'. Expert-review diseases, diseases without a chemical cure, low confidence, an unknown
    # disease and a disease of another crop still go to the expert queue (app.rules.policy). Set it EMPTY to go back to the
    # narrow default (apple scab only). Read by app.rules.policy via getattr(settings, ...).
    rules_auto_advice_diseases: str | None = "*"

    # Owner decision (22 Oct 2026): during development a disease is advised on any date, so the season check is OFF.
    # True = the production behaviour: scab only inside its primary season, leaf spots from 1 June, products by growth stage.
    rules_season_check: bool = False

    # --- policy thresholds (mirrors data/reference/rules_config.json; that file wins when loaded)
    min_confidence_show: float = 0.45
    min_confidence_advice: float = 0.65

    @field_validator("env", mode="before")
    @classmethod
    def _known_environment(cls, value: object) -> str:
        """Only dev, test and prod exist. An unknown name must never silently mean 'not production': that switches off the start-up
        guards and honours the fixed development login code. Names that mean production on any host are read as prod."""
        name = str(value).strip().lower()
        name = _ENV_ALIASES.get(name, name)
        if name not in ("dev", "test", "prod"):
            raise ValueError(f"ENV must be one of: dev, test, prod (got {value!r})")
        return name

    @model_validator(mode="after")
    def _prod_uses_the_real_clock(self) -> Settings:
        """The built-in DEMO_CLOCK default freezes the date at the demo day. In production that default must never apply."""
        if self.env == "prod" and "demo_clock" not in self.model_fields_set:
            self.demo_clock = None
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def openai_configured(self) -> bool:
        return not _is_placeholder(self.openai_api_key)

    @property
    def google_tts_configured(self) -> bool:
        return not _is_placeholder(self.google_tts_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
