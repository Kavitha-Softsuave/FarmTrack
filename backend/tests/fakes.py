"""Fake providers for the API, service and security tests (the real ones belong to the other packages)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from app.clock import IST, Clock
from app.config import Settings
from app.domain.types import (
    AdviceDraft,
    AskCitation,
    AskResult,
    CropCandidate,
    CropResult,
    DiseaseCandidate,
    DiseaseResult,
    FarmerProfile,
    LocalizedText,
    Note,
    ProductChoice,
    QualityIssue,
    QualityResult,
    RiskItem,
    RuleInput,
    RuleOutput,
    SensorReading,
    Severity,
    SpokenText,
    SprayRecord,
    TimingAdvice,
    ValidatedAdvice,
    WarningItem,
    WeatherSnapshot,
)
from app.services.container import Container

NOW = datetime(2026, 5, 12, 8, 0, tzinfo=IST)
DEMO_PHONE = "+910000000001"                   # farmer F001: Apple, Hindi, station ST01 (seeded from data/farmers.csv)
DEMO_PHONE_2 = "+910000000002"                 # farmer F002: Apple, English
SCAB = "Apple___Apple_scab"


def plain_settings(**overrides: Any) -> Settings:
    """Settings built from the process environment only: never the repo-root .env (it holds real secrets)."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def lt(en: str, hi: str | None = None) -> LocalizedText:
    return LocalizedText(en=en, hi=hi or f"hi:{en}")


def sample_product(**overrides: Any) -> ProductChoice:
    base: dict[str, Any] = dict(
        product_id="P012", crop="Apple", active_ingredient="Myclobutanil", active_ingredient_hi="माइक्लोब्यूटानिल",
        formulation="10% WP", brand_examples=["Systhane"], category="fungicide", frac_irac_code="3", behaviour="systemic",
        stage="petal_fall", dose_min=80.0, dose_max=80.0, dose_unit="g/200L", waiting_period_days=21)
    return ProductChoice(**{**base, **overrides})


def rule_output(status: str = "advice", **overrides: Any) -> RuleOutput:
    """A RuleOutput for apple scab by default; `status` picks the branch."""
    defaults: dict[str, Any] = dict(status=status, route="auto_advice" if status == "advice" else "expert_queue",
                                    severity=Severity.yellow, crop_id="Apple", disease_id=SCAB, stage="petal_fall",
                                    notes_query={"crop": "Apple", "disease_id": SCAB, "stage": "petal_fall",
                                                 "product_ids": ["P012"]},
                                    trace=["fake rule trace"])
    if status == "advice":
        defaults["products"] = [sample_product()]
        defaults["timing"] = TimingAdvice(action="spray_now", text=lt("Spray now."), rain_next_12h_mm=0.0)
        defaults["non_chemical"] = [lt("Collect fallen leaves.")]
    elif status in ("no_approved_data", "not_a_disease"):
        defaults["route"] = "none"
    if status in ("expert_review", "needs_more_info"):
        defaults["reasons"] = ["low_confidence"]
    return RuleOutput(**{**defaults, **overrides})


class FakeQuality:
    """Usable by default. `sequence` gives one QualityResult per call (cycled); `raises` simulates a crash."""

    def __init__(self, sequence: list[QualityResult] | None = None) -> None:
        self.sequence = sequence
        self.calls = 0
        self.raises: Exception | None = None

    def check(self, image_bytes: bytes) -> QualityResult:
        index = self.calls
        self.calls += 1
        if self.raises:
            raise self.raises
        if self.sequence:
            return self.sequence[index % len(self.sequence)]
        return QualityResult(usable=True, width=640, height=480)


def unusable(issue: QualityIssue = QualityIssue.blurry, tip: str | None = "scan_retake_blurry") -> QualityResult:
    return QualityResult(usable=False, issues=[issue], tip_prompt_id=tip)


class FakeCropIdentifier:
    def __init__(self, result: CropResult | None = None) -> None:
        self.result = result or CropResult(crop_id="Apple", confidence=0.93, source="server_model",
                                           candidates=[CropCandidate(crop_id="Apple", confidence=0.93)])
        self.calls: list[dict] = []
        self.raises: Exception | None = None

    def identify(self, images: list[bytes], farmer_crops: list[str], client_guess: str | None = None,
                 client_confidence: float | None = None) -> CropResult:
        self.calls.append({"images": len(images), "farmer_crops": list(farmer_crops), "client_guess": client_guess,
                           "client_confidence": client_confidence})
        if self.raises:
            raise self.raises
        return self.result


