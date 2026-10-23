"""Read-only display names for crops and diseases (data/reference/disease_catalogue.csv + hindi_glossary.json).

Only names live here; every decision about diseases and products belongs to the rules engine.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.advice.crop_names import crop_hi
from app.domain.types import LocalizedText

logger = logging.getLogger(__name__)


@dataclass
class Catalogue:
    crops: dict[str, LocalizedText] = field(default_factory=dict)         # keyed by crop_id as in product_master ('Apple')
    diseases: dict[str, LocalizedText] = field(default_factory=dict)      # keyed by disease_id ('Apple___Apple_scab')

    def crop_name(self, crop_id: str) -> LocalizedText:
        if crop_id in self.crops:
            return self.crops[crop_id]
        plain = crop_id.replace("_", " ")                  # 'Custard_Apple': a crop a detector knows but the glossary does not
        return LocalizedText(en=plain, hi=crop_hi(crop_id) or plain)

    def disease_name(self, disease_id: str | None) -> LocalizedText | None:
        if disease_id is None:
            return None
        return self.diseases.get(disease_id) or LocalizedText(en=disease_id.replace("___", " ").replace("_", " "),
                                                              hi=disease_id.replace("___", " ").replace("_", " "))

    def canonical_crop(self, raw: str | None) -> str | None:
        """Match a crop name case-insensitively against the known crops; None when unknown."""
        if not raw:
            return None
        wanted = raw.strip().casefold()
        return next((crop for crop in self.crops if crop.casefold() == wanted), None)


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        logger.warning("catalogue file missing: %s", path.name)
        return []


def _read_glossary(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("glossary file missing or invalid: %s", path.name)
        return {}


@lru_cache(maxsize=4)
def load_catalogue(data_dir: str) -> Catalogue:
    reference = Path(data_dir) / "reference"
    catalogue = Catalogue()
    glossary = _read_glossary(reference / "hindi_glossary.json")
    for crop, hindi in (glossary.get("crops") or {}).items():
        catalogue.crops[crop] = LocalizedText(en=crop, hi=hindi or crop_hi(crop) or crop)
    for row in _read_csv(reference / "disease_catalogue.csv"):
        crop = row.get("crop") or ""
        if crop and crop not in catalogue.crops:
            catalogue.crops[crop] = LocalizedText(en=crop, hi=row.get("crop_hi") or crop_hi(crop) or crop)
        if row.get("disease_id"):
            catalogue.diseases[row["disease_id"]] = LocalizedText(en=row.get("name_en") or row["disease_id"],
                                                                  hi=row.get("name_hi") or row.get("name_en") or "")
    return catalogue
