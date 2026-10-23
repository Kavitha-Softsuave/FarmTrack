"""Factory used by app.services.container."""
from __future__ import annotations

from app.advice.composer import LLMAdviceComposer
from app.advice.refdata import load_refdata
from app.config import Settings
from app.interfaces import AdviceComposer, LLMProvider


def build_advice_composer(settings: Settings, llm: LLMProvider) -> AdviceComposer:
    return LLMAdviceComposer(llm, load_refdata(str(settings.data_dir)))
