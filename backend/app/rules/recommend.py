"""The recommendation pipeline: crop -> disease policy -> stage and season -> candidates -> exclusions -> ranking -> timing.

Rules decide; nothing here calls a network or a clock. `RuleInput.now` is the only notion of time. Every decision appends a
human-readable line to `trace` (kept for audit).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.domain.types import (
    LocalizedText,
    ProductChoice,
    RiskItem,
    RuleInput,
    RuleOutput,
    Severity,
    TimingAdvice,
    WarningItem,
)
from app.rules import checks
from app.rules import messages as msg
from app.rules import risks as risk_rules
from app.rules import stage as stage_rules
from app.rules.data import Band, Disease, ReferenceData, cfg
from app.rules.history import Spray, resolve_history
from app.rules.policy import auto_advice_diseases
from app.rules.selection import (
    Context,
    apply_exclusions,
    build_choice,
    candidate_rows,
    rank_products,
    rotation_limits,
)
from app.rules.timing import timing_advice
from app.rules.weather import as_ist

Status = Literal["advice", "expert_review", "no_approved_data", "not_a_disease", "needs_more_info"]
Route = Literal["auto_advice", "expert_queue", "none"]

SCAB_IDS = frozenset({"Apple___Apple_scab"})
LEAF_SPOT_IDS = frozenset({"Apple___Marssonina_blotch", "Apple___Alternaria_leaf_spot"})
_OIL = re.compile(r"\boil\b", re.IGNORECASE)
_OWN_NO_CURE = re.compile(r"^no cure", re.IGNORECASE)


def _measures(ref: ReferenceData, disease: Disease | None) -> list[LocalizedText]:
    """General non-chemical measures from the catalogue; a no-cure message when there is no chemical control."""
    items: list[LocalizedText] = []
    catalogue = ""
    if disease is not None:
        catalogue = disease.non_chemical
        if catalogue.lower().startswith("see ") and disease.treat_as in ref.diseases:
            catalogue = ref.diseases[disease.treat_as].non_chemical
        if _OIL.search(catalogue):
            catalogue = ""                          # a named oil spray is a medicine: never in the expert-route measures
        if disease.chemical_control == "no" and not _OWN_NO_CURE.match(catalogue):
            items.append(msg.text("NO_CURE"))
    if catalogue:
        items.append(msg.non_chemical(catalogue))
    elif not items:
        items.append(msg.text("HYGIENE"))
    return items


def _relevant_risk_level(disease_id: str | None, risks: list[RiskItem]) -> Severity:
    """Red when a risk that concerns this disease (or a wash-off of the last spray) is red, otherwise yellow."""
    wanted = {"rain_washoff"}
    if disease_id in SCAB_IDS or disease_id == "Apple___Apple_scab_rust":
        wanted.add("scab_infection_risk")
    if disease_id in LEAF_SPOT_IDS or disease_id == "Apple___Brown_spot":
        wanted.add("marssonina_alternaria_risk")
    if disease_id and "Late_blight" in disease_id:
        wanted.add("late_blight_risk")
    return Severity.red if any(r.level == Severity.red and r.id in wanted for r in risks) else Severity.yellow


@dataclass
class _Run:
    """Everything derived from the input before the disease is judged; builds the RuleOutput for every exit."""

    ref: ReferenceData
    disabled: frozenset[str]
    inp: RuleInput
    now: datetime
    crop: str
    band: Band | None
    stage: str | None
    stage_source: str | None
    days_to_harvest: int | None
    sprays: list[Spray]
    risks: list[RiskItem]
    history_warnings: list[WarningItem]
    auto_advice_setting: str | None = None
    trace: list[str] = field(default_factory=list)

    def output(self, status: Status, route: Route, reasons: list[str], disease: Disease | None, *,
               products: list[ProductChoice] | None = None, excluded: list | None = None, timing: TimingAdvice | None = None,
               extra_warnings: list[WarningItem] | None = None, measures: list[LocalizedText] | None = None) -> RuleOutput:
        products = products or []
        healthy = status == "not_a_disease"
        return RuleOutput(
            status=status, route=route,
            severity=Severity.green if healthy else _relevant_risk_level(self.inp.disease_id, self.risks),
            crop_id=self.crop, disease_id=self.inp.disease_id, treat_as=disease.treat_as if disease else None, stage=self.stage,
            stage_source=self.stage_source, products=products, excluded=excluded or [], timing=timing,
            warnings=(extra_warnings or []) + ([] if healthy else self.history_warnings), risks=self.risks,
            non_chemical=measures or [],
            notes_query={"crop": self.crop, "disease_id": self.inp.disease_id, "stage": self.stage,
                         "product_ids": [p.product_id for p in products]},
            reasons=reasons, trace=self.trace,
        )

    def expert(self, reasons: list[str], disease: Disease | None, status: Status = "expert_review",
               excluded: list | None = None) -> RuleOutput:
        self.trace.append(f"Routed to the expert queue: {', '.join(reasons)}.")
        return self.output(status, "expert_queue", reasons, disease, excluded=excluded, measures=_measures(self.ref, disease))


def _prepare(ref: ReferenceData, disabled: frozenset[str], inp: RuleInput, crop: str, now: datetime, trace: list[str],
             auto_advice_setting: str | None) -> _Run:
    farmer = inp.farmer
    band = stage_rules.band_for(ref, farmer) if crop == "Apple" else None
    stage: str | None = None
    stage_source: str | None = None
    days_to_harvest = inp.days_to_harvest
    if band is not None:
        cultivar = stage_rules.cultivar_for(band, farmer)
        doy = stage_rules.day_of_year(now)
        stage, stage_source = stage_rules.current_stage(band, doy, cultivar), "calendar"
        trace.append(f"Stage: band {band.band_id}, day {doy} of the year, cultivar {cultivar} -> {stage}.")
        if days_to_harvest is None:
            days_to_harvest = stage_rules.days_to_harvest(band, cultivar, now)
    elif crop == "Apple":
        trace.append("Apple farmer without a phenology band or elevation: the growth stage cannot be derived.")
    if days_to_harvest is not None:
        source = "given" if inp.days_to_harvest is not None else "calendar estimate"
        trace.append(f"Days to harvest: {days_to_harvest} ({source}).")

    sprays = resolve_history(ref, inp.history, now)
    trace.append(f"History: {len(sprays)} spray rows up to now ({sum(1 for s in sprays if s.nutrient)} nutrient rows).")
    if inp.weather is None:
        risks: list[RiskItem] = []
        trace.append("No weather snapshot: timing is 'unknown' and no weather risks were evaluated.")
    else:
        risks = risk_rules.evaluate(ref, farmer, risk_rules.farmer_crops(farmer) | {crop.lower()}, inp.weather, now, inp.history)
    history_warnings = checks.history_warnings(ref, farmer, crop, sprays, now, rotation_limits(ref, sprays, now, crop))
    return _Run(ref, disabled, inp, now, crop, band, stage, stage_source, days_to_harvest, sprays, risks, history_warnings,
                auto_advice_setting, trace)


def _policy_reasons(run: _Run, disease: Disease | None) -> list[str]:
    """Why this case must go to the expert queue (machine codes); an empty list means automatic advice is allowed."""
    inp, ref = run.inp, run.ref
    if inp.disease_id is None:
        run.trace.append("No disease was identified.")
        return ["disease_unknown"]
    if disease is None:
        run.trace.append(f"Disease '{inp.disease_id}' is not in the catalogue.")
        return ["disease_not_in_catalogue"]

    run.trace.append(
        f"Disease {disease.disease_id}: kind={disease.kind}, chemical_control={disease.chemical_control}, "
        f"treat_as={disease.treat_as}, requires_expert_review={disease.requires_expert_review}."
    )
    min_confidence = float(cfg(ref.config, "confidence_policy.min_confidence_for_auto_advice", 0.65))
    low_confidence = inp.disease_confidence < min_confidence
    reasons: list[str] = []
    if disease.crop and disease.crop.lower() != run.crop.lower():
        reasons.append("disease_crop_mismatch")
    if disease.kind == "healthy":
        return reasons or ["low_confidence"]                       # a confident healthy class never gets here
    if disease.requires_expert_review:
        reasons.append("requires_expert_review")
    if disease.chemical_control == "no":
        reasons.append("no_chemical_cure")
    elif disease.chemical_control == "expert_referral":
        reasons.append("expert_referral")
    if low_confidence:
        reasons.append("low_confidence")
    allowed = auto_advice_diseases(ref.diseases, run.auto_advice_setting)
    if disease.disease_id not in allowed:
        reasons.append("not_in_auto_advice_policy")
    run.trace.append(f"Policy: auto-advice diseases = {', '.join(sorted(allowed))}; confidence {inp.disease_confidence:.2f} "
                     f"vs minimum {min_confidence:.2f}.")
    return reasons


def _out_of_season(run: _Run, target_ids: frozenset[str]) -> bool:
    """Scab: primary season for the farmer's band (7 days slack). Marssonina/Alternaria: from 1 June."""
    if target_ids & SCAB_IDS and run.band is not None:
        start, end = stage_rules.scab_season_window(run.band)
        active = stage_rules.scab_season_active(run.ref, run.band, run.now)
        run.trace.append(f"Scab primary season for band {run.band.band_id}: day {start}-{end} of the year (7 days slack); "
                         f"today is day {stage_rules.day_of_year(run.now)} -> {'in season' if active else 'out of season'}.")
        if not active:
            return True
    if target_ids & LEAF_SPOT_IDS and not stage_rules.leaf_spot_season_active(run.ref, run.now):
        run.trace.append("Leaf spot (Marssonina/Alternaria) season starts on 1 June: out of season.")
        return True
    return False


