"""The scan pipeline: photos -> quality -> crop -> disease -> history + weather -> rules -> notes -> advice -> persisted result.

Principles (CLAUDE.md): rules decide, the composer only explains; no medicine until the crop is confident or confirmed; 'not sure'
is a status, never an error. Optional parts (KB notes, audio, Zoho writes, composer) degrade with a log line; a failure of vision
or rules returns 503 and stores nothing, so the farmer can simply retry.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import AdviceOut, NextStep, QualityOut, ScanListOut, ScanOut, SpokenOut, WarningOut
from app.db.models import AdviceRow, AuditLogRow, ReviewTaskRow, ScanRow, new_id
from app.db.repo import sortable_id
from app.domain.types import (
    AdviceDraft,
    CropResult,
    DiseaseResult,
    FarmerProfile,
    LocalizedText,
    Note,
    QualityResult,
    RuleInput,
    RuleOutput,
    Severity,
    SpokenText,
    ValidatedAdvice,
    WeatherSnapshot,
)
from app.security import timeutil
from app.security.errors import ApiError
from app.security.uploads import CleanImage
from app.services import texts
from app.services.catalogue import load_catalogue
from app.services.container import Container
from app.services.history import merged_history
from app.services.photo_store import PhotoStore
from app.services.presenters import advice_out, crop_out, disease_out, ist, quality_out
from app.services.prompts import PromptBook
from app.services.speech import speak
from app.vision.labels import canonical_crop, canonical_crops

logger = logging.getLogger(__name__)

ScanStatus = Literal["ok", "confirm_crop", "needs_expert", "no_approved_data", "photo_unusable", "not_a_disease"]
_STATUS_FROM_RULES: dict[str, ScanStatus] = {
    "advice": "ok",
    "expert_review": "needs_expert",
    "needs_more_info": "needs_expert",
    "no_approved_data": "no_approved_data",
    "not_a_disease": "not_a_disease",
}
_TIP_BY_ISSUE = {"blurry": "scan_retake_blurry", "too_dark": "scan_retake_dark", "too_bright": "scan_retake_dark",
                 "too_small": "scan_retake_far", "no_leaf": "scan_retake_no_leaf", "unreadable": "scan_retake_blurry"}
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CLIENT_CROP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$")
FARMER_REQUEST_PREFIX = "farmer_request"      # ReviewTask.reason of tasks the farmer asked for (POST /v1/expert-requests)


def _unavailable() -> ApiError:
    return ApiError(503, "analysis_unavailable", "We could not check your photo right now. Please try again.")


@dataclass
class Outcome:
    """Everything the pipeline decided, before anything is written."""
    status: ScanStatus
    quality: QualityOut
    spoken: SpokenOut
    next_steps: list[NextStep]
    crop: CropResult | None = None
    crop_confirmed: bool = False
    disease: DiseaseResult | None = None
    rules: RuleOutput | None = None
    advice: AdviceOut | None = None
    expert_reason: str | None = None            # set -> a ReviewTask is needed
    rule_trace: list[str] = field(default_factory=list)


class ScanService:
    def __init__(self, container: Container, db: Session, store: PhotoStore | None = None) -> None:
        self.c = container
        self.db = db
        self.store = store or PhotoStore(container.settings.storage_dir)
        self.catalogue = load_catalogue(str(container.settings.data_dir))
        self.book = PromptBook(container.settings.voice_dir)

    # ================================================================== public API
    def find_by_request_id(self, farmer: FarmerProfile, client_request_id: str | None) -> ScanOut | None:
        """The stored result of the scan this farmer already created with this Idempotency-Key (None: no key, or a new one)."""
        if client_request_id is None:
            return None
        row = self.db.scalars(select(ScanRow).where(ScanRow.farmer_id == farmer.id,
                                                    ScanRow.client_request_id == client_request_id)).first()
        return self._cached(row) if row is not None else None

    def create(self, farmer: FarmerProfile, images: list[CleanImage], *, client_crop: str | None = None,
               client_confidence: float | None = None, taken_at: datetime | None = None,
               lat: float | None = None, lon: float | None = None, client_request_id: str | None = None) -> ScanOut:
        """Analyse and store a new scan. With a `client_request_id` a concurrent twin that lost the race to the unique index
        returns the winner's stored result (its photos and rows are rolled back), never an error."""
        now = self.c.clock.now()
        scan_id = sortable_id()
        jpegs = [image.data for image in images]
        outcome = self._evaluate(farmer, scan_id, jpegs, now=now, client_crop=client_crop,
                                 client_confidence=client_confidence, confirmed_crop=None,
                                 lat=_first(lat, farmer.lat), lon=_first(lon, farmer.lon))
        paths = [self.store.save(farmer.id, scan_id, data) for data in jpegs]
        row = ScanRow(id=scan_id, farmer_id=farmer.id, created_at=now, status=outcome.status, client_crop=client_crop,
                      lat=lat, lon=lon, photo_paths=paths, client_request_id=client_request_id)
        try:
            return self._persist(farmer, row, outcome, now, new_row=True,
                                 audit_extra={"taken_at": taken_at.isoformat() if taken_at else None}, on_failure_delete=paths)
        except IntegrityError:
            stored = self.find_by_request_id(farmer, client_request_id)      # _persist already rolled back and removed the photos
            if stored is None:
                raise
            logger.info("scan upload lost the race to its twin farmer=%s: returning the stored result", farmer.id)
            return stored

    def photo_count(self, farmer: FarmerProfile, scan_id: str) -> int:
        """Photos already stored on the scan (also the ownership check, so a stranger gets 404 before any upload is read)."""
        return len(self._owned(farmer, scan_id).photo_paths or [])

    def add_photos(self, farmer: FarmerProfile, scan_id: str, images: list[CleanImage]) -> ScanOut:
        row = self._owned(farmer, scan_id)
        if len(row.photo_paths or []) + len(images) > self.c.settings.max_photos_per_scan:
            raise ApiError(400, "too_many_photos", f"A scan can have at most {self.c.settings.max_photos_per_scan} photos.")
        now = self.c.clock.now()
        stored = self._load_photos(row, required=False)             # old photos may have expired; the new ones are enough
        new_jpegs = [image.data for image in images]
        confirmed = row.crop_id if row.crop_confirmed else None
        outcome = self._evaluate(farmer, scan_id, stored + new_jpegs, now=now, client_crop=row.client_crop,
                                 client_confidence=None, confirmed_crop=confirmed,
                                 lat=_first(row.lat, farmer.lat), lon=_first(row.lon, farmer.lon))
        new_paths = [self.store.save(farmer.id, scan_id, data) for data in new_jpegs]
        row.photo_paths = [*list(row.photo_paths or []), *new_paths]
        return self._persist(farmer, row, outcome, now, new_row=False, audit_extra={"added_photos": len(new_paths)},
                             on_failure_delete=new_paths)

    def confirm_crop(self, farmer: FarmerProfile, scan_id: str, crop_id: str) -> ScanOut:
        row = self._owned(farmer, scan_id)
        crop = self._known_crop(farmer, row, crop_id)
        if row.crop_confirmed and row.crop_id == crop and row.status != "confirm_crop":
            return self._cached(row)                                         # a retried tick returns the same answer
        now = self.c.clock.now()
        outcome = self._evaluate(farmer, scan_id, self._load_photos(row), now=now, client_crop=row.client_crop,
                                 client_confidence=None, confirmed_crop=crop,
                                 lat=_first(row.lat, farmer.lat), lon=_first(row.lon, farmer.lon))
        return self._persist(farmer, row, outcome, now, new_row=False, audit_extra={"confirmed_crop": crop})

    def release_expert_result(self, farmer: FarmerProfile, row: ScanRow, crop_id: str, disease_id: str | None,
                              disease_confirmed: bool) -> ScanOut | None:
        """Re-run the rules with a crop/disease confirmed by the agronomist (no photo analysis).

        Returns the new stored result when the rules give advice; None (nothing written) when they still do not, so an expert
        cannot push out advice the rules would refuse. A confirmed disease counts as certain; an unconfirmed one keeps its score.
        """
        now = self.c.clock.now()
        history, history_ok = merged_history(self.c, self.db, farmer, now)
        confidence = 1.0 if disease_confirmed else (row.disease_confidence or 0.0)
        disease = DiseaseResult(crop_id=crop_id, disease_id=disease_id, confidence=confidence, model="agronomist")
        rule_in = RuleInput(farmer=farmer, crop_id=crop_id, disease_id=disease_id, disease_confidence=confidence, now=now,
                            history=history, weather=self._weather(farmer, _first(row.lat, farmer.lat),
                                                                   _first(row.lon, farmer.lon), now),
                            language=farmer.language)
        rules = self._recommend(row.id, rule_in)
        if rules.status != "advice":
            return None
        advice = self._advise(row.id, crop_id, rule_in, rules, history_ok, now)
        quality = QualityOut.model_validate(row.quality) if row.quality else QualityOut(usable=True)
        outcome = Outcome(status="ok", quality=quality, crop=CropResult(crop_id=crop_id, confidence=1.0, source="expert_confirmed"),
                          crop_confirmed=True, disease=disease, rules=rules, advice=advice, rule_trace=[*rules.trace, *rules.reasons],
                          spoken=advice.spoken, next_steps=self._next_steps("ok", len(row.photo_paths or []), bool(advice.products)))
        return self._persist(farmer, row, outcome, now, new_row=False, audit_extra={"released_by": "agronomist"})

    def get(self, farmer: FarmerProfile, scan_id: str) -> ScanOut:
        return self._cached(self._owned(farmer, scan_id))

    def list_scans(self, farmer: FarmerProfile, limit: int, cursor: str | None) -> ScanListOut:
        limit = max(1, min(limit, 50))
        stmt = select(ScanRow).where(ScanRow.farmer_id == farmer.id)
        if cursor is not None:
            if not _ID_RE.match(cursor):
                raise ApiError(400, "invalid_cursor", "The page cursor is not valid.")
            stmt = stmt.where(ScanRow.id < cursor)
        rows = list(self.db.scalars(stmt.order_by(ScanRow.id.desc()).limit(limit + 1)))
        page = rows[:limit]
        return ScanListOut(items=[self._cached(r) for r in page], next_cursor=page[-1].id if len(rows) > limit else None)

    # ================================================================== the pipeline (no database writes)
    def _evaluate(self, farmer: FarmerProfile, scan_id: str, jpegs: list[bytes], *, now: datetime, client_crop: str | None,
                  client_confidence: float | None, confirmed_crop: str | None, lat: float | None, lon: float | None) -> Outcome:
        qualities = self._check_quality(scan_id, jpegs)
        quality = quality_out(qualities, self._tip(qualities))
        usable = [jpeg for jpeg, q in zip(jpegs, qualities, strict=True) if q.usable]
        if not usable:
            return self._unusable(quality)

        crop = (CropResult(crop_id=confirmed_crop, confidence=1.0, source="farmer_confirmed")
                if confirmed_crop else self._identify(scan_id, usable, farmer, client_crop, client_confidence))
        if crop.crop_id is None or crop.unknown:
            return self._unknown_crop(crop, quality, len(jpegs))
        if crop.needs_confirmation and not confirmed_crop:
            return self._needs_confirmation(crop, quality)

        disease = self._classify(scan_id, usable, crop.crop_id)
        history, history_ok = merged_history(self.c, self.db, farmer, now)
        weather = self._weather(farmer, lat, lon, now)
        rule_in = RuleInput(farmer=farmer, crop_id=crop.crop_id, disease_id=disease.disease_id if disease.model_covers_crop else None,
                            disease_confidence=disease.confidence, now=now, history=history, weather=weather,
                            language=farmer.language)
        rules = self._recommend(scan_id, rule_in)
        status = _STATUS_FROM_RULES[rules.status]
        advice = self._advise(scan_id, crop.crop_id, rule_in, rules, history_ok, now)
        return Outcome(status=status, quality=quality, crop=crop, crop_confirmed=bool(confirmed_crop), disease=disease,
                       rules=rules, advice=advice, rule_trace=[*rules.trace, *rules.reasons],
                       spoken=advice.spoken,                  # the composer writes a complete text for every rule outcome
                       next_steps=self._next_steps(status, len(jpegs), bool(advice.products), rules.status == "needs_more_info"),
                       expert_reason=f"{rules.status}: {','.join(rules.reasons) or 'review'}" if status == "needs_expert" else None)

    # ------------------------------------------------------------------ vision
    def _check_quality(self, scan_id: str, jpegs: list[bytes]) -> list[QualityResult]:
        try:
            return [self.c.quality.check(jpeg) for jpeg in jpegs]
        except Exception:
            logger.exception("photo quality check failed scan=%s", scan_id)
            raise _unavailable() from None

    def _tip(self, qualities: list[QualityResult]) -> str | None:
        """Voice prompt for the first unusable photo; None when at least one photo is usable."""
        if any(q.usable for q in qualities):
            return None
        first = qualities[0]
        if first.tip_prompt_id:
            return first.tip_prompt_id
        return next((_TIP_BY_ISSUE[i.value] for i in first.issues if i.value in _TIP_BY_ISSUE), "scan_retake_blurry")

    def _identify(self, scan_id: str, usable: list[bytes], farmer: FarmerProfile, client_crop: str | None,
                  client_confidence: float | None) -> CropResult:
        try:
            return self.c.crop_identifier.identify(usable, farmer.crops, client_crop, client_confidence)
        except Exception:
            logger.exception("crop identification failed scan=%s", scan_id)
            raise _unavailable() from None

    def _classify(self, scan_id: str, usable: list[bytes], crop_id: str) -> DiseaseResult:
        try:
            return self.c.disease_classifier.classify(usable, crop_id)
        except Exception:
            logger.exception("disease classification failed scan=%s", scan_id)
            raise _unavailable() from None

    # ------------------------------------------------------------------ context and rules
    def _weather(self, farmer: FarmerProfile, lat: float | None, lon: float | None, now: datetime) -> WeatherSnapshot | None:
        try:
            return self.c.weather.snapshot(farmer.station_id, lat, lon, now)
        except Exception:
            logger.exception("weather unavailable; rules run without it farmer=%s", farmer.id)
            return None

    def _recommend(self, scan_id: str, rule_in: RuleInput) -> RuleOutput:
        try:
            return self.c.rules.recommend(rule_in)
        except Exception:
            logger.exception("rules engine failed scan=%s", scan_id)
            raise _unavailable() from None

    def _notes(self, rules: RuleOutput, crop_id: str) -> list[Note]:
        query = rules.notes_query or {}
        try:
            return list(self.c.kb.notes_for(
                query.get("crop") or crop_id, query.get("disease_id", rules.disease_id), query.get("stage", rules.stage),
                list(query.get("product_ids") or [p.product_id for p in rules.products])))
        except Exception:
            logger.exception("knowledge base unavailable; advice has no sources")
            return []

    # ------------------------------------------------------------------ advice
    def _advise(self, scan_id: str, crop_id: str, rule_in: RuleInput, rules: RuleOutput, history_ok: bool,
                now: datetime) -> AdviceOut:
        notes = self._notes(rules, crop_id)
        try:
            composed = self.c.composer.compose(rule_in, rules, notes)
        except Exception:
            logger.exception("advice composer failed; using the safe template scan=%s", scan_id)
            composed = _safe_composed(rules)
        extra = [] if history_ok else [WarningOut(code="HISTORY_UNAVAILABLE", level=Severity.yellow, text=texts.HISTORY_UNAVAILABLE)]
        draft = composed.draft
        spoken_text = LocalizedText(en=draft.spoken.en or f"{draft.headline.en} {draft.summary.en}".strip(),
                                    hi=draft.spoken.hi or f"{draft.headline.hi} {draft.summary.hi}".strip())
        if extra:
            spoken_text = self.book.join(spoken_text, texts.HISTORY_UNAVAILABLE)
        return advice_out(advice_id=sortable_id(), scan_id=scan_id, crop_id=crop_id, rules=rules, composed=composed,
                          spoken=speak(self.c.audio, spoken_text),
                          sources=list(dict.fromkeys(n.source_ref for n in notes if n.source_ref)),
                          extra_warnings=extra, created_at=now)

    # ------------------------------------------------------------------ outcomes that stop before the rules
    def _unusable(self, quality: QualityOut) -> Outcome:
        tip = quality.tip_prompt_id or "scan_retake_blurry"
        text = self.book.get(tip, texts.RETAKE_FALLBACK)
        return Outcome(status="photo_unusable", quality=quality, spoken=speak(self.c.audio, text),
                       next_steps=[NextStep(action="retake", prompt_id=tip)])

    def _unknown_crop(self, crop: CropResult, quality: QualityOut, photos: int) -> Outcome:
        crop = crop.model_copy(update={"crop_id": None, "unknown": True})
        text = self.book.join(self.book.get("crop_is_unknown", texts.CROP_UNKNOWN_FALLBACK),
                              self.book.get("result_expert", texts.RESULT_EXPERT_FALLBACK))
        return Outcome(status="needs_expert", quality=quality, crop=crop, spoken=speak(self.c.audio, text),
                       expert_reason="crop_unknown", next_steps=self._next_steps("needs_expert", photos, False))

    def _needs_confirmation(self, crop: CropResult, quality: QualityOut) -> Outcome:
        assert crop.crop_id is not None  # noqa: S101
        said = self.book.get(f"crop_is_{crop.crop_id.lower()}")
        if not said.en:
            name = self.catalogue.crop_name(crop.crop_id)
            said = LocalizedText(en=texts.CROP_IS_FALLBACK.en.format(crop=name.en), hi=texts.CROP_IS_FALLBACK.hi.format(crop=name.hi))
        text = self.book.join(said, self.book.get("crop_confirm_prompt", texts.CROP_CONFIRM_FALLBACK))
        return Outcome(status="confirm_crop", quality=quality, crop=crop, spoken=speak(self.c.audio, text),
                       next_steps=[NextStep(action="confirm_crop", prompt_id="crop_confirm_prompt")])

    # ------------------------------------------------------------------ result text and next steps
    def _next_steps(self, status: str, photos: int, has_products: bool, more_info: bool = False) -> list[NextStep]:
        """What the app offers next. `more_info`: the rules asked for another photo, so that comes before 'ask an expert'."""
        can_add = photos < self.c.settings.max_photos_per_scan
        add = [NextStep(action="add_photo", prompt_id="scan_add_more")] if can_add else []
        expert = NextStep(action="ask_expert", prompt_id="result_expert")
        if status == "ok":
            sprayed = [NextStep(action="mark_sprayed", prompt_id="diary_tick_sprayed")] if has_products else []
            return [*sprayed, NextStep(action="done", prompt_id="result_next_diary")]
        if status == "needs_expert":
            return [*add, expert] if more_info else [expert, *add]
        if status == "not_a_disease":
            return [*add, expert]
        return [expert]                                  # no_approved_data

    # ================================================================== persistence
    def _persist(self, farmer: FarmerProfile, row: ScanRow, outcome: Outcome, now: datetime, *, new_row: bool,
                 audit_extra: dict, on_failure_delete: list[str] | None = None) -> ScanOut:
        try:
            row.status = outcome.status
            row.crop_id = outcome.crop.crop_id if outcome.crop else None
            row.crop_confidence = outcome.crop.confidence if outcome.crop else None
            row.crop_source = outcome.crop.source if outcome.crop else None
            row.crop_confirmed = outcome.crop_confirmed and outcome.crop is not None
            row.disease_id = (outcome.rules.disease_id if outcome.rules and outcome.rules.disease_id else
                              (outcome.disease.disease_id if outcome.disease else None))
            row.disease_confidence = outcome.disease.confidence if outcome.disease else None
            row.route = outcome.rules.route if outcome.rules else None
            row.quality = outcome.quality.model_dump(mode="json")
            if new_row:
                self.db.add(row)
                self.db.flush()                                              # review task and advice reference the scan
            task_id = self._sync_review_task(farmer, row.id, outcome, now)
            result = self._scan_out(row, outcome, task_id)
            row.result = result.model_dump(mode="json")
            if outcome.advice is not None:
                self._store_advice(farmer, row.id, outcome, now)
            self.db.add(AuditLogRow(id=new_id(), at=timeutil.utcnow(), actor=farmer.id, action="scan.evaluated", entity="scan",
                                    entity_id=row.id, detail={"status": outcome.status, "crop": row.crop_id,
                                                              "disease": row.disease_id, **audit_extra}))
            self.db.commit()
        except Exception:
            self.db.rollback()
            self.store.delete(on_failure_delete or [])
            raise
        self._write_diagnosis(farmer, row, outcome, now)
        logger.info("scan evaluated scan=%s farmer=%s status=%s photos=%d", row.id, farmer.id, outcome.status, len(row.photo_paths or []))
        return result

    def _scan_out(self, row: ScanRow, outcome: Outcome, review_task_id: str | None) -> ScanOut:
        return ScanOut(
            id=row.id, status=outcome.status, created_at=ist(row.created_at), photos=len(row.photo_paths or []),
            crop=crop_out(outcome.crop, self.catalogue) if outcome.crop else None, quality=outcome.quality,
            disease=disease_out(outcome.disease, outcome.rules, self.catalogue), advice=outcome.advice,
            review_task_id=review_task_id, next_steps=outcome.next_steps, spoken=outcome.spoken)

    def _store_advice(self, farmer: FarmerProfile, scan_id: str, outcome: Outcome, now: datetime) -> None:
        advice = outcome.advice
        assert advice is not None  # noqa: S101
        self.db.add(AdviceRow(id=advice.id, scan_id=scan_id, farmer_id=farmer.id, crop_id=advice.crop_id,
                              disease_id=advice.disease_id, severity=str(advice.severity.value),
                              payload=advice.model_dump(mode="json"), rule_trace=outcome.rule_trace,
                              validated=advice.validated, created_at=now))

    def _sync_review_task(self, farmer: FarmerProfile, scan_id: str, outcome: Outcome, now: datetime) -> str | None:
        """At most one open task per scan: update it while the scan still needs an expert, close it once it no longer does."""
        open_task = self.db.scalars(select(ReviewTaskRow).where(ReviewTaskRow.scan_id == scan_id,
                                                                ReviewTaskRow.status == "open")).first()
        asked_by_farmer = open_task is not None and open_task.reason.startswith(FARMER_REQUEST_PREFIX)
        if outcome.expert_reason is None:
            if open_task is not None and not asked_by_farmer:
                open_task.status = "resolved"
                open_task.resolved_at = now
                open_task.resolution = {"auto": "superseded_by_new_result"}
                return None
            return open_task.id if open_task is not None else None
        if open_task is not None:
            if not asked_by_farmer:
                open_task.reason = outcome.expert_reason
            return open_task.id
        task = ReviewTaskRow(id=sortable_id(), scan_id=scan_id, farmer_id=farmer.id, status="open",
                             reason=outcome.expert_reason, created_at=now)
        self.db.add(task)
        return task.id

    def _write_diagnosis(self, farmer: FarmerProfile, row: ScanRow, outcome: Outcome, now: datetime) -> None:
        """Best effort: record the diagnosis in Zoho. Not for 'confirm crop' or 'unusable photo' (nothing was diagnosed)."""
        if outcome.rules is None:
            return
        payload = {"scan_id": row.id, "status": outcome.status, "crop_id": row.crop_id, "disease_id": row.disease_id,
                   "confidence": row.disease_confidence, "route": row.route, "severity": str(outcome.rules.severity.value),
                   "product_ids": [p.product_id for p in outcome.rules.products] if outcome.status == "ok" else [],
                   "at": now.isoformat()}
        try:
            self.c.zoho.write_diagnosis(farmer.id, payload)
        except Exception:
            logger.exception("zoho diagnosis write failed scan=%s", row.id)

    # ================================================================== helpers
    def _owned(self, farmer: FarmerProfile, scan_id: str) -> ScanRow:
        row = self.db.get(ScanRow, scan_id) if _ID_RE.match(scan_id) else None
        if row is None or row.farmer_id != farmer.id:
            raise ApiError(404, "scan_not_found", "That scan was not found.")
        return row

    def _cached(self, row: ScanRow) -> ScanOut:
        return ScanOut.model_validate(row.result)

    def _load_photos(self, row: ScanRow, required: bool = True) -> list[bytes]:
        photos = [data for rel in (row.photo_paths or []) if (data := self.store.load(rel)) is not None]
        if required and not photos:
            raise ApiError(409, "photos_unavailable", "The photos of this scan are no longer stored. Please take new photos.")
        return photos

    def _known_crop(self, farmer: FarmerProfile, row: ScanRow, raw: str) -> str:
        """The catalogue spelling of a crop the farmer may pick: any crop with data, one they grow, or one the models suggested."""
        if not _CLIENT_CROP_RE.match(raw.strip()):
            raise ApiError(422, "unknown_crop", "That crop is not known.")
        suggested = [c.get("crop_id", "") for c in ((row.result or {}).get("crop") or {}).get("candidates", [])]
        known = canonical_crops([*self.catalogue.crops, *self.c.rules.supported_crops(), *farmer.crops, *suggested])
        crop = canonical_crop(raw)
        if crop not in known:
            raise ApiError(422, "unknown_crop", "That crop is not known.")
        return crop


def _first(value: float | None, default: float | None) -> float | None:
    return default if value is None else value


def _safe_composed(rules: RuleOutput) -> ValidatedAdvice:
    """Platform-written fallback when the composer raises. For 'advice' the card still lists the rule products; other statuses
    only say to see an expert. Never normal operation: the composer has its own validated template."""
    if rules.status == "advice":
        headline, summary = texts.SAFE_ADVICE_HEADLINE, texts.SAFE_ADVICE_SUMMARY
        safety = [texts.SAFE_ADVICE_SAFETY]
    else:
        headline, summary = texts.SAFE_EXPERT_HEADLINE, texts.SAFE_EXPERT_SUMMARY
        safety = []
    draft = AdviceDraft(headline=headline, summary=summary, steps=list(rules.non_chemical), safety=safety,
                        spoken=SpokenText(en=f"{headline.en}. {summary.en}", hi=f"{headline.hi}। {summary.hi}"))
    return ValidatedAdvice(draft=draft, validated=False, problems=["composer_failed"], used_llm=False)
