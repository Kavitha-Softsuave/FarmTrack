"""Crop identification: the first and most critical gate (a wrong crop means a wrong disease list and a wrong medicine list).

Two implementations of CropIdentifier:
- ProfileCropIdentifier: no image model. Uses the on-device guess (client_guess / client_confidence) and the farmer's own crops.
  It is the default ('stub') and the fallback when the server model is unavailable.
- ModelCropIdentifier: the two ixrbhii crop detectors (16 and 36 crops) combined with the farmer's crops as a prior.

ALL confidence numbers returned here are heuristic: they order the candidates and drive `needs_confirmation`, they are not
calibrated probabilities (no field data exists yet). Candidate confidences never sum to more than 1.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from PIL import Image

from app.domain.types import CropCandidate, CropResult
from app.vision.inference import ImageClassifier, check_distribution, decode_all, floor4, mean_vectors, top_k
from app.vision.labels import canonical_crop, canonical_crops, detector_label_to_crop

# ------------------------------------------------------------------------------------------------ ProfileCropIdentifier
STRONG_GUESS = 0.5          # on-device guess accepted without asking when it is also one of the farmer's crops
PROFILE_ONLY = 0.6          # the farmer grows one crop and we have no guess
PROFILE_AGREES = 0.75       # one crop, a weak guess that agrees
PROFILE_VS_WEAK_GUESS = 0.55   # one crop, a weak guess that contradicts it: the profile still leads
UNDECIDED_SHARE = 0.3       # weight of each candidate when there is nothing to choose between them
MIN_USABLE_GUESS = 0.3      # with no profile at all, a guess below this is reported as unknown
NEGLIGIBLE_GUESS = 0.05     # a guess this unsure is treated as no guess at all


def _clean_confidence(value: float | None) -> float | None:
    if value is None or math.isnan(value):
        return None
    return min(1.0, max(0.0, float(value)))


def _candidates(pairs: Sequence[tuple[str, float]]) -> list[CropCandidate]:
    """Sorted by confidence (stable), scaled down when they would add up to more than 1."""
    ordered = sorted(pairs, key=lambda kv: -kv[1])
    total = sum(p for _, p in ordered)
    scale = 1.0 / total if total > 1.0 else 1.0
    return [CropCandidate(crop_id=c, confidence=floor4(p * scale)) for c, p in ordered if p > 0]


def _others(top_conf: float, others: Sequence[str]) -> list[tuple[str, float]]:
    """The rest of the farmer's crops share the remaining mass, never more than the top candidate has."""
    if not others:
        return []
    share = min(top_conf, (1.0 - top_conf) / len(others))
    return [(c, share) for c in others]


