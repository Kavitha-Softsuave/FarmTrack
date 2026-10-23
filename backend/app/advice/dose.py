"""Human sentence for a product's dose (ProductOut.dose_text) and the figures the validator allows for it.

Handles every dose_unit in data/reference/product_master.csv. The text keeps digits (it is read on screen and checked by the
validator); the spoken version turns the same text into words (spoken.py).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal

from app.advice.numbers import format_number
from app.advice.quantities import MASS, PERCENT, VOLUME
from app.domain.types import LocalizedText, ProductChoice

logger = logging.getLogger(__name__)

_NUM = r"\d+(?:\.\d+)?"
_PER_WATER = re.compile(rf"^(g|ml|L|kg)/({_NUM})L$")
_PER_LITRE = re.compile(r"^(g|ml)/L$")
_PER_AREA = re.compile(rf"^(g|ml|kg)/(ha|acre)(?: in ({_NUM})(?:-({_NUM}))? ?L)?$")
_COMBO = re.compile(rf"^kg ([\w-]+) \+ ({_NUM}) kg ([\w-]+) per ha$")

_UNIT_EN = {"g": "g", "ml": "ml", "L": "litres", "kg": "kg"}
_UNIT_HI = {"g": "ग्राम", "ml": "मिलीलीटर", "L": "लीटर", "kg": "किलोग्राम"}
_AREA_EN = {"ha": "hectare", "acre": "acre"}
_AREA_HI = {"ha": "हेक्टेयर", "acre": "एकड़"}
_BASE_FACTOR = {"g": (MASS, 1), "kg": (MASS, 1000), "ml": (VOLUME, 1), "L": (VOLUME, 1000)}


@dataclass(frozen=True)
class DoseSpec:
    """A parsed dose_unit. kind: per_water | per_litre | per_area | percent | percent_drench | combo."""
    kind: str
    unit: str = ""                              # g | ml | L | kg
    water_l: tuple[str, ...] = ()               # litres of water named in the unit, as text
    area: str = ""                              # ha | acre
    lead: str = ""                              # combo rows: the ingredient that takes dose_min
    extra: tuple[tuple[str, str, str], ...] = ()  # combo rows: (amount text, unit, ingredient) of the further components


def parse_dose_unit(dose_unit: str | None) -> DoseSpec | None:
    """None for a unit this module does not know (the caller then falls back to a generic sentence)."""
    unit = (dose_unit or "").strip()
    if m := _PER_WATER.match(unit):
        return DoseSpec("per_water", m.group(1), (m.group(2),))
    if m := _PER_LITRE.match(unit):
        return DoseSpec("per_litre", m.group(1), ("1",))
    if m := _PER_AREA.match(unit):
        water = tuple(w for w in (m.group(3), m.group(4)) if w)
        return DoseSpec("per_area", m.group(1), water, area=m.group(2))
    if unit in ("percent", "percent_drench"):
        return DoseSpec(unit)
    if m := _COMBO.match(unit):
        return DoseSpec("combo", "kg", area="ha", lead=m.group(1), extra=((m.group(2), "kg", m.group(3)),))
    return None


def _amount(product: ProductChoice, to: str) -> str:
    values = [v for v in (product.dose_min, product.dose_max) if v is not None]
    if not values:
        return ""
    low, high = format_number(min(values)), format_number(max(values))
    return low if low == high else f"{low} {to} {high}"


def _water(water: tuple[str, ...], to: str, label: str) -> str:
    return f"{water[0]} {to} {water[1]} {label}" if len(water) == 2 else f"{water[0]} {label}"


def _split_names(product: ProductChoice) -> dict[str, str]:
    """Latin ingredient name (lowercase) -> Hindi name, for the components of a combination product."""
    latin = [p.strip() for p in product.active_ingredient.split("+")]
    hindi = [p.strip() for p in (product.active_ingredient_hi or "").split("+")]
    if len(latin) != len(hindi):
        return {}
    return {en.lower(): hi for en, hi in zip(latin, hindi, strict=True)}


def dose_text(product: ProductChoice) -> LocalizedText:
    amount_en, amount_hi = _amount(product, "to"), _amount(product, "से")
    if not amount_en:
        return LocalizedText(en="Ask your expert for the dose.", hi="मात्रा के लिए विशेषज्ञ से पूछें।")
    spec = parse_dose_unit(product.dose_unit)
    if spec is None:
        logger.warning("dose_text: unknown dose_unit %r for %s", product.dose_unit, product.product_id)
        unit = product.dose_unit or ""
        return LocalizedText(en=f"{amount_en} {unit}".strip(), hi=f"{amount_hi} {unit}".strip())
    u_en, u_hi = _UNIT_EN.get(spec.unit, ""), _UNIT_HI.get(spec.unit, "")
    if spec.kind == "per_water":
        return LocalizedText(en=f"{amount_en} {u_en} in {spec.water_l[0]} litres of water",
                             hi=f"{spec.water_l[0]} लीटर पानी में {amount_hi} {u_hi}")
    if spec.kind == "per_litre":
        return LocalizedText(en=f"{amount_en} {u_en} per litre of water", hi=f"1 लीटर पानी में {amount_hi} {u_hi}")
    if spec.kind == "per_area":
        en = f"{amount_en} {u_en} per {_AREA_EN[spec.area]}"
        hi = f"प्रति {_AREA_HI[spec.area]} {amount_hi} {u_hi}"
        if spec.water_l:
            en += f", in {_water(spec.water_l, 'to', 'litres')} of water"
            hi += f", {_water(spec.water_l, 'से', 'लीटर')} पानी में"
        return LocalizedText(en=en, hi=hi)
    if spec.kind == "percent":
        return LocalizedText(en=f"{amount_en} percent solution in water", hi=f"{amount_hi} प्रतिशत का घोल")
    if spec.kind == "percent_drench":
        return LocalizedText(en=f"{amount_en} percent solution, poured on the soil around the base of the tree",
                             hi=f"{amount_hi} प्रतिशत का घोल, पेड़ के तने के चारों ओर ज़मीन में डालें")
    # combo, e.g. 'kg dimethomorph + 2 kg mancozeb per ha': dose_min belongs to the lead ingredient
    names = _split_names(product)
    qty, _unit, second = spec.extra[0]
    lead_hi, second_hi = names.get(spec.lead.lower(), spec.lead), names.get(second.lower(), second)
    return LocalizedText(
        en=f"{amount_en} kg {spec.lead} and {qty} kg {second} per hectare",
        hi=f"प्रति हेक्टेयर {amount_hi} किलोग्राम {lead_hi} और {qty} किलोग्राम {second_hi}")


def dose_amounts(product: ProductChoice) -> set[tuple[str, Decimal]]:
    """Only the dose figures themselves (no water volume): what a text about this product must state."""
    spec = parse_dose_unit(product.dose_unit)
    if spec is None:
        return set()
    amounts = [Decimal(format_number(x)) for x in (product.dose_min, product.dose_max) if x is not None]
    if spec.kind in ("percent", "percent_drench"):
        return {(PERCENT, a) for a in amounts}
    family, factor = _BASE_FACTOR[spec.unit]
    return {(family, a * factor) for a in amounts}


def allowed_quantities(product: ProductChoice) -> set[tuple[str, Decimal]]:
    """(family, value) pairs a text about this product may contain: the dose, the water volume and any extra component."""
    spec = parse_dose_unit(product.dose_unit)
    allowed = dose_amounts(product)
    if spec is None:
        return allowed
    allowed.update((VOLUME, Decimal(w) * 1000) for w in spec.water_l)
    for qty, unit, _name in spec.extra:
        family, factor = _BASE_FACTOR[unit]
        allowed.add((family, Decimal(qty) * factor))
    return allowed
