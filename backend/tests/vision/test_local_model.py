"""DISEASE_MODEL_DIR: a locally trained apple model (data/training/train_apple.py) answers for apple instead of the downloaded A+B mix.

Fake models only, except two tests that need torch/timm (skipped without the `ml` extras) and one that needs the exported folder
(skipped when data/training/output/apple_leaf_v1 does not exist)."""
from __future__ import annotations

import json

import pytest

from app.config import REPO_ROOT, Settings
from app.vision import factory
from app.vision.disease import ModelDiseaseClassifier
from app.vision.fallback import SafeDiseaseClassifier
from app.vision.inference import ModelUnavailableError
from app.vision.labels import PV_LABELS
from tests.vision.support import FakeClassifier, distribution, photo_bytes, textured

LOCAL = ["Apple___Apple_scab", "Apple___Marssonina_blotch", "Apple___Alternaria_leaf_spot", "Apple___healthy"]
EXPORTED = REPO_ROOT / "data" / "training" / "output" / "apple_leaf_v1"


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


@pytest.fixture(autouse=True)
def _fresh_model_cache():
    factory.clear_model_cache()
    yield
    factory.clear_model_cache()


def test_setting_defaults_to_unset():
    assert settings().disease_model_dir is None


def test_local_model_answers_for_apple_and_a_still_answers_other_crops():
    a = FakeClassifier(PV_LABELS, distribution(PV_LABELS, {"Tomato___Late_blight": 0.9}))
    b = FakeClassifier(["Healthy"], [1.0])      # must not be used for apple when a local model is set
    local = FakeClassifier(LOCAL, distribution(LOCAL, {"Apple___Marssonina_blotch": 0.8}))
    clf = ModelDiseaseClassifier(a, b, apple_local=local, apple_local_name="local:apple_leaf_v1")
    apple = clf.classify(photo_bytes(), "Apple")
    assert (apple.disease_id, apple.model, apple.model_covers_crop) == ("Apple___Marssonina_blotch", "local:apple_leaf_v1", True)
    assert abs(sum(c.confidence for c in apple.candidates) - 1.0) < 0.01
    assert clf.classify(photo_bytes(), "Tomato").disease_id == "Tomato___Late_blight"


def test_factory_uses_the_configured_dir(monkeypatch, tmp_path):
    seen: list[str] = []
    monkeypatch.setattr(factory, "missing_packages", lambda packages: [])
    monkeypatch.setattr(factory, "load_local_timm_classifier",
                        lambda path: seen.append(path.name) or FakeClassifier(LOCAL, distribution(LOCAL, {"Apple___Apple_scab": 0.7})))
    s = settings(disease_provider="model", disease_model_dir=str(tmp_path / "my_model"), storage_dir=tmp_path)
    disease = factory.build_disease_classifier(s)
    assert isinstance(disease, SafeDiseaseClassifier)
    result = disease.classify(photo_bytes(), "Apple")
    assert result.disease_id == "Apple___Apple_scab" and result.model == "local:my_model"
    disease.classify(photo_bytes(), "Apple")
    assert seen == ["my_model"]                    # loaded once, then cached


def test_empty_dir_setting_means_unset(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "missing_packages", lambda packages: [])
    clf = factory.build_model_disease_classifier(settings(disease_model_dir="  ", storage_dir=tmp_path))
    assert clf._apple_local is None


def test_missing_model_dir_degrades_to_the_stub_result(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "missing_packages", lambda packages: [])
    s = settings(disease_provider="model", disease_model_dir=str(tmp_path / "nope"), storage_dir=tmp_path)
    result = factory.build_disease_classifier(s).classify(photo_bytes(), "Apple")
    assert result.model == "stub" and result.disease_id is None


def test_loader_reports_missing_files(tmp_path):
    pytest.importorskip("torch")
    from app.vision.torch_models import load_local_timm_classifier
    with pytest.raises(ModelUnavailableError, match="model.safetensors"):
        load_local_timm_classifier(tmp_path)


def test_loader_reads_a_tiny_exported_folder(tmp_path):
    torch = pytest.importorskip("torch")
    timm = pytest.importorskip("timm")
    from safetensors.torch import save_file

    from app.vision.torch_models import load_local_timm_classifier
    torch.manual_seed(0)
    net = timm.create_model("resnet10t", pretrained=False, num_classes=4)
    save_file({k: v.half().contiguous() for k, v in net.state_dict().items()}, str(tmp_path / "model.safetensors"))
    (tmp_path / "config.json").write_text(json.dumps({
        "architecture": "resnet10t", "num_classes": 4, "label_names": LOCAL,
        "pretrained_cfg": {"input_size": [3, 64, 64], "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}}), encoding="utf-8")
    model = load_local_timm_classifier(tmp_path)
    assert list(model.labels) == LOCAL
    probs = model.predict_proba([textured((80, 60))])
    assert len(probs) == 1 and len(probs[0]) == 4 and abs(sum(probs[0]) - 1.0) < 1e-4


@pytest.mark.skipif(not (EXPORTED / "model.safetensors").is_file(), reason="trained folder not present (run data/training/train_apple.py)")
def test_exported_apple_model_loads_and_classifies():
    pytest.importorskip("torch")
    pytest.importorskip("timm")
    from app.vision.torch_models import load_local_timm_classifier
    model = load_local_timm_classifier(EXPORTED)
    assert list(model.labels) == LOCAL
    probs = model.predict_proba([textured((300, 240))])[0]
    assert len(probs) == 4 and abs(sum(probs) - 1.0) < 1e-3
