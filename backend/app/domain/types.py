"""Shared domain types. These are the contracts BETWEEN backend modules (vision, rules, advice, integrations, api).

Rules for all modules:
- crop_id is the catalogue crop name as used in data/reference/product_master.csv ('Apple', 'Tomato', 'Potato', 'Maize', 'Grape', ...).
- disease_id is the catalogue id from data/reference/disease_catalogue.csv ('Apple___Apple_scab', 'PEST_apple_mites', ...).
- Datetimes are timezone-aware (Asia/Kolkata unless stated). Weather CSVs are naive IST: attach IST when loading.
- Languages are 'hi' and 'en' only.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["hi", "en"]
LANGS: tuple[str, ...] = ("hi", "en")


class Severity(StrEnum):
    green = "green"
    yellow = "yellow"
    red = "red"


class LocalizedText(BaseModel):
    en: str = ""
    hi: str = ""

    def get(self, lang: str) -> str:
        return self.hi if lang == "hi" else self.en


# ------------------------------------------------------------------------------------------ farmer
class FarmerProfile(BaseModel):
    id: str
    name: str
    phone: str
    language: Lang = "hi"
    district: str | None = None
    village: str | None = None
    station_id: str | None = None            # nearest sensor/weather station (ST01..ST12 in demo data)
    elevation_m: float | None = None
    phenology_band: str | None = None        # B1..B4 (see data/reference/stage_calendar.csv)
    crops: list[str] = Field(default_factory=list)   # crops the farmer grows (strong prior for crop identification)
    primary_crop: str | None = None
    primary_variety: str | None = None       # e.g. 'Royal_Delicious' (drives harvest date estimate)
    zoho_contact_id: str | None = None
    lat: float | None = None
    lon: float | None = None


# ------------------------------------------------------------------------------------------ vision
class QualityIssue(StrEnum):
    blurry = "blurry"
    too_dark = "too_dark"
    too_bright = "too_bright"
    too_small = "too_small"
    no_leaf = "no_leaf"          # no plant-like (green/brown vegetation) content found
    unreadable = "unreadable"


class QualityResult(BaseModel):
    usable: bool
    issues: list[QualityIssue] = Field(default_factory=list)
    blur_score: float | None = None
    brightness: float | None = None
    width: int | None = None
    height: int | None = None
    tip_prompt_id: str | None = None         # voice prompt to play, e.g. 'scan_retake_blurry'


class CropCandidate(BaseModel):
    crop_id: str
    confidence: float


class CropResult(BaseModel):
    crop_id: str | None                      # None = could not tell
    confidence: float = 0.0
    candidates: list[CropCandidate] = Field(default_factory=list)
    source: str = "stub"                     # on_device | server_model | farmer_profile | stub | farmer_confirmed
    needs_confirmation: bool = False         # app must ask the farmer (one tap) before medicine advice
    unknown: bool = False


class DiseaseCandidate(BaseModel):
    disease_id: str
    confidence: float


class DiseaseResult(BaseModel):
    crop_id: str
    disease_id: str | None                   # None = no model for this crop or could not tell
    confidence: float = 0.0
    candidates: list[DiseaseCandidate] = Field(default_factory=list)
    model: str = "stub"
    model_covers_crop: bool = True           # False -> no photo model for this crop (expert / knowledge only)


# ------------------------------------------------------------------------------------------ history and weather
class SprayRecord(BaseModel):
    sprayed_at: datetime
    product_id: str | None = None            # product-master id when known
    active_ingredient: str | None = None
    frac_irac_code: str | None = None        # '1', '3', 'M03', '1 + M03', '7+3' (normalise: strip spaces, M3 -> M03)
    category: str | None = None              # fungicide | insecticide | acaricide | oil | bactericide
    trade_name: str | None = None
    nutrient: bool = False                   # Zinc/Boron/12-61-00 style rows
    rain_mm_since: float | None = None
    source: Literal["zoho", "app"] = "zoho"


class WeatherHour(BaseModel):
    time: datetime
    temp_c: float
    rh_pct: float
    rain_mm: float
    leaf_wet: bool = False                   # derived: rain>=0.1 mm or RH>=90 (proxy; see rules_config.leaf_wetness_proxy)


class ForecastDay(BaseModel):
    day: date
    tmin_c: float
    tmax_c: float
    rain_mm: float


class WeatherSnapshot(BaseModel):
    station_id: str | None
    as_of: datetime
    temp_c: float | None = None
    rh_pct: float | None = None
    rain_last_24h_mm: float = 0.0
    rain_next_12h_mm: float = 0.0
    rain_next_48h_mm: float = 0.0
    hourly_past: list[WeatherHour] = Field(default_factory=list)      # up to the last ~14 days, hourly, oldest first
    hourly_future: list[WeatherHour] = Field(default_factory=list)    # next ~48 h
    daily_forecast: list[ForecastDay] = Field(default_factory=list)   # next 7 days
    stale: bool = False
    source: str = "csv"


class SensorReading(BaseModel):
    station_id: str
    time: datetime
    temp_c: float | None = None
    rh_pct: float | None = None
    rain_mm: float | None = None
    leaf_wetness_min: int | None = None
    soil_moisture_pct: float | None = None
    battery_v: float | None = None


# ------------------------------------------------------------------------------------------ rules
class WarningItem(BaseModel):
    code: str                                 # e.g. PROPOSED_BAN, OFF_LABEL_HISTORY, ROTATION_LIMIT, STALE_HISTORY, NO_WAITING_PERIOD
    level: Severity = Severity.yellow
    text: LocalizedText = Field(default_factory=LocalizedText)
    params: dict = Field(default_factory=dict)


class ProductChoice(BaseModel):
    product_id: str
    crop: str
    active_ingredient: str
    active_ingredient_hi: str | None = None
    formulation: str | None = None
    brand_examples: list[str] = Field(default_factory=list)   # HP-evaluated brands first (data/reference/brand_master.csv)
    category: str
    frac_irac_code: str | None = None
    behaviour: str | None = None             # contact | systemic | mixed | not_applicable
    stage: str | None = None
    dose_min: float | None = None
    dose_max: float | None = None
    dose_unit: str | None = None             # e.g. 'g/200L', 'ml/ha'
    waiting_period_days: int | None = None
    ban_status: str = "registered"
    use_note: str | None = None
    rank_reason: str = ""
    warnings: list[WarningItem] = Field(default_factory=list)
    source_ref: str | None = None


class ExcludedProduct(BaseModel):
    product_id: str
    active_ingredient: str
    reasons: list[str]                        # machine codes, e.g. 'same_frac_as_last_spray', 'dmi_season_limit', 'waiting_period_exceeds_harvest'


class TimingAdvice(BaseModel):
    action: Literal["spray_now", "wait", "repeat_within_days", "not_needed", "unknown"] = "unknown"
    reasons: list[str] = Field(default_factory=list)
    rain_next_12h_mm: float | None = None
    repeat_within_days: int | None = None
    text: LocalizedText = Field(default_factory=LocalizedText)


class RiskItem(BaseModel):
    id: str                                   # scab_infection_risk | marssonina_alternaria_risk | late_blight_risk | rain_washoff ...
    level: Severity
    title: LocalizedText
    text: LocalizedText
    detail: dict = Field(default_factory=dict)


class RuleInput(BaseModel):
    farmer: FarmerProfile
    crop_id: str
    disease_id: str | None
    disease_confidence: float = 0.0
    now: datetime
    history: list[SprayRecord] = Field(default_factory=list)
    weather: WeatherSnapshot | None = None
    weather_enabled: bool = True              # False (WEATHER_ENABLED=false): no weather risks, no weather timing, no weather wording
    days_to_harvest: int | None = None        # None = estimate from stage calendar + variety
    language: Lang = "hi"


class RuleOutput(BaseModel):
    status: Literal["advice", "expert_review", "no_approved_data", "not_a_disease", "needs_more_info"]
    route: Literal["auto_advice", "expert_queue", "none"]
    severity: Severity = Severity.green
    crop_id: str
    disease_id: str | None = None
    treat_as: str | None = None               # alias target from the catalogue (Brown_spot -> Marssonina ...)
    stage: str | None = None
    stage_source: str | None = None           # 'calendar' | 'override'
    products: list[ProductChoice] = Field(default_factory=list)
    excluded: list[ExcludedProduct] = Field(default_factory=list)
    timing: TimingAdvice | None = None
    warnings: list[WarningItem] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    non_chemical: list[LocalizedText] = Field(default_factory=list)
    notes_query: dict = Field(default_factory=dict)       # {'crop','disease_id','stage','product_ids'} for RAG retrieval
    reasons: list[str] = Field(default_factory=list)      # why status/route (machine codes)
    trace: list[str] = Field(default_factory=list)        # human-readable decision trace (kept in the audit log)


# ------------------------------------------------------------------------------------------ advice (composer output)
class Note(BaseModel):
    note_id: str
    topic: str
    crop: str | None = None
    disease_id: str | None = None
    stage: str | None = None
    text_en: str
    text_hi: str = ""
    source_ref: str = ""
    confidence: str = ""
    score: float = 0.0


class SpokenText(BaseModel):
    en: str = ""
    hi: str = ""


class AdviceDraft(BaseModel):
    """What the LLM (or the template fallback) returns. Validated against RuleOutput before use."""
    headline: LocalizedText
    summary: LocalizedText
    steps: list[LocalizedText] = Field(default_factory=list)
    safety: list[LocalizedText] = Field(default_factory=list)
    spoken: SpokenText = Field(default_factory=SpokenText)
    product_ids_mentioned: list[str] = Field(default_factory=list)
    doses_mentioned: list[str] = Field(default_factory=list)


class AskCitation(BaseModel):
    note_id: str
    source: str = ""


class AskResult(BaseModel):
    answer: str
    language: Lang
    refused: bool = False
    citations: list[AskCitation] = Field(default_factory=list)


class ValidatedAdvice(BaseModel):
    draft: AdviceDraft
    validated: bool                           # False -> the safe template was used instead of the LLM text
    problems: list[str] = Field(default_factory=list)
    used_llm: bool = False
