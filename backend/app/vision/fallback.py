"""Safe wrappers: a model failure (not installed, no network and no cached weights, bad image, unexpected output) must never break a
scan. The wrapper answers with the always-available fallback and logs the failure once per kind (no farmer data in the message).
"""
from __future__ import annotations

import logging
import threading

from app.domain.types import CropResult, DiseaseResult
from app.interfaces import CropIdentifier, DiseaseClassifier

log = logging.getLogger("app.vision")


class _LogOnce:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def failure(self, what: str, exc: Exception) -> None:
        key = f"{what}:{type(exc).__name__}"
        with self._lock:
            first = key not in self._seen
            self._seen.add(key)
        if first:
            log.warning("%s failed (%s: %s); using the fallback. Further identical failures are not logged.", what,
                        type(exc).__name__, exc)


class SafeCropIdentifier:
    def __init__(self, primary: CropIdentifier, fallback: CropIdentifier) -> None:
        self._primary = primary
        self._fallback = fallback
        self._once = _LogOnce()

    def identify(self, images: list[bytes], farmer_crops: list[str], client_guess: str | None = None,
                 client_confidence: float | None = None) -> CropResult:
        try:
            return self._primary.identify(images, farmer_crops, client_guess, client_confidence)
        except Exception as exc:   # any failure of the model path degrades to the profile identifier
            self._once.failure("crop model", exc)
            return self._fallback.identify(images, farmer_crops, client_guess, client_confidence)


class SafeDiseaseClassifier:
    def __init__(self, primary: DiseaseClassifier, fallback: DiseaseClassifier) -> None:
        self._primary = primary
        self._fallback = fallback
        self._once = _LogOnce()

    def classify(self, images: list[bytes], crop_id: str) -> DiseaseResult:
        try:
            return self._primary.classify(images, crop_id)
        except Exception as exc:
            self._once.failure("disease model", exc)
            return self._fallback.classify(images, crop_id)

