"""Lazy loading, image decoding, probability helpers, pinned model specs and the numpy-only preprocessing."""
from __future__ import annotations

import io
import threading

import numpy as np
import pytest
from PIL import Image

from app.vision.inference import (
    DETECTOR_16,
    DETECTOR_36,
    MODEL_A,
    MODEL_A_TEMPERATURE,
    MODEL_B,
    LazyClassifier,
    ModelUnavailableError,
    decode_all,
    decode_rgb,
    floor4,
    mean_vectors,
    top_k,
)
from app.vision.torch_models import DISEASE_PACKAGES, TIMM_PACKAGES, missing_packages, preprocess_timm
from tests.vision.support import FakeClassifier, jpeg, textured


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_models_are_pinned_to_full_commit_shas():
    for spec in (MODEL_A, MODEL_B, DETECTOR_16, DETECTOR_36):
        assert len(spec.revision) == 40 and set(spec.revision) <= set("0123456789abcdef")
    assert MODEL_A.revision == "d33601185b32cf05b3942661b8d84ffb86dc48ec" and MODEL_A_TEMPERATURE == 0.8845188130635788
    assert MODEL_B.revision == "8bb9c1ae513fff294eed77bdec53ca6fa3c10e8a"
    assert DETECTOR_16.repo == "ixrbhii/leaf-crop-detector-16-convnext" and DETECTOR_36.repo == "ixrbhii/leaf-crop-detector-36-convnext"
    assert MODEL_B.short == "ixrbhii/apple-disease-convnext@8bb9c1a"


# ------------------------------------------------------------------------------------------------------ LazyClassifier
def test_lazy_classifier_loads_once_and_only_when_used():
    calls = []
    lazy = LazyClassifier("m", lambda: calls.append(1) or FakeClassifier(["a", "b"], [0.4, 0.6]))
    assert calls == []
    assert list(lazy.labels) == ["a", "b"] and lazy.predict_proba([Image.new("RGB", (4, 4))]) == [[0.4, 0.6]]
    assert calls == [1]


def test_lazy_classifier_remembers_a_failure_then_retries_after_the_delay():
    clock, calls = Clock(), []

    def loader():
        calls.append(clock.now)
        if len(calls) == 1:
            raise OSError("connection refused")
        return FakeClassifier(["a"], [1.0])

    lazy = LazyClassifier("detector", loader, retry_after_s=300, monotonic=clock)
    with pytest.raises(ModelUnavailableError, match="detector: OSError: connection refused"):
        lazy.get()
    clock.now += 299
    with pytest.raises(ModelUnavailableError):
        lazy.get()
    assert len(calls) == 1                       # inside the back-off window the loader is not called again
    clock.now += 2
    assert list(lazy.labels) == ["a"] and len(calls) == 2
    assert lazy.get() is lazy.get() and len(calls) == 2


def test_lazy_classifier_keeps_a_model_unavailable_error_as_is():
    err = ModelUnavailableError("torch is not installed")
    lazy = LazyClassifier("m", lambda: (_ for _ in ()).throw(err))
    with pytest.raises(ModelUnavailableError) as raised:
        lazy.get()
    assert raised.value is err


def test_lazy_classifier_is_safe_under_concurrent_first_use():
    calls, gate = [], threading.Barrier(8)

    def loader():
        calls.append(1)
        return FakeClassifier(["a"], [1.0])

    lazy = LazyClassifier("m", loader)
    models = []

    def work():
        gate.wait()
        models.append(lazy.get())

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1 and len({id(m) for m in models}) == 1


# ------------------------------------------------------------------------------------------------------ helpers
def test_decode_rgb_returns_rgb_and_bounds_the_size():
    img = decode_rgb(jpeg(textured((3000, 1500))))
    assert img.mode == "RGB" and max(img.size) <= 1024
    buf = io.BytesIO()
    Image.new("L", (50, 40)).save(buf, "PNG")
    assert decode_rgb(buf.getvalue()).mode == "RGB"


@pytest.mark.parametrize("data", [b"", b"nope"])
def test_decode_rgb_rejects_garbage(data):
    with pytest.raises(ValueError, match="unreadable"):
        decode_rgb(data)


def test_decode_all_needs_at_least_one_image():
    with pytest.raises(ValueError, match="no images"):
        decode_all([])
    assert len(decode_all([jpeg(textured((64, 64)))] * 3)) == 3


def test_mean_vectors():
    assert mean_vectors([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]) == pytest.approx([0.5, 0.5])
    with pytest.raises(ValueError):
        mean_vectors([])
    with pytest.raises(ValueError, match="differ"):
        mean_vectors([[1.0], [0.5, 0.5]])


def test_floor4_never_rounds_up():
    assert floor4(0.99999) == 0.9999 and floor4(0.8) == 0.8 and floor4(0.29) == 0.29 and floor4(1.0) == 1.0 and floor4(0.0) == 0.0


def test_top_k_is_sorted_and_deterministic():
    assert top_k({"b": 0.3, "a": 0.3, "c": 0.4, "z": 0.0}, 3) == [("c", 0.4), ("a", 0.3), ("b", 0.3)]


# ------------------------------------------------------------------------------------------------------ preprocessing (numpy only)
def test_preprocess_shape_dtype_and_normalisation():
    mean, std = [0.5, 0.5, 0.5], [0.25, 0.25, 0.25]
    arr = preprocess_timm(Image.new("RGB", (300, 200), (255, 0, 127)), 224, mean, std)
    assert arr.shape == (3, 224, 224) and arr.dtype == np.float32 and arr.flags["C_CONTIGUOUS"]
    assert arr[0, 0, 0] == pytest.approx((1.0 - 0.5) / 0.25) and arr[1, 5, 5] == pytest.approx(-2.0)
    assert arr[2, 9, 9] == pytest.approx((127 / 255 - 0.5) / 0.25, abs=1e-3)


def test_preprocess_scales_the_short_side_then_centre_crops():
    img = Image.new("RGB", (448, 224), (0, 0, 0))
    img.paste((255, 255, 255), (112, 0, 336, 224))           # the middle 224 x 224 is white, the sides black
    arr = preprocess_timm(img, 224, [0, 0, 0], [1, 1, 1])
    assert arr.min() == pytest.approx(1.0) and arr.max() == pytest.approx(1.0)      # the centre crop sees only the white square
    tall = Image.new("RGB", (100, 400), (255, 255, 255))
    assert preprocess_timm(tall, 224, [0, 0, 0], [1, 1, 1]).shape == (3, 224, 224)


def test_preprocess_upscales_small_photos():
    assert preprocess_timm(Image.new("RGB", (60, 50)), 224, [0, 0, 0], [1, 1, 1]).shape == (3, 224, 224)


def test_missing_packages_reports_what_is_absent():
    assert missing_packages(["json", "definitely_not_a_package_xyz"]) == ["definitely_not_a_package_xyz"]
    assert set(TIMM_PACKAGES) < set(DISEASE_PACKAGES)
