"""Disease classification for a KNOWN crop.

IMPORTANT, read before relying on any number from this module: the confidence values are NOT calibrated. In the first field test
(23 web leaf photos, 19 Oct 2026, review in data/model_test/review_2026-10-19.md) the apple model's confidence did not separate
right from wrong answers (mean 0.85 when right, 0.86 when wrong) and the two models share the same blind spot (both call spotty
apple leaves "scab"). Only apple scab is recognised with any reliability. Downstream policy (rules, confidence cut-offs) must not
treat these values as probabilities of being right; the date/stage prior, the approved list and the agronomist queue do the real
work.

- StubDiseaseClassifier: deterministic placeholder so the whole pipeline runs offline.
- ModelDiseaseClassifier: model A (PlantVillage, 38 classes, crop-masked softmax) for the 14 PlantVillage crops and, for apple,
  model B (8 apple classes, the only one with Marssonina and Alternaria) merged with A's apple evidence.
"""
from __future__ import annotations

from collections.abc import Mapping

from PIL import Image

from app.domain.types import DiseaseCandidate, DiseaseResult
from app.vision.inference import (
    MODEL_A,
    MODEL_B,
    ImageClassifier,
    ModelUnavailableError,
    check_distribution,
    decode_all,
    floor4,
    mean_vectors,
    top_k,
)
from app.vision.labels import (
    A_COVERED_CROPS,
    B_COVERED_CROPS,
    B_MAP,
    DEMO_CROPS,
    canonical_crop,
    pv_labels_for,
)

MAX_CANDIDATES = 5
APPLE_A_WEIGHT = 0.2    # share of model A in the apple mixture (heuristic, see ModelDiseaseClassifier)
STUB_HINT_CONFIDENCE = 0.8


class StubDiseaseClassifier:
    """Deterministic placeholder. Looks at nothing: `model_covers_crop` is True for the demo crops (so the pipeline treats them as
    covered), `disease_id` is None unless a hint was configured for that crop (a demo or a test can force a result with
    `hints={'Apple': 'Apple___Apple_scab'}`; a value may also be `(disease_id, confidence)`)."""

    def __init__(self, hints: Mapping[str, str | tuple[str, float]] | None = None) -> None:
        self._hints = {canonical_crop(crop): hint for crop, hint in (hints or {}).items()}

    def classify(self, images: list[bytes], crop_id: str) -> DiseaseResult:
        crop = canonical_crop(crop_id)
        hint = self._hints.get(crop)
        covered = crop in DEMO_CROPS or hint is not None
        if hint is None:
            return DiseaseResult(crop_id=crop, disease_id=None, model="stub", model_covers_crop=covered)
        disease_id, confidence = (hint, STUB_HINT_CONFIDENCE) if isinstance(hint, str) else hint
        return DiseaseResult(crop_id=crop, disease_id=disease_id, confidence=confidence,
                             candidates=[DiseaseCandidate(disease_id=disease_id, confidence=confidence)], model="stub",
                             model_covers_crop=True)


def covers_crop(crop_id: str) -> bool:
    """True when a photo model exists for the crop (the same answer whether or not the weights are loaded)."""
    crop = canonical_crop(crop_id)
    return crop in A_COVERED_CROPS or crop in B_COVERED_CROPS


