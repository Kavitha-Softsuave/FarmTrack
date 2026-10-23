import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_farmer, get_db, get_limiters
from app.api.idempotency import REPLAY_HEADER, idempotency_key, serialised
from app.api.schemas import AskIn, AskOut, CitationOut, ErrorOut, ExpertRequestIn, ExpertRequestOut
from app.db.models import ExpertRequestRow, ReviewTaskRow, ScanRow
from app.db.repo import sortable_id
from app.domain.types import FarmerProfile, LocalizedText
from app.security.errors import ApiError
from app.security.ratelimit import RateLimiters, enforce
from app.services.catalogue import load_catalogue
from app.services.container import Container
from app.services.scan_service import FARMER_REQUEST_PREFIX
from app.services.speech import speak

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["ask"], responses={401: {"model": ErrorOut}})

_CROP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$")


@router.post("/ask", response_model=AskOut, responses={429: {"model": ErrorOut}, 503: {"model": ErrorOut}})
def ask(body: AskIn, farmer: FarmerProfile = Depends(get_current_farmer), container: Container = Depends(get_container),
        limiters: RateLimiters = Depends(get_limiters)) -> AskOut:
    """Q&A over approved notes only (RAG). refused=true when nothing approved supports an answer."""
    enforce(limiters.ask_farmer, farmer.id)
    question = body.question.strip()
    if len(question) < 2:
        raise ApiError(422, "invalid_question", "Please type your question.")
    crop = farmer.primary_crop                                  # a question that names a crop overrides this inside the service
    if body.crop_id:
        if not _CROP_RE.match(body.crop_id.strip()):
            raise ApiError(422, "invalid_crop", "The crop name is not valid.")
        crop = load_catalogue(str(container.settings.data_dir)).canonical_crop(body.crop_id) or body.crop_id.strip()
    try:
        result = container.ask_service.ask(question, body.language, crop)
    except Exception:
        logger.exception("ask service failed question_chars=%d", len(question))     # never the question text itself
        raise ApiError(503, "ask_unavailable", "We could not answer right now. Please try again.") from None
    text = LocalizedText(en=result.answer if result.language == "en" else "", hi=result.answer if result.language == "hi" else "")
    return AskOut(answer=result.answer, language=result.language, refused=result.refused,
                  citations=[CitationOut(note_id=c.note_id, source=c.source) for c in result.citations],
                  spoken=speak(container.audio, text))


@router.post("/expert-requests", response_model=ExpertRequestOut,
             responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def create_expert_request(body: ExpertRequestIn, response: Response, farmer: FarmerProfile = Depends(get_current_farmer),
                          request_key: str | None = Depends(idempotency_key), db: Session = Depends(get_db), container: Container = Depends(get_container),
                          limiters: RateLimiters = Depends(get_limiters)) -> ExpertRequestOut:
    """'Ask a farm expert': stores the request and, when it is about a scan, puts that scan in the agronomist queue.
    A request without a scan (a plain question) is listed for the staff in the admin 'Expert requests' page.

    Idempotent: send an `Idempotency-Key` header (a fresh UUID per queued request, kept on every retry). A replay by the same
    farmer returns the stored request (same id, 200, header `Idempotent-Replayed: true`) and creates nothing new.
    """
    with serialised("expert", farmer.id, request_key):
        stored = _request_by_key(db, farmer.id, request_key)
        if stored is not None:
            response.headers[REPLAY_HEADER] = "true"
            return _expert_out(stored)
        enforce(limiters.ask_farmer, farmer.id)
        now = container.clock.now()
        message = (body.message or "").strip() or None
        crop_id = _expert_crop(container, body.crop_id)
        if body.scan_id is not None:
            scan = db.get(ScanRow, body.scan_id)
            if scan is None or scan.farmer_id != farmer.id:
                raise ApiError(404, "scan_not_found", "That scan was not found.")
            _queue_for_expert(db, scan.id, farmer.id, message, now)
        request = ExpertRequestRow(id=sortable_id(), farmer_id=farmer.id, scan_id=body.scan_id, message=message, status="open",
                                   created_at=now, client_request_id=request_key, crop_id=crop_id)
        db.add(request)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            stored = _request_by_key(db, farmer.id, request_key)                   # lost the race to a twin with the same key
            if stored is None:
                raise
            response.headers[REPLAY_HEADER] = "true"
            return _expert_out(stored)
        return _expert_out(request)


def _expert_out(request: ExpertRequestRow) -> ExpertRequestOut:
    return ExpertRequestOut(id=request.id, status="resolved" if request.status == "resolved" else "open")


def _request_by_key(db: Session, farmer_id: str, key: str | None) -> ExpertRequestRow | None:
    if key is None:
        return None
    return db.scalars(select(ExpertRequestRow).where(ExpertRequestRow.farmer_id == farmer_id,
                                                     ExpertRequestRow.client_request_id == key)).first()


def _expert_crop(container: Container, raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    if not _CROP_RE.match(raw.strip()):
        raise ApiError(422, "invalid_crop", "The crop name is not valid.")
    return load_catalogue(str(container.settings.data_dir)).canonical_crop(raw) or raw.strip()


def _queue_for_expert(db: Session, scan_id: str, farmer_id: str, message: str | None, now: datetime) -> None:
    reason = FARMER_REQUEST_PREFIX + (f": {message}" if message else "")
    task = db.scalars(select(ReviewTaskRow).where(ReviewTaskRow.scan_id == scan_id, ReviewTaskRow.status == "open")).first()
    if task is None:
        db.add(ReviewTaskRow(id=sortable_id(), scan_id=scan_id, farmer_id=farmer_id, status="open", reason=reason, created_at=now))
    elif not task.reason.startswith(FARMER_REQUEST_PREFIX):
        task.reason = f"{reason}; was: {task.reason}"