class FakeDiseaseClassifier:
    def __init__(self, result: DiseaseResult | None = None) -> None:
        self.result = result or DiseaseResult(crop_id="Apple", disease_id=SCAB, confidence=0.9, model="fake",
                                              candidates=[DiseaseCandidate(disease_id=SCAB, confidence=0.9)])
        self.calls: list[dict] = []
        self.raises: Exception | None = None

    def classify(self, images: list[bytes], crop_id: str) -> DiseaseResult:
        self.calls.append({"images": len(images), "crop_id": crop_id})
        if self.raises:
            raise self.raises
        return self.result.model_copy(update={"crop_id": crop_id})


class FakeRules:
    def __init__(self, output: RuleOutput | None = None) -> None:
        self.output = output or rule_output()
        self.inputs: list[RuleInput] = []
        self.raises: Exception | None = None
        self.risks: list[RiskItem] = []
        self.spray_warnings: list[WarningItem] = []
        self.spray_checks: list[dict] = []
        self.crops = ["Apple", "Tomato", "Potato", "Maize", "Grape"]
        self.risk_history: list[SprayRecord] = []

    def recommend(self, inp: RuleInput) -> RuleOutput:
        self.inputs.append(inp)
        if self.raises:
            raise self.raises
        return self.output

    def evaluate_risks(self, farmer: FarmerProfile, weather: WeatherSnapshot, now: datetime, history: list[SprayRecord]) -> list:
        self.risk_history = history
        return self.risks

    def supported_crops(self) -> list[str]:
        return list(self.crops)

    def check_spray(self, farmer: FarmerProfile, record: SprayRecord, history: list[SprayRecord], now: datetime) -> list:
        self.spray_checks.append({"record": record, "history": history})
        return self.spray_warnings


class FakeComposer:
    def __init__(self) -> None:
        self.calls: list[tuple[RuleInput, RuleOutput, list[Note]]] = []
        self.raises: Exception | None = None
        self.validated = True

    def compose(self, inp: RuleInput, out: RuleOutput, notes: list[Note]) -> ValidatedAdvice:
        self.calls.append((inp, out, notes))
        if self.raises:
            raise self.raises
        draft = AdviceDraft(
            headline=lt(f"{out.status} for {out.crop_id}"), summary=lt("Summary text."),
            steps=[lt(p.active_ingredient) for p in out.products] + list(out.non_chemical), safety=[lt("Wear gloves.")],
            spoken=SpokenText(en=f"Spoken {out.status}", hi=f"बोला {out.status}"),
            product_ids_mentioned=[p.product_id for p in out.products])
        return ValidatedAdvice(draft=draft, validated=self.validated, used_llm=False)


