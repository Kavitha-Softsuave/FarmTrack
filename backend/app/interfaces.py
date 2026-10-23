"""Provider and service interfaces. Every external dependency sits behind one of these so it can be mocked, swapped or replaced
(LLM vendor, TTS engine, Zoho, sensor platform, weather API, push service, vision models).

Implementations live in the package named in the comment. Factories live in app/services/container.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.domain.types import (
    CropResult,
    DiseaseResult,
    FarmerProfile,
    Lang,
    Note,
    QualityResult,
    RuleInput,
    RuleOutput,
    SensorReading,
    SprayRecord,
    ValidatedAdvice,
    WeatherSnapshot,
)


# ---------------------------------------------------------------- vision  (app/vision)
@runtime_checkable
class PhotoQualityChecker(Protocol):
    def check(self, image_bytes: bytes) -> QualityResult: ...


@runtime_checkable
class CropIdentifier(Protocol):
    def identify(self, images: list[bytes], farmer_crops: list[str], client_guess: str | None = None,
                 client_confidence: float | None = None) -> CropResult:
        """Identify the crop. Must fold in the farmer's own crops as a prior and set needs_confirmation / unknown."""
        ...


@runtime_checkable
class DiseaseClassifier(Protocol):
    def classify(self, images: list[bytes], crop_id: str) -> DiseaseResult:
        """Disease for a KNOWN crop. model_covers_crop=False when no photo model exists for that crop."""
        ...


# ---------------------------------------------------------------- rules  (app/rules)
@runtime_checkable
class RulesEngine(Protocol):
    def recommend(self, inp: RuleInput) -> RuleOutput: ...

    def evaluate_risks(self, farmer: FarmerProfile, weather: WeatherSnapshot, now: datetime,
                       history: list[SprayRecord]) -> list: ...   # list[RiskItem]: used by /field and the alert scheduler

    def supported_crops(self) -> list[str]:
        """Crops that have approved-list data (product master rows)."""
        ...

    def check_spray(self, farmer: FarmerProfile, record: SprayRecord, history: list[SprayRecord],
                    now: datetime) -> list: ...   # list[WarningItem] for a NEW diary entry: same-day nutrient mixing, repeated
                                                  # chemical/FRAC group, off-label or banned product, DMI/QoI/SDHI limit reached


# ---------------------------------------------------------------- llm  (app/llm)
@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def generate_json(self, prompt: str, schema: dict[str, Any], schema_name: str = "response",
                      images: list[bytes] | None = None) -> dict[str, Any]:
        """Return a dict that satisfies `schema` (strict JSON). Raise LLMError on failure. Never log prompts containing farmer PII."""
        ...


class LLMError(RuntimeError):
    pass


# ---------------------------------------------------------------- advice  (app/advice)
@runtime_checkable
class AdviceComposer(Protocol):
    def compose(self, inp: RuleInput, out: RuleOutput, notes: list[Note]) -> ValidatedAdvice:
        """Write the farmer-facing advice + a SPOKEN version (ear-friendly, numbers/units as words) from the rule output ONLY.
        Validate against `out`; fall back to the template draft when validation fails."""
        ...


# ---------------------------------------------------------------- voice  (app/voice)
@runtime_checkable
class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, lang: Lang, speed: float = 0.9) -> bytes | None:
        """Return mp3 bytes, or None when the provider is not configured (the app then falls back to on-device TTS)."""
        ...


class AudioStore(Protocol):
    def get_or_create(self, text: str, lang: Lang, speed: float = 0.9) -> tuple[str, str] | None:
        """Return (relative_url, sha256) of cached audio for this text, synthesising if needed; None if TTS is unavailable."""
        ...


# ---------------------------------------------------------------- rag  (app/rag)
@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class KnowledgeBase(Protocol):
    def search(self, query: str, k: int = 5, crop: str | None = None, disease_id: str | None = None,
               stage: str | None = None) -> list[Note]: ...

    def notes_for(self, crop: str, disease_id: str | None, stage: str | None, product_ids: list[str],
                  k: int = 6) -> list[Note]: ...


# ---------------------------------------------------------------- integrations  (app/integrations)
@runtime_checkable
class ZohoAdapter(Protocol):
    def get_farmer(self, farmer_id: str) -> FarmerProfile | None: ...

    def get_history(self, farmer_id: str, until: datetime | None = None) -> list[SprayRecord]:
        """Spray history up to `until` (the demo clock): never return rows dated after it."""
        ...

    def write_spray(self, farmer_id: str, record: SprayRecord) -> bool: ...

    def write_diagnosis(self, farmer_id: str, payload: dict[str, Any]) -> bool: ...


@runtime_checkable
class IoTAdapter(Protocol):
    def latest(self, station_id: str, now: datetime) -> SensorReading | None: ...

    def is_stale(self, station_id: str, now: datetime, max_age_hours: int = 48) -> bool: ...


@runtime_checkable
class WeatherAdapter(Protocol):
    def snapshot(self, station_id: str | None, lat: float | None, lon: float | None, now: datetime) -> WeatherSnapshot: ...


@runtime_checkable
class PushProvider(Protocol):
    def send(self, token: str, title: str, body: str, data: dict[str, str] | None = None) -> bool: ...
