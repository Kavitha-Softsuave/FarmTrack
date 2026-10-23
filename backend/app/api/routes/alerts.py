from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_farmer, get_db
from app.api.schemas import AlertListOut, AlertOut, ErrorOut, SpokenOut
from app.db.models import AlertRow, as_ist
from app.domain.types import FarmerProfile, LocalizedText, Severity
from app.security.errors import ApiError
from app.services.container import Container

router = APIRouter(prefix="/v1/alerts", tags=["alerts"], responses={401: {"model": ErrorOut}})


def _alert_out(row: AlertRow) -> AlertOut:
    title, body = LocalizedText.model_validate(row.title), LocalizedText.model_validate(row.body)
    try:
        spoken = SpokenOut.model_validate(row.spoken)
    except ValueError:
        spoken = SpokenOut(text=body, audio={})              # the scheduler stores the audio; text is always available
    created, read = as_ist(row.created_at), as_ist(row.read_at)
    assert created is not None  # noqa: S101
    return AlertOut(id=row.id, kind=row.kind, level=Severity(row.level), title=title, body=body, spoken=spoken, created_at=created,
                    read_at=read, scan_id=_scan_id(row))


def _scan_id(row: AlertRow) -> str | None:
    """The scan an alert is about (expert advice, a wash-off or waiting-period reminder for a spray taken from a scan's advice)."""
    value = (row.payload or {}).get("scan_id")
    return value if isinstance(value, str) and value else None


@router.get("", response_model=AlertListOut)
def list_alerts(limit: int = 30, farmer: FarmerProfile = Depends(get_current_farmer),
                db: Session = Depends(get_db)) -> AlertListOut:
    rows = db.scalars(select(AlertRow).where(AlertRow.farmer_id == farmer.id)
                      .order_by(AlertRow.created_at.desc(), AlertRow.id.desc()).limit(max(1, min(limit, 100))))
    unread = db.scalar(select(func.count()).select_from(AlertRow)
                       .where(AlertRow.farmer_id == farmer.id, AlertRow.read_at.is_(None))) or 0
    return AlertListOut(items=[_alert_out(r) for r in rows], unread=unread)


@router.post("/{alert_id}/read", response_model=AlertOut, responses={404: {"model": ErrorOut}})
def mark_read(alert_id: str, farmer: FarmerProfile = Depends(get_current_farmer), db: Session = Depends(get_db),
              container: Container = Depends(get_container)) -> AlertOut:
    row = db.get(AlertRow, alert_id)
    if row is None or row.farmer_id != farmer.id:
        raise ApiError(404, "alert_not_found", "That alert was not found.")
    if row.read_at is None:
        row.read_at = container.clock.now()
        db.commit()
    return _alert_out(row)