class ProfileCropIdentifier:
    """Decision table (g = on-device guess, c = its confidence, F = the farmer's crops):

    1. g in F and c >= 0.5                  -> g, source on_device, no confirmation
    2. F == [x] and no guess                -> x, source farmer_profile, ASK (one tap)
       F == [x] and g == x (weak c)         -> x, source farmer_profile, no confirmation (the guess agrees)
    3. g in F, several crops, weak c        -> g, source on_device, ASK
    4. g not in F (profile contradicted or empty), candidates ordered by evidence, ASK:
       c >= 0.5                             -> g first, then F
       weak c, F == [x]                     -> x first (the profile leads), then g
       weak c, several crops in F           -> unknown, candidates F + g
       weak c, F empty                      -> g when c >= 0.3, else unknown
    5. no guess, several crops              -> unknown, candidates = F, ASK
    6. no guess, no crops                   -> unknown, no candidates, ASK
    A guess with confidence below 0.05 counts as no guess. Names are normalised (canonical_crop), so 'apple', 'Apple' and
    'Capsicum' / 'Pepper' compare equal.
    """

    def identify(self, images: list[bytes], farmer_crops: list[str], client_guess: str | None = None,
                 client_confidence: float | None = None) -> CropResult:
        crops = canonical_crops(farmer_crops)
        guess = canonical_crop(client_guess) if client_guess and client_guess.strip() else None
        conf = _clean_confidence(client_confidence)
        weak = conf if conf is not None else MIN_USABLE_GUESS
        if guess is not None and conf is not None and conf < NEGLIGIBLE_GUESS:
            guess = None
        if guess is None:
            return self._without_guess(crops)
        if guess in crops:
            return self._guess_in_profile(guess, crops, conf, weak)
        return self._guess_outside_profile(guess, crops, conf, weak)

    @staticmethod
    def _without_guess(crops: list[str]) -> CropResult:
        if len(crops) == 1:
            return CropResult(crop_id=crops[0], confidence=PROFILE_ONLY, candidates=_candidates([(crops[0], PROFILE_ONLY)]),
                              source="farmer_profile", needs_confirmation=True)
        if crops:
            return CropResult(crop_id=None, candidates=_candidates([(c, UNDECIDED_SHARE) for c in crops]), source="farmer_profile",
                              needs_confirmation=True, unknown=True)
        return CropResult(crop_id=None, source="stub", needs_confirmation=True, unknown=True)

    @staticmethod
    def _guess_in_profile(guess: str, crops: list[str], conf: float | None, weak: float) -> CropResult:
        others = [c for c in crops if c != guess]
        if conf is not None and conf >= STRONG_GUESS:
            return CropResult(crop_id=guess, confidence=conf, candidates=_candidates([(guess, conf), *_others(conf, others)]),
                              source="on_device", needs_confirmation=False)
        if not others:   # the farmer's only crop, and the weak guess agrees with it
            return CropResult(crop_id=guess, confidence=PROFILE_AGREES, candidates=_candidates([(guess, PROFILE_AGREES)]),
                              source="farmer_profile", needs_confirmation=False)
        return CropResult(crop_id=guess, confidence=weak, candidates=_candidates([(guess, weak), *_others(weak, others)]),
                          source="on_device", needs_confirmation=True)

    @staticmethod
    def _guess_outside_profile(guess: str, crops: list[str], conf: float | None, weak: float) -> CropResult:
        if conf is not None and conf >= STRONG_GUESS:
            return CropResult(crop_id=guess, confidence=conf, candidates=_candidates([(guess, conf), *_others(conf, crops)]),
                              source="on_device", needs_confirmation=True)
        guess_weight = min(weak, STRONG_GUESS - 0.05)
        if len(crops) == 1:
            return CropResult(crop_id=crops[0], confidence=PROFILE_VS_WEAK_GUESS,
                              candidates=_candidates([(crops[0], PROFILE_VS_WEAK_GUESS), (guess, guess_weight)]),
                              source="farmer_profile", needs_confirmation=True)
        if crops:
            return CropResult(crop_id=None, candidates=_candidates([*((c, UNDECIDED_SHARE) for c in crops), (guess, guess_weight)]),
                              source="farmer_profile", needs_confirmation=True, unknown=True)
        if weak >= MIN_USABLE_GUESS:
            return CropResult(crop_id=guess, confidence=weak, candidates=_candidates([(guess, weak)]), source="on_device",
                              needs_confirmation=True)
        return CropResult(crop_id=None, candidates=_candidates([(guess, weak)]), source="on_device", needs_confirmation=True, unknown=True)


# ------------------------------------------------------------------------------------------------ ModelCropIdentifier
PRIOR_FLOOR = 0.15       # prior weight of a crop the farmer does not grow (farmer's own crops weigh 1.0): a new crop can still win
MIN_MARGIN = 0.25        # posterior gap between the best two crops below which the farmer is asked
MIN_EVIDENCE = 0.6       # the detectors' own probability for the winner below which the farmer is asked (the repo card refuses < 0.6)
UNKNOWN_BELOW = 0.3      # winner's posterior below which the crop is reported as unknown (flat, clueless detector output)
MAX_CANDIDATES = 3


