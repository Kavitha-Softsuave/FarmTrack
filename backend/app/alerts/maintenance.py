"""Housekeeping jobs run by the scheduler next to the alert evaluator: Zoho write retries and photo retention."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SprayLogRow
from app.integrations.history import records_from_spray_logs
from app.integrations.reference import load_product_master

if TYPE_CHECKING:
    from app.services.container import Container

log = logging.getLogger(__name__)

SYNC_BATCH = 100


def sync_unsynced_sprays(session: Session, container: Container, limit: int = SYNC_BATCH) -> int:
    """Retry the Zoho write for diary entries that could not be sent when the farmer ticked 'sprayed'. Returns entries synced."""
    rows = session.scalars(select(SprayLogRow).where(SprayLogRow.synced_to_zoho.is_(False))
                           .order_by(SprayLogRow.sprayed_at).limit(limit)).all()
    products = load_product_master(container.settings.data_dir)
    synced = 0
    for row in rows:
        records = records_from_spray_logs([row], products)
        if not records:
            continue
        try:
            ok = bool(container.zoho.write_spray(row.farmer_id, records[0]))
        except Exception as exc:
            log.warning("zoho retry failed for spray log %s: %s", row.id, type(exc).__name__)
            continue
        if ok:
            row.synced_to_zoho = True
            synced += 1
    session.commit()
    return synced


def purge_expired_photos(session: Session, container: Container) -> int:
    """Privacy: delete the photo files of scans older than settings.photo_retention_days (the scan result stays)."""
    from app.services.photo_store import PhotoStore

    settings = container.settings
    return PhotoStore(settings.storage_dir).purge_expired(session, container.clock.now(), settings.photo_retention_days)
