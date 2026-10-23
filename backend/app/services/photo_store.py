"""Scan photo files under storage_dir/photos/<farmer_id>/<scan_id>/. Names are server-generated; paths are always checked."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ScanRow
from app.security.paths import UnsafePathError, safe_join

logger = logging.getLogger(__name__)


class PhotoStore:
    def __init__(self, storage_dir: Path) -> None:
        self.root = storage_dir

    def save(self, farmer_id: str, scan_id: str, data: bytes) -> str:
        """Write one cleaned JPEG and return its path relative to the storage directory (posix separators)."""
        relative = f"photos/{farmer_id}/{scan_id}/{secrets.token_hex(8)}.jpg"
        target = safe_join(self.root, *relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return relative

    def load(self, relative: str) -> bytes | None:
        try:
            path = safe_join(self.root, *relative.split("/"))
            return path.read_bytes()
        except (UnsafePathError, OSError):
            logger.warning("photo file not readable: %s", relative.rsplit("/", 1)[-1])
            return None

    def delete(self, relatives: list[str]) -> None:
        for relative in relatives:
            try:
                safe_join(self.root, *relative.split("/")).unlink(missing_ok=True)
            except (UnsafePathError, OSError):
                logger.warning("photo file not deletable: %s", relative.rsplit("/", 1)[-1])

    def purge_expired(self, db: Session, now: datetime, retention_days: int) -> int:
        """Delete photo files of scans older than the retention period (privacy). The scan result stays. Returns scans purged.

        Not scheduled by the platform itself: the integrations scheduler (or an ops cron) should call it daily.
        """
        cutoff = now - timedelta(days=retention_days)
        purged = 0
        for scan in db.scalars(select(ScanRow).where(ScanRow.created_at < cutoff)):
            if scan.photo_paths:
                self.delete(list(scan.photo_paths))
                scan.photo_paths = []
                purged += 1
        db.commit()
        return purged
