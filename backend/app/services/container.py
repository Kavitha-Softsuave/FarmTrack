"""Dependency container: builds every provider from settings. Created by the architect; the PLATFORM agent owns it from here.

Factory contract (each agent exposes exactly these callables; imports are lazy so a missing module fails only when used):
  app.rules.engine.build_rules_engine(settings, disabled_products: Callable[[], set[str]] | None = None) -> RulesEngine
  app.vision.factory.build_quality_checker(settings) -> PhotoQualityChecker
  app.vision.factory.build_crop_identifier(settings) -> CropIdentifier
  app.vision.factory.build_disease_classifier(settings) -> DiseaseClassifier
  app.llm.factory.build_llm(settings) -> LLMProvider
  app.advice.factory.build_advice_composer(settings, llm) -> AdviceComposer
  app.voice.factory.build_audio_store(settings) -> AudioStore
  app.voice.catalogue.load_catalogue(settings, lang, audio_store=None) -> VoiceCatalogueOut
  app.voice.spoken.spoken_out(store: AudioStore | None, en: str, hi: str) -> SpokenOut      # builds SpokenOut with audio refs (None if no TTS)
  app.rag.factory.build_knowledge_base(settings) -> KnowledgeBase
  app.rag.ask.build_ask_service(settings, kb, llm) -> AskService  with .ask(question, language, crop_id) -> AskResult (domain type)
  app.integrations.factory.build_zoho(settings) / build_iot(settings) / build_weather(settings) / build_push(settings)
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.clock import Clock, get_clock
from app.config import Settings, get_settings
from app.interfaces import (
    AdviceComposer,
    AudioStore,
    CropIdentifier,
    DiseaseClassifier,
    IoTAdapter,
    KnowledgeBase,
    LLMProvider,
    PhotoQualityChecker,
    PushProvider,
    RulesEngine,
    WeatherAdapter,
    ZohoAdapter,
)


@dataclass
class Container:
    settings: Settings
    clock: Clock
    rules: RulesEngine
    quality: PhotoQualityChecker
    crop_identifier: CropIdentifier
    disease_classifier: DiseaseClassifier
    llm: LLMProvider
    composer: AdviceComposer
    audio: AudioStore | None          # None when TTS is not configured (clients fall back to on-device speech)
    kb: KnowledgeBase
    ask_service: Any
    zoho: ZohoAdapter
    iot: IoTAdapter
    weather: WeatherAdapter
    push: PushProvider


def disabled_products_from_db() -> set[str]:
    """Products an admin switched off (ProductOverrideRow). Read on every recommendation. Errors propagate on purpose:
    if the switch cannot be read the rules must fail (503), never recommend a product an admin disabled."""
    from app.db.models import ProductOverrideRow
    from app.db.session import session_scope

    with session_scope() as session:
        return set(session.scalars(select(ProductOverrideRow.product_id).where(ProductOverrideRow.enabled.is_(False))))


def build_container(settings: Settings | None = None, disabled_products: Callable[[], set[str]] | None = None) -> Container:
    from app.advice.factory import build_advice_composer
    from app.integrations.factory import build_iot, build_push, build_weather, build_zoho
    from app.llm.factory import build_llm
    from app.rag.ask import build_ask_service
    from app.rag.factory import build_knowledge_base
    from app.rules.engine import build_rules_engine
    from app.vision.factory import build_crop_identifier, build_disease_classifier, build_quality_checker
    from app.voice.factory import build_audio_store

    s = settings or get_settings()
    llm = build_llm(s)
    kb = build_knowledge_base(s)
    return Container(
        settings=s,
        clock=get_clock(),
        rules=build_rules_engine(s, disabled_products or disabled_products_from_db),
        quality=build_quality_checker(s),
        crop_identifier=build_crop_identifier(s),
        disease_classifier=build_disease_classifier(s),
        llm=llm,
        composer=build_advice_composer(s, llm),
        audio=build_audio_store(s),
        kb=kb,
        ask_service=build_ask_service(s, kb, llm),
        zoho=build_zoho(s),
        iot=build_iot(s),
        weather=build_weather(s),
        push=build_push(s),
    )
