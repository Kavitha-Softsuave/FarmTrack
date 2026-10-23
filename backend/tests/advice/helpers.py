"""Builders shared by the advice tests: products straight from the product master and rule outputs around them."""
from __future__ import annotations

import csv
from datetime import datetime
from functools import cache

from app.advice.refdata import RefData, load_refdata
from app.config import REPO_ROOT
from app.domain.types import (
    FarmerProfile,
    LocalizedText,
    ProductChoice,
    RiskItem,
    RuleInput,
    RuleOutput,
    Severity,
    TimingAdvice,
    WarningItem,
)

DATA_DIR = REPO_ROOT / "data"


@cache
def master_rows() -> dict[str, dict[str, str]]:
    with open(DATA_DIR / "reference" / "product_master.csv", newline="", encoding="utf-8-sig") as handle:
        return {r["product_id"]: r for r in csv.DictReader(handle)}


@cache
def ref() -> RefData:
    return load_refdata(str(DATA_DIR))


def product(pid: str, **overrides) -> ProductChoice:
    row = master_rows()[pid]
    wait = row["waiting_period_days"]
    data = {
        "product_id": pid, "crop": row["crop"], "active_ingredient": row["active_ingredient"],
        "active_ingredient_hi": row["active_ingredient_hi"], "formulation": row["formulation"],
        "brand_examples": [row["brand_example"]], "category": row["category"], "frac_irac_code": row["frac_irac_code"],
        "dose_min": float(row["dose_min"]), "dose_max": float(row["dose_max"]), "dose_unit": row["dose_unit"],
        "waiting_period_days": int(wait) if wait else None, "ban_status": row["ban_status"], "stage": row["stage"],
    }
    data.update(overrides)
    return ProductChoice(**data)


def loc(en: str, hi: str) -> LocalizedText:
    return LocalizedText(en=en, hi=hi)


def timing(action: str = "spray_now", **kw) -> TimingAdvice:
    text = kw.pop("text", loc("No rain is expected in the next 12 hours.", "अगले 12 घंटे बारिश की उम्मीद नहीं है।"))
    return TimingAdvice(action=action, text=text, **kw)


def advice_output(pids=("P001", "P002"), action: str = "spray_now", **kw) -> RuleOutput:
    """An apple scab advice output with the given master products."""
    data = {
        "status": "advice", "route": "auto_advice", "severity": Severity.yellow, "crop_id": "Apple",
        "disease_id": "Apple___Apple_scab", "stage": "green_tip", "products": [product(p) for p in pids],
        "timing": timing(action, **({"repeat_within_days": 7} if action == "repeat_within_days" else {})),
        "non_chemical": [loc("Compost fallen leaves or spray 5% urea on the orchard floor.",
                             "गिरी पत्तियों की खाद बनाएँ या बाग की ज़मीन पर 5% यूरिया छिड़कें।")],
    }
    data.update(kw)
    return RuleOutput(**data)


def plain_output(status: str, crop: str = "Apple", **kw) -> RuleOutput:
    route = "expert_queue" if status == "expert_review" else "none"
    return RuleOutput(status=status, route=route, crop_id=crop, **kw)


def warning(code: str = "PROPOSED_BAN", level: Severity = Severity.yellow) -> WarningItem:
    return WarningItem(code=code, level=level, text=loc("This medicine is proposed to be banned, but it is still registered.",
                                                          "इस दवा पर रोक का प्रस्ताव है, पर यह अभी पंजीकृत है।"))


def risk() -> RiskItem:
    return RiskItem(id="scab_infection_risk", level=Severity.red, title=loc("Scab risk", "स्कैब का खतरा"),
                    text=loc("Leaves stayed wet for 14 hours, so scab infection is likely.", "पत्तियाँ 14 घंटे गीली रहीं, इसलिए स्कैब का संक्रमण संभव है।"))


def rule_input(out: RuleOutput) -> RuleInput:
    farmer = FarmerProfile(id="F001", name="Test Farmer", phone="+910000000001", village="Kotgarh")
    return RuleInput(farmer=farmer, crop_id=out.crop_id, disease_id=out.disease_id, now=datetime(2026, 5, 12, 8, 0))