def _harvest_warnings(run: _Run, products: list[ProductChoice]) -> list[WarningItem]:
    extra = [WarningItem(code="NO_TANK_MIX", level=Severity.green, text=msg.text("NO_TANK_MIX"))]
    stop_days = int(cfg(run.ref.config, "product_constraints.stop_sprays_before_harvest_days", 21))
    days = run.days_to_harvest
    if days is None and products:
        extra.append(WarningItem(code="HARVEST_DATE_UNKNOWN", level=Severity.yellow, text=msg.text("HARVEST_DATE_UNKNOWN")))
    elif days is not None and days <= stop_days:
        extra.append(WarningItem(code="NEAR_HARVEST", level=Severity.yellow, text=msg.text("NEAR_HARVEST", days=days),
                                 params={"days_to_harvest": days}))
    return extra


def recommend(ref: ReferenceData, disabled: frozenset[str], inp: RuleInput, auto_advice_setting: str | None = None,
              season_check: bool = True) -> RuleOutput:
    now = as_ist(inp.now)
    trace: list[str] = [
        f"Input: crop={inp.crop_id}, disease={inp.disease_id}, confidence={inp.disease_confidence:.2f}, "
        f"now={now.isoformat(timespec='minutes')}, farmer band={inp.farmer.phenology_band}."
    ]

    # 1. approved data for the crop: without it there is never a medicine
    crop = ref.canonical_crop(inp.crop_id)
    approved = [p for p in ref.usable_products(crop) if p.product_id not in disabled] if crop else []
    if crop is None or not approved:
        trace.append(f"No approved product rows for crop '{inp.crop_id}': no medicine advice is possible.")
        disease = ref.diseases.get(inp.disease_id or "")
        return RuleOutput(
            status="no_approved_data", route="none", severity=Severity.yellow, crop_id=inp.crop_id, disease_id=inp.disease_id,
            non_chemical=_measures(ref, disease) if disease else [], reasons=["no_approved_data_for_crop"], trace=trace,
            notes_query={"crop": inp.crop_id, "disease_id": inp.disease_id, "stage": None, "product_ids": []},
        )
    trace.append(f"Crop {crop}: {len(approved)} approved product rows.")
    run = _prepare(ref, disabled, inp, crop, now, trace, auto_advice_setting)

    # 2. disease handling and the auto-advice policy
    disease = ref.diseases.get(inp.disease_id) if inp.disease_id else None
    min_confidence = float(cfg(ref.config, "confidence_policy.min_confidence_for_auto_advice", 0.65))
    if (disease is not None and disease.kind == "healthy" and disease.crop.lower() == crop.lower()
            and inp.disease_confidence >= min_confidence):
        trace.append("Healthy class with enough confidence: nothing to treat.")
        return run.output("not_a_disease", "none", ["healthy_class"], disease)
    reasons = _policy_reasons(run, disease)
    if reasons:
        return run.expert(reasons, disease)
    assert disease is not None

    # 3. apple needs the growth stage; diseases with a season must be in season
    if crop == "Apple" and run.band is None:
        trace.append("Cannot advise on apple without the growth stage: needs the farmer's elevation band.")
        return run.expert(["phenology_band_unknown"], disease, status="needs_more_info")
    target_ids = frozenset({disease.disease_id} | ({disease.treat_as} if disease.treat_as else set()))
    if not season_check:
        trace.append("Season check is off (development): the date does not exclude any disease.")
    elif _out_of_season(run, target_ids):
        return run.expert(["out_of_season_for_disease"], disease)

    # 4. candidates, exclusions, ranking
    ctx = Context(
        ref=ref, now=now, crop=crop, disease_id=disease.disease_id, target_ids=target_ids, stage=run.stage,
        days_to_harvest=run.days_to_harvest, weather=inp.weather, sprays=run.sprays, disabled=disabled, lang=inp.language,
        trace=trace, season_check=season_check,
    )
    rows = candidate_rows(ctx)
    if not rows:
        return run.expert(["no_product_for_disease_and_stage"], disease)
    eligibility = apply_exclusions(ctx, rows)
    infection_active = bool(target_ids & SCAB_IDS) and any(
        r.id == "scab_infection_risk" and r.level == Severity.red for r in run.risks)
    ranked = rank_products(ctx, eligibility, infection_active)
    if not ranked:
        trace.append("Every candidate was excluded: no medicine can be advised.")
        return run.expert(["no_product_after_exclusions"], disease, excluded=eligibility.excluded)

    # 5. timing and warnings
    products = [build_choice(ctx, item) for item in ranked]
    trace.append("Recommended: " + "; ".join(f"{p.product_id} {p.active_ingredient}" for p in products) + ".")
    timing = timing_advice(ref, inp.weather, run.sprays, crop, now, [item.product for item in ranked])
    trace.append(f"Timing: {timing.action} ({', '.join(timing.reasons)}).")
    return run.output("advice", "auto_advice", ["auto_advice_policy"], disease, products=products, excluded=eligibility.excluded,
                      timing=timing, extra_warnings=_harvest_warnings(run, products), measures=_measures(ref, disease))