class ModelCropIdentifier:
    """Server crop detection with the ixrbhii detectors (16 and 36 crops), then the farmer's crops as a prior.

    1. Each detector's probabilities are averaged over the photos, labels mapped to catalogue crop ids.
    2. The two detectors know different crops (10 crops only the 16-detector knows, 30 only the 36-detector), so a crop's evidence is
       the larger of the two probabilities and the evidence is renormalised. If the detectors confidently name different crops the
       margin shrinks and the farmer is asked, which is the safe outcome.
    3. Farmer crops no detector knows (pea, wheat, kiwi, plum ...) get the detectors' leftover doubt (1 - best probability) as
       evidence, so a confused detector can still end up on the farmer's own crop.
    4. posterior = evidence x prior (1.0 for the farmer's crops, `prior_floor` for others), renormalised.
    5. needs_confirmation when: the winner is not one of the farmer's crops (when the profile is known), the margin to the runner-up
       is small, the detectors' own probability for the winner is below 0.6, or the prior changed the detectors' favourite.
       An empty profile is "no information": it never forces a confirmation by itself.

    The on-device guess is ignored here: the on-device model was confidently wrong on the field test, and the server detectors are
    the better evidence. `source` is 'server_model'. The returned confidence is the posterior of the winner: heuristic, not calibrated.
    """

    def __init__(self, detector_16: ImageClassifier, detector_36: ImageClassifier, prior_floor: float = PRIOR_FLOOR,
                 min_margin: float = MIN_MARGIN, min_evidence: float = MIN_EVIDENCE, unknown_below: float = UNKNOWN_BELOW) -> None:
        self._detectors = (detector_16, detector_36)
        self.prior_floor = prior_floor
        self.min_margin = min_margin
        self.min_evidence = min_evidence
        self.unknown_below = unknown_below

    def _evidence(self, pictures: list[Image.Image]) -> dict[str, float]:
        evidence: dict[str, float] = {}
        for det in self._detectors:
            labels = list(det.labels)
            probs = mean_vectors(det.predict_proba(pictures))
            check_distribution(probs, labels)
            for label, p in zip(labels, probs, strict=True):
                crop = detector_label_to_crop(label)
                evidence[crop] = max(evidence.get(crop, 0.0), p)
        return evidence

    def identify(self, images: list[bytes], farmer_crops: list[str], client_guess: str | None = None,
                 client_confidence: float | None = None) -> CropResult:
        evidence = self._evidence(decode_all(images))
        farmer = canonical_crops(farmer_crops)
        raw_top = max(evidence, key=lambda c: (evidence[c], c))
        unseen = [c for c in farmer if c not in evidence]
        for c in unseen:
            evidence[c] = max(0.0, 1.0 - evidence[raw_top]) / len(unseen)
        total = sum(evidence.values()) or 1.0
        weighted = {c: (e / total) * (1.0 if not farmer or c in farmer else self.prior_floor) for c, e in evidence.items()}
        norm = sum(weighted.values()) or 1.0
        posterior = {c: w / norm for c, w in weighted.items()}
        ranked = top_k(posterior, MAX_CANDIDATES + 1)
        if not ranked:
            return CropResult(crop_id=None, source="server_model", needs_confirmation=True, unknown=True)
        top, p1 = ranked[0]
        p2 = ranked[1][1] if len(ranked) > 1 else 0.0
        candidates = [CropCandidate(crop_id=c, confidence=floor4(p)) for c, p in ranked[:MAX_CANDIDATES]]
        if p1 < self.unknown_below:
            return CropResult(crop_id=None, candidates=candidates, source="server_model", needs_confirmation=True, unknown=True)
        ask = (bool(farmer) and top not in farmer) or (p1 - p2 < self.min_margin) or evidence[top] < self.min_evidence or top != raw_top
        return CropResult(crop_id=top, confidence=floor4(p1), candidates=candidates, source="server_model", needs_confirmation=ask)
