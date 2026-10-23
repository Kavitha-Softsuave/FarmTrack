"""Factory used by app.services.container."""
from __future__ import annotations

import logging

from app.config import Settings
from app.interfaces import LLMProvider
from app.llm.mock import MockLLM
from app.llm.openai_client import OpenAILLM

logger = logging.getLogger(__name__)
_logged: set[str] = set()


def _log_once(message: str) -> None:
    if message not in _logged:
        _logged.add(message)
        logger.warning(message)


def _temperature(raw: str) -> float | None:
    """Settings carry the temperature as text so it can be switched off ('' or 'none') for models that reject it."""
    value = (raw or "").strip().lower()
    if value in ("", "none", "null"):
        return None
    try:
        return float(value)
    except ValueError:
        _log_once("OPENAI_TEMPERATURE is not a number; sending no temperature")
        return None


def build_llm(settings: Settings) -> LLMProvider:
    """OpenAI only when it is selected AND a real key is set; otherwise the offline mock (logged once)."""
    if settings.llm_provider == "openai":
        if settings.openai_configured and settings.openai_api_key:
            return OpenAILLM(
                settings.openai_api_key, settings.openai_model, temperature=_temperature(settings.openai_temperature),
                max_output_tokens=settings.openai_max_output_tokens, image_detail=settings.openai_image_detail)
        _log_once("LLM_PROVIDER=openai but OPENAI_API_KEY is not set: using the offline MockLLM")
    elif settings.llm_provider != "mock":
        _log_once(f"Unknown LLM_PROVIDER {settings.llm_provider!r}: using the offline MockLLM")
    return MockLLM()