class ModelDiseaseClassifier:
    """Model A and B behind the DiseaseClassifier interface (a port of data/model_test/run_models.py).

    Model A (`neghani/plantvillage-mobilenetv2`, temperature already applied by the loader): the probabilities of the crop's classes
    are renormalised ("crop mask", identical to a softmax over those classes only). Crops with a single PlantVillage class
    (Blueberry, Raspberry, Soybean, Citrus, Squash) are not covered: a one-class mask is always 1.0 and says nothing about the leaf.

    Apple additionally runs model B (`ixrbhii/apple-disease-convnext`, 8 classes mapped to catalogue ids with B_MAP). B carries the
    answer (only B has Marssonina, Alternaria, Brown spot, Gray spot). Model A adds its evidence for the classes B also has (scab,
    healthy): p = (1 - w) x B + w x A, w = `apple_a_weight` (default 0.2, heuristic), renormalised. A's mass on classes B lacks
    (black rot, cedar rust) is dropped: B never answers them and A's apple answers were unreliable. On the 23 test leaves w = 0,
    0.2 and 0.5 all gave the same top-1 count as B alone (6/23 exact, 11/23 lenient; see docs/design-notes/vision.md): A adds nothing measurable.
    Raw catalogue ids are returned: the rules apply the catalogue aliases (Brown_spot -> Marssonina, Scab_rust -> scab).

    Several photos: each photo is masked and renormalised on its own, then the probability vectors are averaged.
    """

    def __init__(self, model_a: ImageClassifier, model_b: ImageClassifier, apple_a_weight: float = APPLE_A_WEIGHT,
                 apple_local: ImageClassifier | None = None, apple_local_name: str = "local") -> None:
        if not 0.0 <= apple_a_weight <= 1.0:
            raise ValueError("apple_a_weight must be between 0 and 1")
        self._a = model_a
        self._b = model_b
        self._apple_a_weight = apple_a_weight
        self._apple_local = apple_local          # locally trained apple model (DISEASE_MODEL_DIR): replaces A+B for apple
        self._apple_local_name = apple_local_name

    def covers(self, crop_id: str) -> bool:
        return covers_crop(crop_id)

    def classify(self, images: list[bytes], crop_id: str) -> DiseaseResult:
        crop = canonical_crop(crop_id)
        if not covers_crop(crop):
            return DiseaseResult(crop_id=crop, disease_id=None, model="none", model_covers_crop=False)
        pictures = decode_all(images)
        if crop in B_COVERED_CROPS and self._apple_local is not None:
            return self._result(crop, self._local_apple(pictures), self._apple_local_name)
        dist = self._model_a(pictures, crop)
        model = MODEL_A.short
        if crop in B_COVERED_CROPS:
            dist = _mix(self._model_b(pictures), dist, self._apple_a_weight)
            model = f"{MODEL_A.short}+{MODEL_B.short}"
        return self._result(crop, dist, model)

    @staticmethod
    def _result(crop: str, dist: Mapping[str, float], model: str) -> DiseaseResult:
        ranked = top_k(dist, MAX_CANDIDATES)
        if not ranked:
            return DiseaseResult(crop_id=crop, disease_id=None, model=model, model_covers_crop=True)
        candidates = [DiseaseCandidate(disease_id=d, confidence=floor4(p)) for d, p in ranked]
        return DiseaseResult(crop_id=crop, disease_id=ranked[0][0], confidence=candidates[0].confidence, candidates=candidates,
                             model=model, model_covers_crop=True)

    def _local_apple(self, pictures: list[Image.Image]) -> dict[str, float]:
        """The locally trained model: its labels ARE catalogue ids (train_apple.py writes them), averaged over the photos."""
        assert self._apple_local is not None
        raw = list(self._apple_local.labels)
        vectors = self._apple_local.predict_proba(pictures)
        for probs in vectors:
            check_distribution(probs, raw)
        return dict(zip(raw, mean_vectors(vectors), strict=True))

    def _model_a(self, pictures: list[Image.Image], crop: str) -> dict[str, float]:
        labels = list(self._a.labels)
        wanted = set(pv_labels_for(crop, labels))
        index = [i for i, label in enumerate(labels) if label in wanted]
        if len(index) < 2:
            raise ModelUnavailableError(f"model A has no usable classes for crop {crop}")
        per_photo: list[list[float]] = []
        for probs in self._a.predict_proba(pictures):
            check_distribution(probs, labels)
            masked = [probs[i] for i in index]
            total = sum(masked)
            per_photo.append([p / total for p in masked] if total > 1e-12 else [1.0 / len(index)] * len(index))
        return {labels[i]: p for i, p in zip(index, mean_vectors(per_photo), strict=True)}

    def _model_b(self, pictures: list[Image.Image]) -> dict[str, float]:
        raw = list(self._b.labels)
        unknown = [name for name in raw if name not in B_MAP]
        if unknown:
            raise ModelUnavailableError(f"model B has labels this backend cannot map: {unknown}")
        vectors = self._b.predict_proba(pictures)
        for probs in vectors:
            check_distribution(probs, raw)
        return {B_MAP[name]: p for name, p in zip(raw, mean_vectors(vectors), strict=True)}


def _mix(primary: Mapping[str, float], secondary: Mapping[str, float], secondary_weight: float) -> dict[str, float]:
    """(1 - w) x primary + w x secondary, over the primary's classes only, renormalised."""
    mixed = {key: (1.0 - secondary_weight) * p + secondary_weight * secondary.get(key, 0.0) for key, p in primary.items()}
    total = sum(mixed.values())
    return {key: p / total for key, p in mixed.items()} if total > 1e-12 else dict(primary)
