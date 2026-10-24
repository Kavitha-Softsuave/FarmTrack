"""Loading the real models. The only module that touches torch / timm / transformers, and only inside functions, so importing it
(or the whole app) works in an environment without them. Install with `pip install -e ".[ml]"`.

Weights come from Hugging Face at a PINNED commit (inference.py) and are cached under `<storage_dir>/models`. Because a commit is
immutable the cache is tried first and the network only when the files are missing.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
from PIL import Image

from app.vision.inference import MODEL_A_TEMPERATURE, ImageClassifier, ModelSpec, ModelUnavailableError
from app.vision.labels import PV_LABELS

log = logging.getLogger("app.vision")

TIMM_PACKAGES = ("torch", "timm", "huggingface_hub", "safetensors")
DISEASE_PACKAGES = (*TIMM_PACKAGES, "transformers")


def missing_packages(packages: Sequence[str]) -> list[str]:
    return [p for p in packages if importlib.util.find_spec(p) is None]


def preprocess_timm(img: Image.Image, size: int, mean: Sequence[float], std: Sequence[float]) -> np.ndarray:
    """timm's eval transform for crop_pct 1.0 (what the ixrbhii configs declare): shorter side to `size` (bilinear), centre crop,
    normalise. Returns float32 CHW."""
    w, h = img.size
    short = min(w, h)
    new_w, new_h = max(size, int(size * w / short)), max(size, int(size * h / short))
    resized = img.convert("RGB").resize((new_w, new_h), Image.Resampling.BILINEAR)
    left, top = int(round((new_w - size) / 2.0)), int(round((new_h - size) / 2.0))
    pixels = np.asarray(resized.crop((left, top, left + size, top + size)), dtype=np.float32) / np.float32(255.0)
    normalised = (pixels - np.asarray(mean, dtype=np.float32)) / np.asarray(std, dtype=np.float32)
    return np.ascontiguousarray(normalised.transpose(2, 0, 1), dtype=np.float32)


def _snapshot(spec: ModelSpec, models_dir: Path, patterns: list[str]) -> Path:
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")   # Windows without developer mode: copies instead of symlinks
    from huggingface_hub import snapshot_download  # type: ignore[import-not-found,unused-ignore]

    kwargs = {"repo_id": spec.repo, "revision": spec.revision, "cache_dir": str(models_dir), "allow_patterns": patterns}
    try:
        return Path(snapshot_download(local_files_only=True, **kwargs))
    except Exception:   # not cached yet (LocalEntryNotFoundError): download
        log.info("downloading model %s (first use, about 100 MB)", spec.short)
        return Path(snapshot_download(**kwargs))


class TimmClassifier:
    """A ConvNeXt classifier published as a timm model (the crop detectors and the apple model B)."""

    def __init__(self, spec: ModelSpec, models_dir: Path) -> None:
        self._load(_snapshot(spec, models_dir, ["config.json", "model.safetensors"]))

    @classmethod
    def from_dir(cls, path: Path) -> TimmClassifier:
        """A model saved in a local folder (model.safetensors + config.json) instead of the Hugging Face cache."""
        model = cls.__new__(cls)
        model._load(path)
        return model

    def _load(self, path: Path) -> None:
        import timm  # type: ignore[import-not-found,unused-ignore]
        import torch  # type: ignore[import-not-found,unused-ignore]
        from safetensors.torch import load_file  # type: ignore[import-not-found,unused-ignore]

        cfg = json.loads((path / "config.json").read_text(encoding="utf-8"))
        net = timm.create_model(cfg["architecture"], pretrained=False, num_classes=cfg["num_classes"])
        net.load_state_dict({k: v.float() for k, v in load_file(str(path / "model.safetensors")).items()})   # stored in half precision
        self._net = net.eval()
        self._torch = torch
        self.labels: list[str] = list(cfg["label_names"])
        pretrained = cfg["pretrained_cfg"]
        self._size = int(pretrained["input_size"][1])
        self._mean, self._std = pretrained["mean"], pretrained["std"]

    def predict_proba(self, images: Sequence[Image.Image]) -> list[list[float]]:
        torch = self._torch
        batch = torch.from_numpy(np.stack([preprocess_timm(i, self._size, self._mean, self._std) for i in images]))
        with torch.inference_mode():
            return torch.softmax(self._net(batch).float(), dim=-1).tolist()


class PlantVillageClassifier:
    """Model A: the 38-class PlantVillage MobileNetV2, probabilities = softmax(logits / T) over all 38 classes."""

    def __init__(self, spec: ModelSpec, temperature: float, models_dir: Path) -> None:
        import torch  # type: ignore[import-not-found,unused-ignore]
        from transformers import AutoImageProcessor, AutoModelForImageClassification  # type: ignore[import-not-found,unused-ignore]

        path = _snapshot(spec, models_dir, ["config.json", "preprocessor_config.json", "model.safetensors"])
        self._processor = AutoImageProcessor.from_pretrained(str(path))
        self._model = AutoModelForImageClassification.from_pretrained(str(path)).eval()
        id2label = {int(k): v for k, v in self._model.config.id2label.items()}
        self.labels: list[str] = [id2label[i] for i in range(len(id2label))]
        if self.labels != list(PV_LABELS):
            raise ModelUnavailableError(f"{spec.short} has an unexpected label set; refusing to map it to the catalogue")
        self._torch = torch
        self._temperature = temperature

    def predict_proba(self, images: Sequence[Image.Image]) -> list[list[float]]:
        torch = self._torch
        inputs = self._processor(images=[i.convert("RGB") for i in images], return_tensors="pt")
        with torch.inference_mode():
            logits = self._model(**inputs).logits.float()
        return torch.softmax(logits / self._temperature, dim=-1).tolist()


def _timed(name: str, build: Callable[[], ImageClassifier]) -> ImageClassifier:
    start = time.perf_counter()
    model = build()
    log.info("loaded %s in %.1f s", name, time.perf_counter() - start)
    return model


def load_local_timm_classifier(model_dir: Path) -> ImageClassifier:
    """A timm classifier from a local folder (model.safetensors + config.json), e.g. the output of data/training/train_apple.py."""
    def build() -> ImageClassifier:
        for name in ("model.safetensors", "config.json"):
            if not (model_dir / name).is_file():
                raise ModelUnavailableError(f"{model_dir}: {name} not found")
        return TimmClassifier.from_dir(model_dir)
    return _timed(f"local:{model_dir.name}", build)


def load_timm_classifier(spec: ModelSpec, models_dir: Path) -> ImageClassifier:
    return _timed(spec.short, lambda: TimmClassifier(spec, models_dir))


def load_plantvillage(spec: ModelSpec, models_dir: Path, temperature: float = MODEL_A_TEMPERATURE) -> ImageClassifier:
    return _timed(spec.short, lambda: PlantVillageClassifier(spec, temperature, models_dir))
