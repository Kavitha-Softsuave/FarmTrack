"""Synthetic photos and fake classifiers for the vision tests (no torch, no network)."""
from __future__ import annotations

import io
from collections.abc import Mapping, Sequence

import numpy as np
from PIL import Image, ImageFilter

from app.config import REPO_ROOT

LEAF_PHOTOS = sorted((REPO_ROOT / "data" / "images" / "testset_v1" / "leaf").glob("*/*.jpg"))
FRUIT_PHOTOS = sorted((REPO_ROOT / "data" / "images" / "testset_v1" / "fruit_info").glob("*/*.jpg"))


def textured(size: tuple[int, int] = (480, 360), base: tuple[int, int, int] = (70, 140, 60), noise: float = 14.0, seed: int = 1,
             spots: bool = True) -> Image.Image:
    """A sharp, noisy, leaf-coloured picture (noise = fine detail the blur score reacts to) with a few dark spots."""
    rng = np.random.default_rng(seed)
    w, h = size
    arr = np.empty((h, w, 3), dtype=np.float32)
    arr[:] = base
    arr += rng.normal(0.0, noise, (h, w, 1))
    for _ in range(12 if spots else 0):
        cy, cx, r = int(rng.integers(0, h)), int(rng.integers(0, w)), int(rng.integers(6, 20))
        yy, xx = np.ogrid[:h, :w]
        arr[(yy - cy) ** 2 + (xx - cx) ** 2 < r * r] = (60, 40, 25)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def jpeg(img: Image.Image, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def blurred(img: Image.Image, radius: float = 4.0) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius))


def photo_bytes(n: int = 1) -> list[bytes]:
    """n small valid photos (the fake models never look at the pixels)."""
    return [jpeg(textured((64, 64), seed=i)) for i in range(n)]


def distribution(labels: Sequence[str], probs: Mapping[str, float]) -> list[float]:
    """A probability vector: the given labels get their probability, the rest share what is left equally."""
    unknown = set(probs) - set(labels)
    assert not unknown, f"not labels of this model: {unknown}"
    rest = [lab for lab in labels if lab not in probs]
    left = max(0.0, 1.0 - sum(probs.values()))
    return [probs[lab] if lab in probs else left / len(rest) for lab in labels]


class FakeClassifier:
    """Returns the given vectors, one per photo (cycling when there are more photos than vectors)."""

    def __init__(self, labels: Sequence[str], *vectors: Sequence[float]) -> None:
        self.labels = list(labels)
        self._vectors = [list(v) for v in vectors]
        self.calls = 0

    def predict_proba(self, images: Sequence[Image.Image]) -> list[list[float]]:
        self.calls += 1
        return [list(self._vectors[i % len(self._vectors)]) for i in range(len(images))]


class ExplodingClassifier:
    """A model that must never be touched (or that fails when it is)."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or AssertionError("this model must not be used")

    @property
    def labels(self) -> Sequence[str]:
        raise self._error

    def predict_proba(self, images: Sequence[Image.Image]) -> list[list[float]]:
        raise self._error
