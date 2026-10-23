"""Map domain objects (rules, vision, advice) to API schema objects."""
from __future__ import annotations

from datetime import datetime

from app.advice.dose import dose_text
from app.api.schemas import (
    AdviceOut,
    CropCandidateOut,
    CropOut,
    DiseaseCandidateOut,
    DiseaseOut,
    FarmerOut,
    ProductOut,
    QualityOut,
    SpokenOut,
    TimingOut,
    WarningOut,
)
from app.db.models import as_ist
from app.domain.types import (
    CropResult,
    DiseaseResult,
    FarmerProfile,
    LocalizedText,
    ProductChoice,
    QualityResult,
    RuleOutput,
    TimingAdvice,
    ValidatedAdvice,
    WarningItem,
)
from app.security.phone import mask_phone
from app.services.catalogue import Catalogue


def ist(value: datetime) -> datetime:
    converted = as_ist(value)
    assert converted is not None  # noqa: S101
    return converted


def farmer_out(farmer: FarmerProfile) -> FarmerOut:
    return FarmerOut(id=farmer.id, name=farmer.name, phone_masked=mask_phone(farmer.phone), language=farmer.language,
                     district=farmer.district, village=farmer.village, crops=farmer.crops, primary_crop=farmer.primary_crop,
                     station_id=farmer.station_id)


def warning_out(item: WarningItem) -> WarningOut:
    return WarningOut(code=item.code, level=item.level, text=item.text)


def crop_out(result: CropResult, catalogue: Catalogue) -> CropOut:
    return CropOut(
        crop_id=result.crop_id, name=catalogue.crop_name(result.crop_id) if result.crop_id else None,
        confidence=result.confidence, needs_confirmation=result.needs_confirmation, unknown=result.unknown,
        candidates=[CropCandidateOut(crop_id=c.crop_id, name=catalogue.crop_name(c.crop_id), confidence=c.confidence)
                    for c in result.candidates],
        source=result.source)


def disease_out(result: DiseaseResult | None, rules: RuleOutput | None, catalogue: Catalogue) -> DiseaseOut | None:
    if result is None:
        return None
    disease_id = (rules.disease_id if rules and rules.disease_id else None) or result.disease_id
    return DiseaseOut(
        disease_id=disease_id, name=catalogue.disease_name(disease_id), confidence=result.confidence,
        route=rules.route if rules else "none",
        candidates=[DiseaseCandidateOut(disease_id=c.disease_id, name=catalogue.disease_name(c.disease_id) or LocalizedText(),
                                        confidence=c.confidence) for c in result.candidates])


def quality_out(results: list[QualityResult], tip_prompt_id: str | None) -> QualityOut:
    issues = list(dict.fromkeys(str(issue.value) for r in results for issue in r.issues))
    return QualityOut(usable=any(r.usable for r in results), issues=issues, tip_prompt_id=tip_prompt_id)


def product_out(product: ProductChoice) -> ProductOut:
    return ProductOut(
        product_id=product.product_id,
        active_ingredient=LocalizedText(en=product.active_ingredient, hi=product.active_ingredient_hi or product.active_ingredient),
        brand_examples=product.brand_examples, formulation=product.formulation, category=product.category,
        frac_irac_code=product.frac_irac_code, dose_text=dose_text(product), dose_min=product.dose_min,
        dose_max=product.dose_max, dose_unit=product.dose_unit, waiting_period_days=product.waiting_period_days,
        warnings=[warning_out(w) for w in product.warnings])


def timing_out(timing: TimingAdvice | None) -> TimingOut | None:
    if timing is None:
        return None
    return TimingOut(action=timing.action, text=timing.text, rain_next_12h_mm=timing.rain_next_12h_mm,
                     repeat_within_days=timing.repeat_within_days)


def advice_out(*, advice_id: str, scan_id: str, crop_id: str, rules: RuleOutput, composed: ValidatedAdvice,
               spoken: SpokenOut, sources: list[str], extra_warnings: list[WarningOut], created_at: datetime) -> AdviceOut:
    """Build the card. Products and timing are copied from the rule output ONLY when the rules said 'advice':
    every other status carries the general text and never a medicine, whatever the composer returned."""
    is_advice = rules.status == "advice"
    draft = composed.draft
    return AdviceOut(
        id=advice_id, scan_id=scan_id, crop_id=crop_id, disease_id=rules.disease_id, severity=rules.severity,
        headline=draft.headline, summary=draft.summary,
        products=[product_out(p) for p in rules.products] if is_advice else [],
        timing=timing_out(rules.timing) if is_advice else None,
        steps=draft.steps, safety=draft.safety,
        warnings=[warning_out(w) for w in rules.warnings] + extra_warnings,
        sources=sources, validated=composed.validated, spoken=spoken, created_at=ist(created_at))
