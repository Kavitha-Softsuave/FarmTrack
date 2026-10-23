"""Turns the client's messy Advisory-table rows into SprayRecord objects (shared by the mock and the real Zoho adapter).

The row keys are the client's column API names (ASSUMED for the real API, see docs/design-notes/integrations.md):
Self_Spray_Dt, Self_Sprayed, Self_Spray_Frac_Group, Self_Spray_Trade_Name, Total_Rainfall_Since_Last_Spray, row_kind.
The mock CSV adds helper columns `_spray_datetime`, `_product_id` and `_nutrient`; the real API will not have them.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, time

from app.clock import IST
from app.domain.types import SprayRecord
from app.integrations.normalise import normalise_frac
from app.integrations.reference import ProductRef

# Nutrient and fertiliser entries (HP 2026 point 7: never mixed with a pesticide).
_NUTRIENT = re.compile(
    r"\b(zinc|boron|borax|urea|calcium|magnesium|potassium nitrate|potash|npk|micro-?nutrient)\b"
    r"|\b(?:12|13|19)\s*[.\-/ ]\s*(?:61|00|19|0)\s*[.\-/ ]\s*(?:00|45|19|0)\b",
    re.IGNORECASE,
)
_FORMULATION = r"(?:WP|SC|EC|FS|SL|WG|WDG|DF|EW|OD|SG|ZC|SE|CS|GR|DP|SP)"
# '30% EC', '6.89% SC', '27 % w/w SC', and bare '50 WP'
_STRENGTH = re.compile(rf"\b\d+(?:\.\d+)?\s*%\s*(?:w/[wv]\s*)?(?:{_FORMULATION}\b)?|\b\d+\s*{_FORMULATION}\b", re.IGNORECASE)
_DATE_ONLY_HOUR = time(12, 0)    # a date without a time is taken as midday IST


def is_nutrient_text(text: str | None) -> bool:
    return bool(text and _NUTRIENT.search(text))


def parse_active_ingredient(text: str | None) -> str | None:
    """'Pydiflumetofen 6.89% SC Difenoconazole 11.49% SC' -> 'Pydiflumetofen + Difenoconazole'; 'Fenpropathrin 30% EC' -> 'Fenpropathrin'."""
    if not text:
        return None
    cleaned = _STRENGTH.sub("|", text)
    names = []
    for chunk in re.split(r"[+|,&/]|\band\b", cleaned, flags=re.IGNORECASE):
        name = re.sub(r"\s+", " ", chunk).strip(" .-")
        if name:
            names.append(name[:1].upper() + name[1:].lower())
    return " + ".join(names) or None


def _parse_when(row: Mapping[str, str]) -> datetime | None:
    iso = (row.get("_spray_datetime") or "").strip()
    if iso:
        try:
            parsed = datetime.fromisoformat(iso)
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=IST)
    raw = (row.get("Self_Spray_Dt") or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.combine(datetime.strptime(raw, fmt).date(), _DATE_ONLY_HOUR, tzinfo=IST)
        except ValueError:
            continue
    return None


def _rain(row: Mapping[str, str]) -> float | None:
    raw = (row.get("Total_Rainfall_Since_Last_Spray") or "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def build_record(sprayed_at: datetime, text: str | None, frac_raw: str | None, trade_name: str | None,
                 product: ProductRef | None, rain_mm: float | None = None, nutrient_hint: bool = False,
                 source: str = "zoho") -> SprayRecord:
    """One SprayRecord. A product-master match is authoritative for ingredient, group and category; otherwise the typed text is parsed."""
    trade = (trade_name or "").strip() or None
    if product is not None:
        return SprayRecord(sprayed_at=sprayed_at, product_id=product.product_id, active_ingredient=product.active_ingredient,
                           frac_irac_code=product.frac_irac_code, category=product.category, trade_name=trade, nutrient=False,
                           rain_mm_since=rain_mm, source=source)  # type: ignore[arg-type]
    nutrient = nutrient_hint or is_nutrient_text(text) or is_nutrient_text(trade)
    frac = None if nutrient else normalise_frac(frac_raw)
    category = None
    if not nutrient and frac_raw and frac:
        category = "insecticide" if re.match(r"\s*IRAC\b", frac_raw, re.IGNORECASE) else "fungicide"
    active = ((text or "").strip() or None) if nutrient else parse_active_ingredient(text)
    return SprayRecord(sprayed_at=sprayed_at, active_ingredient=active, frac_irac_code=frac, category=category,
                       trade_name=trade, nutrient=nutrient, rain_mm_since=rain_mm, source=source)  # type: ignore[arg-type]


def record_from_row(row: Mapping[str, str], products: Mapping[str, ProductRef]) -> SprayRecord | None:
    """Advisor rows and rows without any usable date return None."""
    if (row.get("row_kind") or "self_spray") != "self_spray":
        return None
    when = _parse_when(row)
    if when is None:
        return None
    return build_record(
        when, row.get("Self_Sprayed"), row.get("Self_Spray_Frac_Group"), row.get("Self_Spray_Trade_Name"),
        products.get((row.get("_product_id") or "").strip()), _rain(row),
        nutrient_hint=(row.get("_nutrient") or "").strip().lower() == "true",
    )
