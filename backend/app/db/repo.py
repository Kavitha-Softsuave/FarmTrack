"""Small query helpers shared by routes and services."""
from __future__ import annotations

import secrets
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FarmerRow
from app.domain.types import FarmerProfile, Lang


def sortable_id() -> str:
    """32-hex opaque id that sorts by creation time (ms timestamp + randomness).

    The demo clock is frozen, so `created_at` ties are common; ids give a stable real-time order for lists and cursors.
    """
    return f"{int(time.time() * 1000):012x}{secrets.token_hex(10)}"


def farmer_profile(row: FarmerRow) -> FarmerProfile:
    language: Lang = "en" if row.language == "en" else "hi"
    return FarmerProfile(
        id=row.id, name=row.name, phone=row.phone, language=language, district=row.district, village=row.village,
        station_id=row.station_id, elevation_m=row.elevation_m, phenology_band=row.phenology_band,
        crops=list(row.crops or []), primary_crop=row.primary_crop, primary_variety=row.primary_variety,
        zoho_contact_id=row.zoho_contact_id, lat=row.lat, lon=row.lon,
    )


def get_farmer_row(db: Session, farmer_id: str) -> FarmerRow | None:
    return db.get(FarmerRow, farmer_id)


def get_farmer_by_phone(db: Session, phone: str) -> FarmerRow | None:
    return db.scalars(select(FarmerRow).where(FarmerRow.phone == phone)).first()


def get_farmer_by_username(db: Session, username: str) -> FarmerRow | None:
    """`username` must already be lower case (see app.security.passwords.normalize_username)."""
    return db.scalars(select(FarmerRow).where(FarmerRow.username == username)).first()
