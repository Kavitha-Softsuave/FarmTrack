from app.config import Settings


def make_settings(**overrides) -> Settings:
    """Settings that ignore the repo-root .env (it holds real secrets)."""
    return Settings(_env_file=None, **overrides)
