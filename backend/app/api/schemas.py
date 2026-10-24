"""API schemas (v1). THESE ARE THE CONTRACT between the backend and the mobile app.
Run `python -m app.export_openapi ../contracts/openapi.json` after any change; the mobile app reads that file.

Conventions:
- All texts the farmer reads or hears are LocalizedText {en, hi}. The app shows/speaks the farmer's language and may switch instantly.
- `spoken` blocks carry the text to speak and (when TTS is configured) audio URLs per language. `audio.<lang>` may be null: then the app
  speaks `text.<lang>` with the phone's built-in voice, or plays a bundled prompt.
- Ids are opaque strings. Datetimes are ISO-8601 with offset. Money-free, PII-minimal.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.types import Lang, LocalizedText, Severity


class ErrorOut(BaseModel):
    code: str = Field(examples=["invalid_otp"])
    message: str
    details: dict | None = None


# ---------------------------------------------------------------------------------------------- common
class AudioRef(BaseModel):
    url: str                                  # relative, e.g. /audio/ab12...mp3 (content-addressed, no auth needed)
    sha256: str | None = None
    duration_s: float | None = None


class SpokenOut(BaseModel):
    text: LocalizedText
    audio: dict[Lang, AudioRef | None] = Field(default_factory=dict)


class WarningOut(BaseModel):
    code: str
    level: Severity
    text: LocalizedText


# ---------------------------------------------------------------------------------------------- auth / me
class LoginIn(BaseModel):
    """Username + password login (the MVP login). The username is case-insensitive; the answer for an unknown user and for a wrong
    password is the same 401 `invalid_credentials`."""
    username: str = Field(max_length=100, examples=["f001"])
    password: str = Field(max_length=200)
    device_id: str | None = None


class OtpRequestIn(BaseModel):
    phone: str = Field(pattern=r"^\+?[0-9]{10,13}$", examples=["+919000000001"])


class OtpRequestOut(BaseModel):
    request_id: str
    expires_in: int
    dev_otp: str | None = None                # ONLY returned when env != prod


class OtpVerifyIn(BaseModel):
    request_id: str
    otp: str = Field(pattern=r"^[0-9]{4,8}$")
    device_id: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class FarmerOut(BaseModel):
    id: str
    name: str
    phone_masked: str
    language: Lang
    district: str | None = None
    village: str | None = None
    crops: list[str] = Field(default_factory=list)
    primary_crop: str | None = None
    station_id: str | None = None


class FarmerPatch(BaseModel):
    language: Lang | None = None
    name: str | None = Field(default=None, max_length=80)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    farmer: FarmerOut


# ---------------------------------------------------------------------------------------------- scans
class CropCandidateOut(BaseModel):
    crop_id: str
    name: LocalizedText
    confidence: float


class CropOut(BaseModel):
    crop_id: str | None
    name: LocalizedText | None = None
    confidence: float = 0.0
    needs_confirmation: bool = False          # app asks "Is this apple?" (tick / cross) before showing medicine
    unknown: bool = False
    candidates: list[CropCandidateOut] = Field(default_factory=list)
    source: str = "stub"


class QualityOut(BaseModel):
    usable: bool
    issues: list[str] = Field(default_factory=list)    # blurry | too_dark | too_bright | too_small | no_leaf | unreadable
    tip_prompt_id: str | None = None


class DiseaseCandidateOut(BaseModel):
    disease_id: str
    name: LocalizedText
    confidence: float


class DiseaseOut(BaseModel):
    disease_id: str | None
    name: LocalizedText | None = None
    confidence: float = 0.0
    route: Literal["auto_advice", "expert_queue", "none"] = "none"
    candidates: list[DiseaseCandidateOut] = Field(default_factory=list)


class ProductOut(BaseModel):
    product_id: str
    active_ingredient: LocalizedText
    brand_examples: list[str] = Field(default_factory=list)
    formulation: str | None = None
    category: str
    frac_irac_code: str | None = None
    dose_text: LocalizedText                  # human sentence, e.g. "600 g in 200 litres of water"
    dose_min: float | None = None
    dose_max: float | None = None
    dose_unit: str | None = None
    waiting_period_days: int | None = None
    warnings: list[WarningOut] = Field(default_factory=list)


class TimingOut(BaseModel):
    action: Literal["spray_now", "wait", "repeat_within_days", "not_needed", "unknown"]
    text: LocalizedText
    rain_next_12h_mm: float | None = None
    repeat_within_days: int | None = None


class AdviceOut(BaseModel):
    id: str
    scan_id: str
    crop_id: str
    disease_id: str | None
    severity: Severity
    headline: LocalizedText
    summary: LocalizedText
    products: list[ProductOut] = Field(default_factory=list)
    timing: TimingOut | None = None
    steps: list[LocalizedText] = Field(default_factory=list)
    safety: list[LocalizedText] = Field(default_factory=list)
    warnings: list[WarningOut] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    validated: bool = True                    # False -> the safe template was used (LLM text failed validation)
    spoken: SpokenOut
    created_at: datetime


class NextStep(BaseModel):
    action: Literal["confirm_crop", "add_photo", "retake", "mark_sprayed", "ask_expert", "done"]
    prompt_id: str                            # voice prompt to speak for this step (see voice/prompts.json)


class ScanOut(BaseModel):
    id: str
    status: Literal["ok", "confirm_crop", "needs_expert", "no_approved_data", "photo_unusable", "not_a_disease"]
    created_at: datetime                       # when the server evaluated the scan (the demo clock in demos)
    taken_at: datetime | None = None           # when the phone took the photo (offline uploads: earlier than created_at); null = not sent
    offline: bool = False                      # the app sent this scan from its offline queue
    photos: int
    crop: CropOut | None = None
    quality: QualityOut
    disease: DiseaseOut | None = None
    advice: AdviceOut | None = None
    review_task_id: str | None = None
    next_steps: list[NextStep] = Field(default_factory=list)
    spoken: SpokenOut                          # what to say on the result screen right now


class ScanListOut(BaseModel):
    items: list[ScanOut]
    next_cursor: str | None = None


class CropConfirmIn(BaseModel):
    crop_id: str


# ---------------------------------------------------------------------------------------------- spray diary
class SprayLogIn(BaseModel):
    crop_id: str
    advice_id: str | None = Field(default=None, description="The farmer's own advice; with nothing else the advice's first product is logged")
    product_id: str | None = Field(default=None, description="A product of that advice or of the approved catalogue (422 unknown_product otherwise)")
    free_text: str | None = Field(default=None, max_length=200,
                                  description="Typed medicine name; matched exactly against brands, active ingredients (English or Hindi) and ids")
    sprayed_at: datetime | None = None         # default: server now (demo clock)
    notes: str | None = Field(default=None, max_length=300)


class SprayLogOut(BaseModel):
    id: str
    crop_id: str
    product_id: str | None
    product_name: str | None
    sprayed_at: datetime
    advice_id: str | None = None
    warnings: list[WarningOut] = Field(default_factory=list)   # e.g. nutrient mixed same day, same chemical repeated; PRODUCT_NOT_RECOGNISED (yellow) when a typed name could not be matched
    synced_to_zoho: bool = False
    spoken: SpokenOut | None = None


# ---------------------------------------------------------------------------------------------- field / alerts
class ReadingsOut(BaseModel):
    temp_c: float | None = None
    rh_pct: float | None = None
    rain_24h_mm: float | None = None
    leaf_wetness_min: int | None = None
    soil_moisture_pct: float | None = None


class ForecastDayOut(BaseModel):
    day: date
    tmin_c: float
    tmax_c: float
    rain_mm: float


class RiskOut(BaseModel):
    id: str
    level: Severity
    title: LocalizedText
    text: LocalizedText


class FieldOut(BaseModel):
    station_id: str | None
    village: str | None
    as_of: datetime
    stale: bool = False
    readings: ReadingsOut | None = None
    forecast: list[ForecastDayOut] = Field(default_factory=list)
    risks: list[RiskOut] = Field(default_factory=list)
    spoken: SpokenOut


class AlertOut(BaseModel):
    id: str
    kind: str                                  # scab_infection_risk | marssonina_alternaria_risk | late_blight_risk | rain_washoff | waiting_period | rotation_limit
    level: Severity
    title: LocalizedText
    body: LocalizedText
    spoken: SpokenOut
    created_at: datetime
    read_at: datetime | None = None
    scan_id: str | None = None                 # set when the alert is about a scan (open GET /v1/scans/{scan_id}); null otherwise


class AlertListOut(BaseModel):
    items: list[AlertOut]
    unread: int = 0


class DeviceIn(BaseModel):
    platform: Literal["android", "ios"]
    push_token: str = Field(max_length=4096)
    app_version: str | None = None


# ---------------------------------------------------------------------------------------------- ask / expert / voice / meta
class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    language: Lang = "hi"
    crop_id: str | None = None


class CitationOut(BaseModel):
    note_id: str
    source: str


class AskOut(BaseModel):
    answer: str
    language: Lang
    refused: bool = False                       # True when no approved note supports an answer
    citations: list[CitationOut] = Field(default_factory=list)
    spoken: SpokenOut | None = None


class ExpertRequestIn(BaseModel):
    scan_id: str | None = None
    message: str | None = Field(default=None, max_length=500)
    crop_id: str | None = Field(default=None, max_length=40, description="Crop the question is about (optional; shown to the staff)")


class ExpertRequestOut(BaseModel):
    id: str
    status: Literal["open", "resolved"]


class PromptOut(BaseModel):
    id: str
    text: str
    audio: AudioRef | None = None               # generated audio bundled/served; null -> use on-device TTS


class VoiceCatalogueOut(BaseModel):
    version: str                                # changes when any prompt text or audio changes (app re-syncs)
    language: Lang
    prompts: list[PromptOut]


class MetaOut(BaseModel):
    app_version: str
    env: str
    demo_clock: datetime | None
    supported_languages: list[Lang]
    supported_crops: list[str]                  # crops with approved-list data
    providers: dict[str, str]
    weather_enabled: bool = True                # False: the app hides every weather screen and card (WEATHER_ENABLED)


class HealthOut(BaseModel):
    status: Literal["ok"]
    db: bool


# ---------------------------------------------------------------------------------------------- admin (X-Admin-Key)
class ReviewTaskOut(BaseModel):
    id: str
    scan_id: str
    status: Literal["open", "resolved"]
    created_at: datetime
    farmer_id: str
    farmer_name: str | None = None
    crop_guess: str | None = None
    disease_candidates: list[DiseaseCandidateOut] = Field(default_factory=list)
    reason: str = ""
    photo_urls: list[str] = Field(default_factory=list)
    resolution_note: str | None = None


class ReviewResolveIn(BaseModel):
    confirmed_crop: str | None = None
    confirmed_disease: str | None = None
    note: str | None = Field(default=None, max_length=500)
    release_advice: bool = False                # re-run the rules with the confirmed disease and send the advice to the farmer


class DemoClockIn(BaseModel):
    now: datetime | None = None                 # null = back to the real clock


class DemoClockOut(BaseModel):
    now: datetime
    fixed: bool


class ProductAdminOut(BaseModel):
    product_id: str
    crop: str
    active_ingredient: str
    stage: str | None = None
    targets: list[str] = Field(default_factory=list)
    dose_text: str | None = None
    waiting_period_days: int | None = None
    ban_status: str
    enabled: bool = True


class ProductAdminPatch(BaseModel):
    enabled: bool
    note: str | None = None


class FarmerAdminOut(BaseModel):
    id: str
    name: str
    district: str | None = None
    village: str | None = None
    primary_crop: str | None = None
    language: Lang
    last_scan_at: datetime | None = None
    username: str | None = None               # the login name (never the password)
    has_login: bool = False                   # a username and a password are set