class FakeAudio:
    """AudioStore: content-addressed urls, no files. `fail` simulates a broken TTS."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.fail = False

    def get_or_create(self, text: str, lang: str, speed: float = 0.9) -> tuple[str, str] | None:
        if self.fail:
            raise RuntimeError("tts down")
        self.requests.append((lang, text))
        digest = hashlib.sha256(f"{lang}:{text}".encode()).hexdigest()
        return f"/audio/{digest}.mp3", digest


class FakeKB:
    def __init__(self, notes: list[Note] | None = None) -> None:
        self.notes = notes if notes is not None else [
            Note(note_id="N1", topic="scab", text_en="Scab note", source_ref="HP 2026 schedule"),
            Note(note_id="N2", topic="dose", text_en="Dose note", source_ref="HP 2026 schedule"),
            Note(note_id="N3", topic="rain", text_en="Rain note", source_ref="NIPHM")]
        self.raises: Exception | None = None
        self.queries: list[dict] = []

    def notes_for(self, crop: str, disease_id: str | None, stage: str | None, product_ids: list[str], k: int = 6) -> list[Note]:
        self.queries.append({"crop": crop, "disease_id": disease_id, "stage": stage, "product_ids": product_ids})
        if self.raises:
            raise self.raises
        return self.notes

    def search(self, query: str, k: int = 5, crop: str | None = None, disease_id: str | None = None,
               stage: str | None = None) -> list[Note]:
        return self.notes


class FakeAsk:
    def __init__(self) -> None:
        self.result = AskResult(answer="Use the approved schedule.", language="en",
                                citations=[AskCitation(note_id="N1", source="HP 2026 schedule")])
        self.calls: list[tuple[str, str, str | None]] = []
        self.raises: Exception | None = None

    def ask(self, question: str, language: str, crop_id: str | None = None) -> AskResult:
        self.calls.append((question, language, crop_id))
        if self.raises:
            raise self.raises
        return self.result.model_copy(update={"language": language})


class FakeZoho:
    def __init__(self) -> None:
        self.history: list[SprayRecord] = []
        self.spray_writes: list[tuple[str, SprayRecord]] = []
        self.diagnoses: list[tuple[str, dict]] = []
        self.write_ok = True
        self.history_raises: Exception | None = None
        self.diagnosis_raises: Exception | None = None
        self.history_calls: list[datetime | None] = []

    def get_farmer(self, farmer_id: str) -> FarmerProfile | None:
        return None

    def get_history(self, farmer_id: str, until: datetime | None = None) -> list[SprayRecord]:
        self.history_calls.append(until)
        if self.history_raises:
            raise self.history_raises
        return [r for r in self.history if until is None or r.sprayed_at <= until]

    def write_spray(self, farmer_id: str, record: SprayRecord) -> bool:
        self.spray_writes.append((farmer_id, record))
        return self.write_ok

    def write_diagnosis(self, farmer_id: str, payload: dict[str, Any]) -> bool:
        if self.diagnosis_raises:
            raise self.diagnosis_raises
        self.diagnoses.append((farmer_id, payload))
        return True


class FakeIoT:
    def __init__(self) -> None:
        self.reading: SensorReading | None = SensorReading(station_id="ST01", time=NOW - timedelta(hours=1), temp_c=14.0,
                                                           rh_pct=80.0, rain_mm=0.0, leaf_wetness_min=10, soil_moisture_pct=40.0)
        self.stale = False
        self.raises: Exception | None = None

    def latest(self, station_id: str, now: datetime) -> SensorReading | None:
        if self.raises:
            raise self.raises
        return self.reading

    def is_stale(self, station_id: str, now: datetime, max_age_hours: int = 48) -> bool:
        return self.stale


class FakeWeather:
    def __init__(self) -> None:
        self.snapshot_value = WeatherSnapshot(station_id="ST01", as_of=NOW, temp_c=14.0, rh_pct=80.0, rain_last_24h_mm=0.5,
                                              rain_next_12h_mm=0.0, rain_next_48h_mm=0.0)
        self.raises: Exception | None = None
        self.calls: list[tuple] = []

    def snapshot(self, station_id: str | None, lat: float | None, lon: float | None, now: datetime) -> WeatherSnapshot:
        self.calls.append((station_id, lat, lon, now))
        if self.raises:
            raise self.raises
        return self.snapshot_value


class FakePush:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, dict | None]] = []

    def send(self, token: str, title: str, body: str, data: dict[str, str] | None = None) -> bool:
        self.sent.append((token, title, body, data))
        return True


class FakeLLM:
    name = "fake"

    def generate_json(self, prompt: str, schema: dict[str, Any], schema_name: str = "response",
                      images: list[bytes] | None = None) -> dict[str, Any]:
        return {}


def make_container(settings: Settings, **overrides: Any) -> Container:
    """A Container of fakes on the frozen demo clock. Pass any field to replace it."""
    parts: dict[str, Any] = dict(
        settings=settings, clock=Clock(NOW), rules=FakeRules(), quality=FakeQuality(), crop_identifier=FakeCropIdentifier(),
        disease_classifier=FakeDiseaseClassifier(), llm=FakeLLM(), composer=FakeComposer(), audio=FakeAudio(), kb=FakeKB(),
        ask_service=FakeAsk(), zoho=FakeZoho(), iot=FakeIoT(), weather=FakeWeather(), push=FakePush())
    return Container(**{**parts, **overrides})
