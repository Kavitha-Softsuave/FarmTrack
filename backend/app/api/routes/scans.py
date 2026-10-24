import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_farmer, get_db, get_limiters
from app.api.idempotency import KEY_RE, REPLAY_HEADER, idempotency_key, serialised
from app.api.schemas import CropConfirmIn, ErrorOut, ScanListOut, ScanOut
from app.domain.types import FarmerProfile
from app.security.errors import ApiError
from app.security.ratelimit import RateLimiters, enforce
from app.security.uploads import process_uploads
from app.services.container import Container
from app.services.scan_service import ScanService

router = APIRouter(prefix="/v1/scans", tags=["scans"], responses={401: {"model": ErrorOut}})

_CROP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$")
_SCAN_ERRORS: dict[int | str, dict[str, Any]] = {400: {"model": ErrorOut}, 413: {"model": ErrorOut}, 429: {"model": ErrorOut}, 503: {"model": ErrorOut}}


def _client_crop(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    if not _CROP_RE.match(raw.strip()):
        raise ApiError(400, "invalid_client_crop", "client_crop is not a valid crop name.")
    return raw.strip()


def _unit_interval(value: float | None) -> float | None:
    if value is not None and not 0.0 <= value <= 1.0:
        raise ApiError(400, "invalid_client_confidence", "client_confidence must be between 0 and 1.")
    return value


def _location(lat: float | None, lon: float | None) -> tuple[float | None, float | None]:
    if (lat is None) != (lon is None) or (lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180)):
        raise ApiError(400, "invalid_location", "lat and lon must be sent together and be valid coordinates.")
    return lat, lon


def _taken_at(raw: str | None) -> datetime | None:
    if raw is None or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.strip())
    except ValueError:
        raise ApiError(400, "invalid_taken_at", "taken_at must be an ISO-8601 date and time.") from None


@router.post("", response_model=ScanOut, responses=_SCAN_ERRORS)
def create_scan(response: Response,
                photos: list[UploadFile] = File(..., description="1 to 4 JPEG/PNG photos of the same crop"),
                client_crop: str | None = Form(None, description="Crop guessed by the on-device model, if any"),
                client_confidence: float | None = Form(None),
                taken_at: str | None = Form(None, description="ISO-8601 time the phone took the photo (offline uploads: send it)"),
                offline: bool = Form(False, description="true when this upload waited in the app's offline queue"),
                lat: float | None = Form(None), lon: float | None = Form(None),
                farmer: FarmerProfile = Depends(get_current_farmer), request_key: str | None = Depends(idempotency_key),
                db: Session = Depends(get_db),
                container: Container = Depends(get_container), limiters: RateLimiters = Depends(get_limiters)) -> ScanOut:
    """Pipeline: photo quality, crop identification, disease, rules, advice, spoken audio.
    Always returns 200 with a status; 'not sure' is a status, never a raw error.

    Idempotent: send an `Idempotency-Key` header (a fresh UUID per queued upload, kept on every retry). A replay by the same
    farmer returns the stored scan (same ids, 200, header `Idempotent-Replayed: true`) without analysing the photos again.

    Offline queue: send `taken_at` (when the photo was taken) and `offline=true`. Advice is always worked out when the server
    receives the photo (spray timing and weather are about now), the result carries both times. If the response was lost, the
    app can fetch the result with `GET /v1/scans/by-request/{key}` without sending the photos again.
    """
    service = ScanService(container, db)
    with serialised("scan", farmer.id, request_key):
        replay = service.find_by_request_id(farmer, request_key)
        if replay is not None:                                   # a retry: no rate-limit hit, no upload processing, no models
            response.headers[REPLAY_HEADER] = "true"
            return replay
        enforce(limiters.scan_farmer, farmer.id)
        crop, confidence = _client_crop(client_crop), _unit_interval(client_confidence)
        taken, (latitude, longitude) = _taken_at(taken_at), _location(lat, lon)
        images = process_uploads(photos, container.settings)
        return service.create(farmer, images, client_crop=crop, client_confidence=confidence, taken_at=taken, lat=latitude,
                              lon=longitude, client_request_id=request_key, offline=offline)


@router.post("/{scan_id}/photos", response_model=ScanOut, responses={**_SCAN_ERRORS, 404: {"model": ErrorOut}})
def add_photos(scan_id: str, photos: list[UploadFile] = File(...), farmer: FarmerProfile = Depends(get_current_farmer),
               db: Session = Depends(get_db), container: Container = Depends(get_container),
               limiters: RateLimiters = Depends(get_limiters)) -> ScanOut:
    """'Add more photos' step: re-evaluates the scan with all photos."""
    enforce(limiters.scan_farmer, farmer.id)
    service = ScanService(container, db)
    images = process_uploads(photos, container.settings, already_stored=service.photo_count(farmer, scan_id))
    return service.add_photos(farmer, scan_id, images)


@router.post("/{scan_id}/crop", response_model=ScanOut,
             responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 429: {"model": ErrorOut}, 503: {"model": ErrorOut}})
def confirm_crop(scan_id: str, body: CropConfirmIn, farmer: FarmerProfile = Depends(get_current_farmer),
                 db: Session = Depends(get_db), container: Container = Depends(get_container),
                 limiters: RateLimiters = Depends(get_limiters)) -> ScanOut:
    """Farmer ticks or corrects the detected crop; the pipeline continues with that crop."""
    enforce(limiters.scan_farmer, farmer.id)
    return ScanService(container, db).confirm_crop(farmer, scan_id, body.crop_id)


@router.get("/by-request/{request_key}", response_model=ScanOut, responses={404: {"model": ErrorOut}})
def get_scan_by_request(request_key: str, farmer: FarmerProfile = Depends(get_current_farmer), db: Session = Depends(get_db),
                        container: Container = Depends(get_container)) -> ScanOut:
    """The stored result of the scan this farmer uploaded with this Idempotency-Key (404 `scan_not_found`: it never arrived).

    For the offline queue: the upload reached the server but the response was lost, so the app does not know the scan id.
    Asking here is free (no photos, no analysis); sending the same upload again returns the same scan too."""
    if not KEY_RE.match(request_key):
        raise ApiError(404, "scan_not_found", "That scan was not found.")
    stored = ScanService(container, db).find_by_request_id(farmer, request_key)
    if stored is None:
        raise ApiError(404, "scan_not_found", "That scan was not found.")
    return stored


@router.get("/{scan_id}", response_model=ScanOut, responses={404: {"model": ErrorOut}})
def get_scan(scan_id: str, farmer: FarmerProfile = Depends(get_current_farmer), db: Session = Depends(get_db),
             container: Container = Depends(get_container)) -> ScanOut:
    """The stored result, exactly as it was returned when the scan was evaluated."""
    return ScanService(container, db).get(farmer, scan_id)


@router.get("", response_model=ScanListOut)
def list_scans(limit: int = 20, cursor: str | None = None, farmer: FarmerProfile = Depends(get_current_farmer),
               db: Session = Depends(get_db), container: Container = Depends(get_container)) -> ScanListOut:
    return ScanService(container, db).list_scans(farmer, limit, cursor)
