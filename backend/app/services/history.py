"""Spray history seen by the rules: Zoho records merged with the sprays the farmer logged in this app.

Uses the integrations package's merge helpers so the scan pipeline and the alert evaluator see exactly the same history.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SprayLogRow
from app.domain.types import FarmerProfile, SprayRecord
from app.integrations.history import merge_history, records_from_spray_logs
from app.integrations.reference import load_product_master
from app.services.container import Container

logger = logging.getLogger(__name__)


def merged_history(container: Container, db: Session, farmer: FarmerProfile, now: datetime) -> tuple[list[SprayRecord], bool]:
    """Return (records oldest first, zoho_ok). A diary entry that already synced to Zoho is counted once.

    zoho_ok is False when Zoho could not be read: the caller must warn the farmer that the history is incomplete.
    """
    try:
        zoho_records = list(container.zoho.get_history(farmer.id, until=now))
        zoho_ok = True
    except Exception:
        logger.exception("zoho history unavailable farmer=%s", farmer.id)
        zoho_records, zoho_ok = [], False
    rows = db.scalars(select(SprayLogRow).where(SprayLogRow.farmer_id == farmer.id, SprayLogRow.sprayed_at <= now)
                      .order_by(SprayLogRow.sprayed_at))
    own = records_from_spray_logs(rows, load_product_master(container.settings.data_dir), until=now)
    return merge_history(zoho_records, own), zoho_ok
