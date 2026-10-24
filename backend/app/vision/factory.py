"""Builders chosen by settings (crop_id_provider / disease_provider: 'stub' = default, offline; 'model' = the real models).

'model' needs the optional ML packages (`pip install -e ".[ml]"`). Without them, or when the weights cannot be loaded, the model
classes degrade to the stub/profile implementations (logged once), so a scan never fails because of a model.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from app.config import Settings
from app.integrations.reference import load_disease_options
from app.interfaces import CropIdentifier, DiseaseClassifier, PhotoQualityChecker
from app.vision.crop import ModelCropIdentifier, ProfileCropIdentifier
from app.vision.disease import APPLE_A_WEIGHT, ModelDiseaseClassifier, StubDiseaseClassifier
from app.vision.fallback import SafeCropIdentifier, SafeDiseaseClassifier
from app.vision.hints import parse_demo_disease_hints
from app.vision.inference import DETECTOR_16, DETECTOR_36, MODEL_A, MODEL_B, LazyClassifier, ModelSpec
from app.vision.quality import PillowQualityChecker
from app.vision.torch_models import (
    DISEASE_PACKAGES,
    TIMM_PACKAGES,
    load_local_timm_classifier,
    load_plantvillage,
    load_timm_classifier,
    missing_packages,
)

log = logging.getLogger("app.vision")


def _models_dir(settings: Settings) -> str:
    return str(Path(settings.storage_dir) / "models")


@lru_cache
def _timm_model(spec: ModelSpec, models_dir: str) -> LazyClassifier:
    return LazyClassifier(spec.short, lambda: load_timm_classifier(spec, Path(models_dir)))


@lru_cache
def _plantvillage_model(models_dir: str) -> LazyClassifier:
    return LazyClassifier(MODEL_A.short, lambda: load_plantvillage(MODEL_A, Path(models_dir)))


@lru_cache
def _local_model(model_dir: str) -> LazyClassifier:
    return LazyClassifier(f"local:{Path(model_dir).name}", lambda: load_local_timm_classifier(Path(model_dir)))


def clear_model_cache() -> None:
    """Forget the lazily loaded models (tests, or after changing storage_dir)."""
    _timm_model.cache_clear()
    _plantvillage_model.cache_clear()
    _local_model.cache_clear()


def warm_up_models(settings: Settings) -> None:
    """Download (first run only) and load all four models now instead of on the first scan, e.g. at deploy time.
    Raises ModelUnavailableError when one cannot be loaded."""
    models_dir = _models_dir(settings)
    local_dir = (settings.disease_model_dir or "").strip()
    for spec in (DETECTOR_16, DETECTOR_36) if local_dir else (DETECTOR_16, DETECTOR_36, MODEL_B):   # a local apple model replaces B
        _timm_model(spec, models_dir).get()
    _plantvillage_model(models_dir).get()
    if local_dir:
        _local_model(str(Path(local_dir))).get()


def build_quality_checker(settings: Settings) -> PhotoQualityChecker:
    return PillowQualityChecker()


def build_model_crop_identifier(settings: Settings) -> ModelCropIdentifier:
    """The real crop detectors WITHOUT the safety fallback (errors propagate): for evaluation scripts."""
    models_dir = _models_dir(settings)
    return ModelCropIdentifier(_timm_model(DETECTOR_16, models_dir), _timm_model(DETECTOR_36, models_dir))


def build_model_disease_classifier(settings: Settings, apple_a_weight: float = APPLE_A_WEIGHT) -> ModelDiseaseClassifier:
    """The real disease models WITHOUT the safety fallback (errors propagate): for evaluation scripts."""
    models_dir = _models_dir(settings)
    local_dir = (settings.disease_model_dir or "").strip()
    local = _local_model(str(Path(local_dir))) if local_dir else None     # DISEASE_MODEL_DIR: locally trained apple model
    return ModelDiseaseClassifier(_plantvillage_model(models_dir), _timm_model(MODEL_B, models_dir), apple_a_weight,
                                  apple_local=local, apple_local_name=local.name if local else "local")


def build_crop_identifier(settings: Settings) -> CropIdentifier:
    provider = settings.crop_id_provider.strip().lower()
    profile = ProfileCropIdentifier()
    if provider == "stub":
        return profile
    if provider != "model":
        raise ValueError(f"unknown crop_id_provider {settings.crop_id_provider!r} (expected 'stub' or 'model')")
    missing = missing_packages(TIMM_PACKAGES)
    if missing:
        log.warning("crop_id_provider=model but %s are not installed (pip install -e '.[ml]'); using the profile identifier", missing)
        return profile
    return SafeCropIdentifier(build_model_crop_identifier(settings), profile)


def demo_hints(settings: Settings) -> dict[str, tuple[str, float]]:
    """The DEMO_DISEASE_HINTS setting parsed and validated; always empty in production (the setting is refused at start-up anyway)."""
    raw = (settings.demo_disease_hints or "").strip()
    if not raw:
        return {}
    if settings.is_prod:
        log.warning("DEMO_DISEASE_HINTS is set but ENV=prod: ignored")
        return {}
    try:
        known: set[str] | None = {disease_id for disease_id, _ in load_disease_options(settings.data_dir)}
    except OSError:
        known = None                                        # no catalogue to check against: the format is still validated
    hints = parse_demo_disease_hints(raw, known)
    if hints:
        log.warning("DEMO_DISEASE_HINTS active for %s: the stub disease classifier is steered (demo only)", sorted(hints))
    return hints


def build_disease_classifier(settings: Settings, stub_hints: Mapping[str, str | tuple[str, float]] | None = None) -> DiseaseClassifier:
    """`stub_hints` (crop -> disease id, or (id, confidence)) only affects the stub: it lets a demo force a result.
    Without it the DEMO_DISEASE_HINTS setting is used (never in production, see app/vision/hints.py)."""
    provider = settings.disease_provider.strip().lower()
    stub = StubDiseaseClassifier(stub_hints if stub_hints is not None else demo_hints(settings))
    if provider == "stub":
        return stub
    if provider != "model":
        raise ValueError(f"unknown disease_provider {settings.disease_provider!r} (expected 'stub' or 'model')")
    missing = missing_packages(DISEASE_PACKAGES)
    if missing:
        log.warning("disease_provider=model but %s are not installed (pip install -e '.[ml]'); using the stub classifier", missing)
        return stub
    return SafeDiseaseClassifier(build_model_disease_classifier(settings), stub)
