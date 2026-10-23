"""Hook behind the admin 'send the advice to the farmer' button (app.state.release_advice).

The agronomist confirms a crop and/or disease; the rules run again on that confirmation. Only when the rules produce advice is the
scan result replaced and the farmer notified, otherwise the hook returns False and the review task stays open.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ReviewResolveIn
from app.db.models import AlertRow, DeviceRow, FarmerRow, ReviewTaskRow, ScanRow, new_id
from app.db.repo import farmer_profile
from app.domain.types import LocalizedText
from app.services.catalogue import load_catalogue
from app.services.container import Container
from app.services.scan_service import ScanService
from app.services.speech import speak

logger = logging.getLogger(__name__)

TITLE = LocalizedText(en="Advice from a farm expert is ready", hi="खेती के जानकार की सलाह आ गई है")
BODY = LocalizedText(en="A farm expert has seen your photo. Open your scan to hear the advice.",
                     hi="खेती के जानकार ने आपकी फोटो देख ली है। सलाह सुनने के लिए अपना स्कैन खोलिए।")


def release_advice(container: Container, db: Session, task: ReviewTaskRow, body: ReviewResolveIn) -> bool:
    scan = db.get(ScanRow, task.scan_id)
    farmer_row = db.get(FarmerRow, task.farmer_id)
    if scan is None or farmer_row is None:
        return False
    catalogue = load_catalogue(str(container.settings.data_dir))
    crop_id = (catalogue.canonical_crop(body.confirmed_crop) if body.confirmed_crop else None) or scan.crop_id
    if crop_id is None:
        return False
    farmer = farmer_profile(farmer_row)
    result = ScanService(container, db).release_expert_result(
        farmer, scan, crop_id, body.confirmed_disease or scan.disease_id, disease_confirmed=bool(body.confirmed_disease))
    if result is None:
        return False
    _notify(container, db, farmer_row, scan.id, task.id)
    return True


def _notify(container: Container, db: Session, farmer: FarmerRow, scan_id: str, task_id: str) -> None:
    """In-app alert plus a best-effort push. Failures only log: the stored scan result is already updated."""
    now = container.clock.now()
    try:
        db.add(AlertRow(id=new_id(), farmer_id=farmer.id, kind="expert_advice", level="green", dedupe_key=f"expert:{task_id}",
                        title=TITLE.model_dump(), body=BODY.model_dump(),
                        spoken=speak(container.audio, BODY).model_dump(mode="json"), payload={"scan_id": scan_id}, created_at=now))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("expert-advice alert could not be stored scan=%s", scan_id)
    language = "en" if farmer.language == "en" else "hi"
    for token in db.scalars(select(DeviceRow.push_token).where(DeviceRow.farmer_id == farmer.id)).all():
        try:
            container.push.send(token, TITLE.get(language), BODY.get(language), {"kind": "expert_advice", "scan_id": scan_id})
        except Exception:
            logger.warning("push failed for expert advice scan=%s", scan_id)
