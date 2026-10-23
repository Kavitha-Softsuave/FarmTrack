"""Torch-free plumbing shared by the model-backed vision classes: pinned model specs, the classifier protocol, lazy loading with a
retry back-off, image decoding and probability helpers. Real torch code lives in torch_models.py and is imported only on first use.
"""
from __future__ import annotations

import io
import math
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

MAX_INFERENCE_SIDE = 1024   # photos are shrunk to this long side before they reach a model (models resize to 224 anyway)
MAX_PIXELS = 100_000_000   # refuse absurd images (decompression bombs) as unreadable


class ModelUnavailableError(RuntimeError):
    """A model could not be loaded (torch/timm not installed, no network and no cached weights, corrupt file ...)."""


@dataclass(frozen=True)
class ModelSpec:
    key: str
    repo: str
    revision: str           # full commit sha: weights are immutable, so a cached copy is always valid
    note: str = ""

    @property
    def short(self) -> str:
        return f"{self.repo}@{self.revision[:7]}"


# Model A: on-device candidate, also used on the server for the 14 PlantVillage crops (neghani/..., Apache-2.0)
MODEL_A = ModelSpec("A", "neghani/plantvillage-mobilenetv2", "d33601185b32cf05b3942661b8d84ffb86dc48ec")
MODEL_A_TEMPERATURE = 0.8845188130635788   # fitted by the model's author; applied as softmax(logits / T)
# Model B: server apple model, 8 classes incl. Marssonina and Alternaria (ixrbhii/..., CC-BY-4.0)
MODEL_B = ModelSpec("B", "ixrbhii/apple-disease-convnext", "8bb9c1ae513fff294eed77bdec53ca6fa3c10e8a")
# Crop detectors (ixrbhii, CC-BY-4.0). Same weights as detectors/original and detectors/new of ixrbhii/multicrop-disease-models
# (identical SHA-256 checked on 19 Oct 2026); the standalone repos are used because their config.json carries label_names.
DETECTOR_16 = ModelSpec("D16", "ixrbhii/leaf-crop-detector-16-convnext", "87da121765fcfa7d2d20c1798fb06de495499eed",
                        "16 crops, 99.8 % on its own test set")
DETECTOR_36 = ModelSpec("D36", "ixrbhii/leaf-crop-detector-36-convnext", "e2e60f990a4f07e004ce19fe2f146849bd65d1ba",
                        "36 crops, 98.4 % on its own test set")


class ImageClassifier(Protocol):
    """What the model-backed classes need. Real implementations are in torch_models.py; tests inject fakes."""

    @property
    def labels(self) -> Sequence[str]: ...

    def predict_proba(self, images: Sequence[Image.Image]) -> list[list[float]]:
        """One probability vector per image, aligned with `labels`."""
        ...


class LazyClassifier:
    """Loads a classifier on first use. A failed load is remembered for `retry_after_s` seconds so a missing network or model
    is not retried (and slow) on every request, then tried again."""

    def __init__(self, name: str, loader: Callable[[], ImageClassifier], retry_after_s: float = 300.0,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.name = name
        self._loader = loader
        self._retry_after_s = retry_after_s
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._model: ImageClassifier | None = None
        self._failed_at: float | None = None
        self._failure: ModelUnavailableError | None = None

    def get(self) -> ImageClassifier:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            if self._failure is not None and self._failed_at is not None and self._monotonic() - self._failed_at < self._retry_after_s:
                raise self._failure
            try:
                self._model = self._loader()
            except ModelUnavailableError as exc:
                self._failed_at, self._failure = self._monotonic(), exc
                raise
            except Exception as exc:   # any loader failure means "unavailable", never a crash of the request
                err = ModelUnavailableError(f"{self.name}: {type(exc).__name__}: {exc}")
                err.__cause__ = exc
                self._failed_at, self._failure = self._monotonic(), err
                raise err from exc
            self._failed_at = self._failure = None
            return self._model

    @property
    def labels(self) -> Sequence[str]:
        return self.get().labels

    def predict_proba(self, images: Sequence[Image.Image]) -> list[list[float]]:
        return self.get().predict_proba(images)


def decode_rgb(data: bytes) -> Image.Image:
    """Bytes -> RGB image with a bounded size. Raises ValueError for anything that is not a readable image."""
    try:
        opened = Image.open(io.BytesIO(data))
        if opened.size[0] * opened.size[1] > MAX_PIXELS:
            raise ValueError("image too large")
        opened.draft("RGB", (MAX_INFERENCE_SIDE, MAX_INFERENCE_SIDE))
        rgb = opened.convert("RGB")
    except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError) as exc:
        raise ValueError("unreadable image") from exc
    rgb.thumbnail((MAX_INFERENCE_SIDE, MAX_INFERENCE_SIDE), Image.Resampling.BOX)
    return rgb


def decode_all(images: Sequence[bytes]) -> list[Image.Image]:
    if not images:
        raise ValueError("no images")
    return [decode_rgb(b) for b in images]


def mean_vectors(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Element-wise mean of equally long probability vectors."""
    n = len(vectors)
    if n == 0:
        raise ValueError("no vectors")
    width = len(vectors[0])
    if any(len(v) != width for v in vectors):
        raise ValueError("vectors differ in length")
    return [sum(v[i] for v in vectors) / n for i in range(width)]


def check_distribution(probs: Sequence[float], labels: Sequence[str]) -> None:
    if len(probs) != len(labels):
        raise ValueError(f"model returned {len(probs)} probabilities for {len(labels)} labels")


def floor4(p: float) -> float:
    """Truncate (not round) to 4 decimals, so a list of rounded probabilities never adds up to more than 1."""
    return math.floor(p * 10_000 + 1e-9) / 10_000


def top_k(dist: Mapping[str, float], k: int) -> list[tuple[str, float]]:
    """Highest first; ties broken by name so results are deterministic."""
    return sorted(((key, p) for key, p in dist.items() if p > 0), key=lambda kv: (-kv[1], kv[0]))[:k]
