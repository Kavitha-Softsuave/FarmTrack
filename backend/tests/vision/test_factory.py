from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.config import BACKEND_ROOT, Settings
from app.interfaces import CropIdentifier, DiseaseClassifier, PhotoQualityChecker
from app.vision import factory
from app.vision.crop import ProfileCropIdentifier
from app.vision.disease import StubDiseaseClassifier
from app.vision.fallback import SafeCropIdentifier, SafeDiseaseClassifier
from app.vision.inference import ModelUnavailableError
from app.vision.quality import PillowQualityChecker
from tests.vision.support import FakeClassifier, photo_bytes


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)       # never the repo-root .env


@pytest.fixture(autouse=True)
def _fresh_model_cache():
    factory.clear_model_cache()
    yield
    factory.clear_model_cache()


def test_quality_checker_builder():
    checker = factory.build_quality_checker(settings())
    assert isinstance(checker, PillowQualityChecker) and isinstance(checker, PhotoQualityChecker)


def test_stub_is_the_default_and_needs_no_models():
    s = settings()
    assert (s.crop_id_provider, s.disease_provider) == ("stub", "stub")
    crop, disease = factory.build_crop_identifier(s), factory.build_disease_classifier(s)
    assert isinstance(crop, ProfileCropIdentifier) and isinstance(crop, CropIdentifier)
    assert isinstance(disease, StubDiseaseClassifier) and isinstance(disease, DiseaseClassifier)


def test_provider_names_are_case_and_space_insensitive():
    assert isinstance(factory.build_crop_identifier(settings(crop_id_provider=" Stub ")), ProfileCropIdentifier)


@pytest.mark.parametrize("kwargs", [{"crop_id_provider": "magic"}, {"disease_provider": "magic"}])
def test_unknown_provider_is_a_clear_error(kwargs):
    s = settings(**kwargs)
    with pytest.raises(ValueError, match="magic"):
        factory.build_crop_identifier(s)
        factory.build_disease_classifier(s)


def test_stub_hints_reach_the_stub_classifier():
    disease = factory.build_disease_classifier(settings(), stub_hints={"Apple": "Apple___Apple_scab"})
    assert disease.classify(photo_bytes(), "Apple").disease_id == "Apple___Apple_scab"


def test_model_provider_without_the_ml_packages_degrades_with_a_warning(monkeypatch, caplog):
    monkeypatch.setattr(factory, "missing_packages", lambda packages: ["torch"])
    s = settings(crop_id_provider="model", disease_provider="model")
    with caplog.at_level("WARNING", logger="app.vision"):
        crop, disease = factory.build_crop_identifier(s), factory.build_disease_classifier(s)
    assert isinstance(crop, ProfileCropIdentifier) and isinstance(disease, StubDiseaseClassifier)
    assert len([r for r in caplog.records if "not installed" in r.getMessage()]) == 2


def test_model_provider_wraps_the_real_models_in_the_safe_fallback(monkeypatch):
    monkeypatch.setattr(factory, "missing_packages", lambda packages: [])
    s = settings(crop_id_provider="model", disease_provider="model")
    assert isinstance(factory.build_crop_identifier(s), SafeCropIdentifier)
    assert isinstance(factory.build_disease_classifier(s), SafeDiseaseClassifier)


def test_model_load_failure_falls_back_end_to_end(monkeypatch, tmp_path):
    attempts: list[str] = []

    def failing_loader(spec, models_dir):
        attempts.append(spec.key)
        raise ModelUnavailableError("offline")

    monkeypatch.setattr(factory, "missing_packages", lambda packages: [])
    monkeypatch.setattr(factory, "load_timm_classifier", failing_loader)
    monkeypatch.setattr(factory, "load_plantvillage", lambda spec, models_dir: failing_loader(spec, models_dir))
    s = settings(crop_id_provider="model", disease_provider="model", storage_dir=tmp_path)
    crop, disease = factory.build_crop_identifier(s), factory.build_disease_classifier(s)
    first = crop.identify(photo_bytes(), ["Apple"], "Apple", 0.9)
    again = crop.identify(photo_bytes(), ["Apple"], "Apple", 0.9)
    assert first == again and first.crop_id == "Apple" and first.source == "on_device"
    assert attempts == ["D16"]      # the failed load is remembered: no second attempt, no network hammering
    result = disease.classify(photo_bytes(), "Tomato")
    assert (result.model, result.disease_id, result.model_covers_crop) == ("stub", None, True)
    assert disease.classify(photo_bytes(), "Pea").model_covers_crop is False      # answered without touching a model


def test_warm_up_loads_all_four_models_and_reports_a_failure(monkeypatch, tmp_path):
    loaded: list[str] = []
    monkeypatch.setattr(factory, "load_timm_classifier", lambda spec, models_dir: loaded.append(spec.key) or FakeClassifier(["a"], [1.0]))
    monkeypatch.setattr(factory, "load_plantvillage", lambda spec, models_dir: loaded.append(spec.key) or FakeClassifier(["a"], [1.0]))
    factory.warm_up_models(settings(storage_dir=tmp_path))
    assert sorted(loaded) == ["A", "B", "D16", "D36"]
    factory.clear_model_cache()
    monkeypatch.setattr(factory, "load_timm_classifier", lambda spec, models_dir: (_ for _ in ()).throw(ModelUnavailableError("offline")))
    with pytest.raises(ModelUnavailableError):
        factory.warm_up_models(settings(storage_dir=tmp_path))


def test_models_are_cached_under_storage_dir_models(monkeypatch, tmp_path):
    seen: list[Path] = []
    monkeypatch.setattr(factory, "missing_packages", lambda packages: [])
    monkeypatch.setattr(factory, "load_timm_classifier", lambda spec, models_dir: seen.append(models_dir) or (_ for _ in ()).throw(
        ModelUnavailableError("stop")))
    crop = factory.build_crop_identifier(settings(crop_id_provider="model", storage_dir=tmp_path))
    crop.identify(photo_bytes(), ["Apple"])
    assert seen == [tmp_path / "models"]


def test_importing_the_factory_never_imports_torch():
    code = "import sys, app.vision.factory; print(','.join(m for m in ('torch', 'timm', 'transformers') if m in sys.modules))"
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_ROOT, capture_output=True, text=True, check=True)   # noqa: S603
    assert done.stdout.strip() == ""
