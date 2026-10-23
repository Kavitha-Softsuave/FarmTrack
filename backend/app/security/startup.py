"""Production startup guard: refuse to boot with development defaults."""
from __future__ import annotations

from app.config import Settings

MIN_SECRET_KEY_LENGTH = 32
MIN_ADMIN_KEY_LENGTH = 16


class InsecureConfigurationError(RuntimeError):
    pass


def validate_production_settings(settings: Settings) -> None:
    """No-op outside production. In production raise InsecureConfigurationError listing every problem found."""
    if not settings.is_prod:
        return
    default_secret = Settings.model_fields["secret_key"].default
    default_admin = Settings.model_fields["admin_api_key"].default
    problems: list[str] = []
    if settings.secret_key == default_secret or len(settings.secret_key) < MIN_SECRET_KEY_LENGTH:
        problems.append(f"SECRET_KEY must be set to a random value of at least {MIN_SECRET_KEY_LENGTH} characters "
                        "(the development default is not allowed)")
    if settings.admin_api_key == default_admin or len(settings.admin_api_key) < MIN_ADMIN_KEY_LENGTH:
        problems.append(f"ADMIN_API_KEY must be set to a random value of at least {MIN_ADMIN_KEY_LENGTH} characters "
                        "(the development default is not allowed)")
    if (settings.demo_disease_hints or "").strip():
        problems.append("DEMO_DISEASE_HINTS steers the demo stub classifier and must not be set in production")
    if (settings.demo_clock or "").strip() and not settings.allow_demo_clock_in_prod:
        problems.append("DEMO_CLOCK freezes the date for every farmer and must be empty in production "
                        "(ALLOW_DEMO_CLOCK_IN_PROD=1 only for a deliberate demo server)")
    if any(origin.strip() == "*" for origin in settings.cors_origins):
        problems.append("CORS_ORIGINS must list explicit origins; '*' is not allowed")
    if problems:
        raise InsecureConfigurationError("Refusing to start with ENV=prod: " + "; ".join(problems))
