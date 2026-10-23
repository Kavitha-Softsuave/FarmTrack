"""DEMO_DISEASE_HINTS: steer the STUB disease classifier for offline demos (never used in production).

Format (a setting or environment variable, one string):

    DEMO_DISEASE_HINTS="Apple=Apple___Apple_scab:0.9;Tomato=Tomato___Late_blight"

- entries are separated by `;`, each entry is `Crop=disease_id` or `Crop=disease_id:confidence`
- `Crop` is a crop name (case and aliases as everywhere: apple, Apple, Corn -> Maize); one entry per crop, the last one wins
- `disease_id` must be a disease id of data/reference/disease_catalogue.csv (when that file can be read); ids may contain
  letters, digits, space and _ - ( ) , . but never ; : =
- `confidence` is a number from 0 to 1; without it the stub's default (0.8) is used
- a malformed entry is ignored and a warning is logged; the remaining entries still apply

With a hint, every scan of that crop gets that disease from the stub, so a demo can show the "scab -> advice" or the
"leaf spot -> expert queue" path without a model. It only steers the stub: with disease_provider=model the real models answer.
The rules, the approved list and the expert queue still decide what the farmer is told.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Collection

from app.vision.disease import STUB_HINT_CONFIDENCE
from app.vision.labels import canonical_crop

log = logging.getLogger("app.vision")

_CROP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$")
_DISEASE_RE = re.compile(r"^[A-Za-z0-9_(),. -]{1,80}$")          # catalogue ids hold ( ) , and spaces; never ; : =


def parse_demo_disease_hints(raw: str | None, known_diseases: Collection[str] | None = None) -> dict[str, tuple[str, float]]:
    """crop -> (disease_id, confidence) from the DEMO_DISEASE_HINTS format. Malformed entries are skipped with a log warning."""
    hints: dict[str, tuple[str, float]] = {}
    for entry in (raw or "").split(";"):
        entry = entry.strip()
        if not entry:
            continue
        parsed = _parse_entry(entry, known_diseases)
        if parsed is None:
            continue
        crop, hint = parsed
        if crop in hints:
            log.warning("DEMO_DISEASE_HINTS: crop %s is listed twice, the last entry wins", crop)
        hints[crop] = hint
    return hints


def _parse_entry(entry: str, known_diseases: Collection[str] | None) -> tuple[str, tuple[str, float]] | None:
    crop_text, equals, rest = entry.partition("=")
    crop_text, rest = crop_text.strip(), rest.strip()
    disease, colon, confidence_text = rest.partition(":")
    disease, confidence_text = disease.strip(), confidence_text.strip()
    if not equals or not _CROP_RE.match(crop_text) or not _DISEASE_RE.match(disease):
        log.warning("DEMO_DISEASE_HINTS: ignoring entry %r (expected Crop=disease_id or Crop=disease_id:confidence)", entry)
        return None
    if known_diseases is not None and disease not in known_diseases:
        log.warning("DEMO_DISEASE_HINTS: ignoring entry %r (%s is not in the disease catalogue)", entry, disease)
        return None
    confidence = STUB_HINT_CONFIDENCE
    if colon:
        try:
            confidence = float(confidence_text)
        except ValueError:
            confidence = -1.0
        if not 0.0 <= confidence <= 1.0:                      # also catches nan: every comparison with it is False
            log.warning("DEMO_DISEASE_HINTS: ignoring entry %r (the confidence must be a number from 0 to 1)", entry)
            return None
    return canonical_crop(crop_text), (disease, confidence)
