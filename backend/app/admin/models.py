"""Response models for the admin routes that are not part of the frozen API schemas (alert log, run-now, audit trail)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.types import LocalizedText, Severity
from app.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    normalize_username,
    password_problem,
)
from app.security.phone import normalize_phone


class AdminAlertOut(BaseModel):
    id: str
    farmer_id: str
    kind: str
    level: Severity
    title: LocalizedText
    body: LocalizedText
    dedupe_key: str
    created_at: datetime
    pushed_at: datetime | None = None
    read_at: datetime | None = None


class ExpertRequestAdminOut(BaseModel):
    """A farmer's 'ask a farm expert' request. With a scan it is also a review task; without one this is the only place staff see it."""
    id: str
    status: Literal["open", "resolved"]
    created_at: datetime
    farmer_id: str
    farmer_name: str | None = None
    farmer_phone: str | None = None              # experts answer by phone call, so the queue shows the number to call
    crop: str | None = None                      # the request's crop, else the scan's crop, else the farmer's main crop
    message: str | None = None
    scan_id: str | None = None
    review_task_id: str | None = None            # the open review task of that scan, if any
    resolved_at: datetime | None = None
    resolution_note: str | None = None


class ExpertRequestResolveIn(BaseModel):
    note: str | None = Field(default=None, max_length=500, description="What was done or told to the farmer (staff record only)")


class RunNowOut(BaseModel):
    created: int
    alerts: list[AdminAlertOut] = Field(default_factory=list)


class AuditOut(BaseModel):
    id: str
    at: datetime
    actor: str
    action: str
    entity: str | None = None
    entity_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


def _clean_username(value: str) -> str:
    name = normalize_username(value)
    if name is None:
        raise ValueError("username must be 3-40 characters: a-z, 0-9, dot, underscore or hyphen")
    return name


def _clean_password(value: str) -> str:
    problem = password_problem(value)
    if problem:
        raise ValueError(problem)
    return value


class FarmerLoginIn(BaseModel):
    """Set (or reset) the login of a farmer. The username is stored in lower case; the password only as a hash."""
    username: str = Field(description="3-40 characters of a-z 0-9 . _ - (not case-sensitive)")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH, description="At least 6 characters")

    _username = field_validator("username")(_clean_username)
    _password = field_validator("password")(_clean_password)


class FarmerCreateIn(BaseModel):
    """The smallest useful farmer record. The phone is required: the database needs it (unique) and the experts call it."""
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(description="Contact number, e.g. +919876543210 (a bare 10-digit number is read as Indian)")
    language: Literal["hi", "en"] = "hi"
    district: str | None = Field(default=None, max_length=60)
    village: str | None = Field(default=None, max_length=60)
    primary_crop: str = Field(min_length=1, max_length=40)
    other_crops: list[str] = Field(default_factory=list, max_length=10)
    phenology_band: str | None = Field(default=None, max_length=4, description="Orchard band, e.g. B3")
    elevation_m: float | None = Field(default=None, ge=0, le=6000)
    username: str = Field(description="3-40 characters of a-z 0-9 . _ - (not case-sensitive)")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH, description="At least 6 characters")

    _username = field_validator("username")(_clean_username)
    _password = field_validator("password")(_clean_password)

    @field_validator("name", "primary_crop")
    @classmethod
    def _required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("district", "village", "phenology_band")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return (value or "").strip() or None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        phone = normalize_phone(value)
        if phone is None or len(phone) > 16:
            raise ValueError("not a valid phone number")
        return phone

    @field_validator("other_crops")
    @classmethod
    def _crops(cls, value: list[str]) -> list[str]:
        cleaned = [c.strip() for c in value if c.strip()]
        if any(len(c) > 40 for c in cleaned):
            raise ValueError("a crop name is at most 40 characters")
        return cleaned
