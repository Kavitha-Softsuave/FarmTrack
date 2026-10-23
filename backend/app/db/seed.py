"""Load the demo farmers (data/farmers.csv) into an empty database. Runs at startup unless env == 'prod' and SEED_DEMO != '1'.

Demo logins: username = the farmer id in lower case (f001 ... f050), password = DEMO_PASSWORD. They exist only where the demo farmers
are loaded (dev/test, or SEED_DEMO=1), never in a normal production database."""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import FarmerRow
from app.db.session import session_scope
from app.security.passwords import hash_password
from app.security.phone import normalize_phone

logger = logging.getLogger(__name__)


def seed_enabled(settings: Settings) -> bool:
    return not settings.is_prod or os.environ.get("SEED_DEMO") == "1"


def _station_coordinates(data_dir: Path) -> dict[str, tuple[float, float]]:
    with (data_dir / "weather" / "stations.csv").open(encoding="utf-8-sig", newline="") as handle:
        return {r["station_id"]: (float(r["lat_approx"]), float(r["lon_approx"])) for r in csv.DictReader(handle)}


def _crops(row: dict[str, str]) -> list[str]:
    crops = [row["primary_crop"].strip()] + [c.strip() for c in (row.get("other_crops") or "").split(";")]
    return list(dict.fromkeys(c for c in crops if c))


def seed_farmers(session: Session, data_dir: Path, now: datetime, demo_password: str | None = None) -> int:
    """Insert every farmer of data/farmers.csv when the farmers table is empty. Returns how many were inserted.

    Every farmer gets the username `farmer id in lower case`; with `demo_password` they can log in with it."""
    if session.scalar(select(func.count()).select_from(FarmerRow)):
        return 0
    stations = _station_coordinates(data_dir)
    inserted = 0
    with (data_dir / "farmers.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            phone = normalize_phone(row["phone"])
            if phone is None:
                logger.warning("seed: skipping %s, invalid phone", row["farmer_id"])
                continue
            lat, lon = stations.get(row["station_id"], (None, None))
            session.add(FarmerRow(
                id=row["farmer_id"], zoho_contact_id=row.get("zoho_contact_id") or None, name=row["name"], phone=phone,
                language=row.get("preferred_language") if row.get("preferred_language") in ("hi", "en") else "hi",
                district=row.get("district") or None, village=row.get("village") or None, station_id=row.get("station_id") or None,
                elevation_m=float(row["orchard_elevation_m"]) if row.get("orchard_elevation_m") else None,
                username=row["farmer_id"].strip().lower(), password_hash=hash_password(demo_password) if demo_password else None,
                phenology_band=row.get("phenology_band") or None, crops=_crops(row), primary_crop=row["primary_crop"] or None,
                primary_variety=row.get("primary_variety") or None, lat=lat, lon=lon, created_at=now))
            inserted += 1
    session.commit()
    return inserted


def add_missing_demo_logins(session: Session, data_dir: Path, demo_password: str) -> int:
    """A dev database made before the password login existed has the demo farmers but no logins: give each demo farmer without a
    password its demo login (username = id in lower case). Never touches a farmer that already has a password, one that has another
    username, one outside the CSV, or a name that someone else already holds."""
    with (data_dir / "farmers.csv").open(encoding="utf-8-sig", newline="") as handle:
        demo_ids = {r["farmer_id"] for r in csv.DictReader(handle)}
    rows = session.scalars(select(FarmerRow).where(FarmerRow.id.in_(demo_ids), FarmerRow.password_hash.is_(None))).all()
    taken = set(session.scalars(select(FarmerRow.username).where(FarmerRow.username.is_not(None))).all())
    given = 0
    for farmer in rows:
        name = farmer.id.strip().lower()
        if farmer.username not in (None, name) or (farmer.username is None and name in taken):
            continue
        farmer.username, farmer.password_hash = name, hash_password(demo_password)
        given += 1
    session.commit()
    return given


def seed_if_enabled(settings: Settings, now: datetime) -> int:
    if not seed_enabled(settings):
        return 0
    password = settings.demo_password or None
    with session_scope() as session:
        count = seed_farmers(session, settings.data_dir, now, password)
        if not count and password:
            added = add_missing_demo_logins(session, settings.data_dir, password)
            if added:
                logger.info("gave %d existing demo farmers their demo login", added)
    if count:
        logger.info("seeded %d demo farmers", count)
    return count
