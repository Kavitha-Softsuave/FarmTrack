"""SQLAlchemy 2.0 models. Additive changes only by agents (new columns need a note + migration).

Time convention: domain timestamps (scan created_at, sprayed_at, alert created_at) come from app.clock.get_clock().now() so the demo clock
drives everything; they are stored timezone-aware. Audit rows use real UTC time. SQLite drops tzinfo: always re-attach IST when reading
(helper: app.db.models.as_ist).
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

IST = ZoneInfo("Asia/Kolkata")


def new_id() -> str:
    return uuid4().hex


def as_ist(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)


class Base(DeclarativeBase):
    pass


class FarmerRow(Base):
    __tablename__ = "farmers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)            # demo: F001..F050 (from data/farmers.csv)
    zoho_contact_id: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # contact + expert phone call (not the login)
    username: Mapped[str | None] = mapped_column(String(40), unique=True, index=True)   # login name, lower case (NULL = cannot log in)
    password_hash: Mapped[str | None] = mapped_column(String(255))           # app.security.passwords format; never the password
    language: Mapped[str] = mapped_column(String(2), default="hi")
    district: Mapped[str | None] = mapped_column(String(60))
    village: Mapped[str | None] = mapped_column(String(60))
    station_id: Mapped[str | None] = mapped_column(String(10))
    elevation_m: Mapped[float | None] = mapped_column(Float)
    phenology_band: Mapped[str | None] = mapped_column(String(4))
    crops: Mapped[list] = mapped_column(JSON, default=list)
    primary_crop: Mapped[str | None] = mapped_column(String(40))
    primary_variety: Mapped[str | None] = mapped_column(String(60))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OtpRequestRow(Base):
    __tablename__ = "otp_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    otp_hash: Mapped[str] = mapped_column(String(128))                        # never store the code in clear
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshTokenRow(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    device_id: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class DeviceRow(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    platform: Mapped[str] = mapped_column(String(10))
    push_token: Mapped[str] = mapped_column(String(4096), unique=True)
    app_version: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScanRow(Base):
    __tablename__ = "scans"
    # Idempotency-Key of the upload (mobile offline queue): one scan per (farmer, key). NULLs never collide.
    __table_args__ = (Index("uq_scans_farmer_request", "farmer_id", "client_request_id", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(24))
    crop_id: Mapped[str | None] = mapped_column(String(40))
    crop_confidence: Mapped[float | None] = mapped_column(Float)
    crop_source: Mapped[str | None] = mapped_column(String(24))
    crop_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    disease_id: Mapped[str | None] = mapped_column(String(80))
    disease_confidence: Mapped[float | None] = mapped_column(Float)
    route: Mapped[str | None] = mapped_column(String(16))
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)                  # cached ScanOut payload (Pydantic JSON)
    photo_paths: Mapped[list] = mapped_column(JSON, default=list)             # relative to settings.storage_dir
    client_crop: Mapped[str | None] = mapped_column(String(40))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    client_request_id: Mapped[str | None] = mapped_column(String(80))


class AdviceRow(Base):
    __tablename__ = "advice"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    crop_id: Mapped[str] = mapped_column(String(40))
    disease_id: Mapped[str | None] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(8))
    payload: Mapped[dict] = mapped_column(JSON)                                # AdviceOut JSON
    rule_trace: Mapped[list] = mapped_column(JSON, default=list)               # audit: why these products
    validated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SprayLogRow(Base):
    __tablename__ = "spray_logs"
    __table_args__ = (Index("uq_spray_logs_farmer_request", "farmer_id", "client_request_id", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    crop_id: Mapped[str] = mapped_column(String(40))
    advice_id: Mapped[str | None] = mapped_column(String(32))
    product_id: Mapped[str | None] = mapped_column(String(10))
    product_name: Mapped[str | None] = mapped_column(String(120))
    free_text: Mapped[str | None] = mapped_column(String(200))
    sprayed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str | None] = mapped_column(String(300))
    synced_to_zoho: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    client_request_id: Mapped[str | None] = mapped_column(String(80))


class AlertRow(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("farmer_id", "dedupe_key", name="uq_alert_dedupe"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    level: Mapped[str] = mapped_column(String(8))
    dedupe_key: Mapped[str] = mapped_column(String(120))                       # one alert per episode, e.g. 'scab:ST05:2026-05-04'
    title: Mapped[dict] = mapped_column(JSON)                                  # LocalizedText JSON
    body: Mapped[dict] = mapped_column(JSON)
    spoken: Mapped[dict] = mapped_column(JSON, default=dict)                   # SpokenOut JSON
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewTaskRow(Base):
    __tablename__ = "review_tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[dict | None] = mapped_column(JSON)


class ExpertRequestRow(Base):
    """'Ask a farm expert'. With a scan the request also opens a ReviewTask; without one the admin lists the row itself."""
    __tablename__ = "expert_requests"
    __table_args__ = (Index("uq_expert_requests_farmer_request", "farmer_id", "client_request_id", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    farmer_id: Mapped[str] = mapped_column(ForeignKey("farmers.id"), index=True)
    scan_id: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), default="open")            # open | resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    client_request_id: Mapped[str | None] = mapped_column(String(80))
    crop_id: Mapped[str | None] = mapped_column(String(40))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[dict | None] = mapped_column(JSON)                      # {"note": ..., "via": "admin" | "review_task"}


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor: Mapped[str] = mapped_column(String(40))                             # farmer id | admin | system
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class AppSettingRow(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class ProductOverrideRow(Base):
    """Admin switch: disable a product in the approved list without a deploy."""
    __tablename__ = "product_overrides"
    product_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
