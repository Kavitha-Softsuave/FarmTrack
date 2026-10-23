"""Database logic behind the admin API and the admin pages (one implementation, two front ends)."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.clock_store import apply_demo_clock, save_demo_clock
from app.admin.models import AdminAlertOut, AuditOut, ExpertRequestAdminOut, FarmerCreateIn, FarmerLoginIn
from app.api.schemas import (
    DemoClockOut,
    DiseaseCandidateOut,
    FarmerAdminOut,
    ProductAdminOut,
    ProductAdminPatch,
    ReviewResolveIn,
    ReviewTaskOut,
)
from app.clock import Clock
from app.db.models import (
    AlertRow,
    AuditLogRow,
    ExpertRequestRow,
    FarmerRow,
    ProductOverrideRow,
    RefreshTokenRow,
    ReviewTaskRow,
    ScanRow,
    as_ist,
)
from app.domain.types import LocalizedText, Severity
from app.integrations.reference import load_disease_options, load_product_master
from app.security.passwords import hash_password

log = logging.getLogger(__name__)

ReleaseHook = Callable[[Session, ReviewTaskRow, ReviewResolveIn], bool]
REVIEW_STATUSES = ("open", "resolved", "all")


def clamp(limit: int, maximum: int = 200) -> int:
    return max(1, min(limit, maximum))


def write_audit(session: Session, action: str, entity: str | None = None, entity_id: str | None = None,
                detail: dict[str, Any] | None = None, actor: str = "admin") -> None:
    session.add(AuditLogRow(at=datetime.now(UTC), actor=actor, action=action, entity=entity, entity_id=entity_id, detail=detail or {}))


def _aware(value: datetime) -> datetime:
    """A stored timestamp as an IST-aware datetime (SQLite drops the offset)."""
    converted = as_ist(value)
    assert converted is not None  # noqa: S101
    return converted


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


# ------------------------------------------------------------------------------------------------- review queue
def list_review_tasks(session: Session, status: str, limit: int, photo_base: str) -> list[ReviewTaskOut]:
    if status not in REVIEW_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(REVIEW_STATUSES)}")
    query = select(ReviewTaskRow)
    if status != "all":
        query = query.where(ReviewTaskRow.status == status)
    oldest_first = status == "open"                       # the open queue is worked first-in first-out
    query = query.order_by(ReviewTaskRow.created_at.asc() if oldest_first else ReviewTaskRow.created_at.desc()).limit(clamp(limit))
    tasks = list(session.scalars(query).all())
    scans = {s.id: s for s in session.scalars(select(ScanRow).where(ScanRow.id.in_([t.scan_id for t in tasks]))).all()}
    names = dict(session.execute(select(FarmerRow.id, FarmerRow.name).where(FarmerRow.id.in_([t.farmer_id for t in tasks]))).all())
    return [_task_out(t, scans.get(t.scan_id), names.get(t.farmer_id), photo_base) for t in tasks]


def _ist(value: datetime) -> datetime:
    """`as_ist` for a column that is never NULL."""
    converted = as_ist(value)
    assert converted is not None  # noqa: S101
    return converted


def _task_out(task: ReviewTaskRow, scan: ScanRow | None, farmer_name: str | None, photo_base: str) -> ReviewTaskOut:
    candidates: list[DiseaseCandidateOut] = []
    for raw in ((scan.result or {}).get("disease") or {}).get("candidates", []) if scan else []:
        try:
            candidates.append(DiseaseCandidateOut.model_validate(raw))
        except ValidationError:
            continue
    resolution = task.resolution or {}
    return ReviewTaskOut(
        id=task.id, scan_id=task.scan_id, status="resolved" if task.status == "resolved" else "open",
        created_at=_ist(task.created_at), farmer_id=task.farmer_id, farmer_name=farmer_name,
        crop_guess=scan.crop_id if scan else None, disease_candidates=candidates, reason=task.reason or "",
        photo_urls=[f"{photo_base}/{task.scan_id}/{i}" for i in range(len(scan.photo_paths or []))] if scan else [],
        resolution_note=resolution.get("note"),
    )


def get_review_task(session: Session, task_id: str, photo_base: str) -> ReviewTaskOut:
    task = session.get(ReviewTaskRow, task_id)
    if task is None:
        raise HTTPException(404, "review task not found")
    scan = session.get(ScanRow, task.scan_id)
    farmer = session.get(FarmerRow, task.farmer_id)
    return _task_out(task, scan, farmer.name if farmer else None, photo_base)


def resolve_review_task(session: Session, task_id: str, body: ReviewResolveIn, now: datetime, data_dir: Path,
                        release_hook: ReleaseHook | None, photo_base: str) -> ReviewTaskOut:
    task = session.get(ReviewTaskRow, task_id)
    if task is None:
        raise HTTPException(404, "review task not found")
    if task.status == "resolved":
        raise HTTPException(409, "review task already resolved")
    if body.confirmed_disease and body.confirmed_disease not in {d for d, _ in load_disease_options(data_dir)}:
        raise HTTPException(422, "confirmed_disease is not in the disease catalogue")
    if body.release_advice and not (body.confirmed_disease or body.confirmed_crop):
        raise HTTPException(422, "release_advice needs a confirmed disease or crop")
    resolution: dict[str, Any] = {"confirmed_crop": body.confirmed_crop or None, "confirmed_disease": body.confirmed_disease or None,
                                  "note": body.note or None, "release_advice": body.release_advice}
    if body.release_advice:
        if release_hook is None:
            resolution["release_status"] = "not_configured"
        else:
            try:
                released = bool(release_hook(session, task, body))
            except Exception:
                log.exception("release of advice failed for review task %s", task_id)
                released = False
            if not released:
                session.rollback()
                raise HTTPException(502, "the advice could not be released; the task stays open")
            resolution["release_status"] = "released"
    task.status = "resolved"
    task.resolved_at = now
    task.resolution = resolution
    _close_requests_of_scan(session, task, body.note, now)
    write_audit(session, "review.resolve", "review_task", task.id,
                {"confirmed_disease": resolution["confirmed_disease"], "confirmed_crop": resolution["confirmed_crop"],
                 "release_advice": body.release_advice})
    session.commit()
    return get_review_task(session, task_id, photo_base)


def _close_requests_of_scan(session: Session, task: ReviewTaskRow, note: str | None, now: datetime) -> None:
    """The farmer asked an expert about this scan and the review task is now done: the request is answered too."""
    for request in session.scalars(select(ExpertRequestRow).where(ExpertRequestRow.scan_id == task.scan_id,
                                                                  ExpertRequestRow.status == "open")).all():
        request.status, request.resolved_at = "resolved", now
        request.resolution = {"note": note or None, "via": "review_task", "review_task_id": task.id}


# ------------------------------------------------------------------------------------------------- expert requests (with or without a scan)
def list_expert_requests(session: Session, status: str, limit: int) -> list[ExpertRequestAdminOut]:
    if status not in REVIEW_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(REVIEW_STATUSES)}")
    query = select(ExpertRequestRow)
    if status != "all":
        query = query.where(ExpertRequestRow.status == status)
    oldest_first = status == "open"                       # first in, first out, like the review queue
    if oldest_first:
        query = query.order_by(ExpertRequestRow.created_at.asc(), ExpertRequestRow.id.asc())
    else:
        query = query.order_by(ExpertRequestRow.created_at.desc(), ExpertRequestRow.id.desc())
    return _expert_out(session, list(session.scalars(query.limit(clamp(limit))).all()))


def _expert_out(session: Session, requests: list[ExpertRequestRow]) -> list[ExpertRequestAdminOut]:
    scan_ids = [r.scan_id for r in requests if r.scan_id]
    farmers = {f.id: f for f in session.scalars(select(FarmerRow).where(FarmerRow.id.in_([r.farmer_id for r in requests]))).all()}
    scan_crops: dict[str, str | None] = {}
    tasks: dict[str, str] = {}
    if scan_ids:
        scan_crops = dict(session.execute(select(ScanRow.id, ScanRow.crop_id).where(ScanRow.id.in_(scan_ids))).all())
        tasks = dict(session.execute(select(ReviewTaskRow.scan_id, ReviewTaskRow.id)
                                     .where(ReviewTaskRow.scan_id.in_(scan_ids), ReviewTaskRow.status == "open")).all())
    out: list[ExpertRequestAdminOut] = []
    for r in requests:
        farmer = farmers.get(r.farmer_id)
        out.append(ExpertRequestAdminOut(
            id=r.id, status="resolved" if r.status == "resolved" else "open", created_at=_aware(r.created_at), farmer_id=r.farmer_id,
            farmer_name=farmer.name if farmer else None,
            crop=r.crop_id or (scan_crops.get(r.scan_id) if r.scan_id else None) or (farmer.primary_crop if farmer else None),
            message=r.message, scan_id=r.scan_id, review_task_id=tasks.get(r.scan_id) if r.scan_id else None,
            resolved_at=as_ist(r.resolved_at), resolution_note=(r.resolution or {}).get("note")))
    return out


def resolve_expert_request(session: Session, request_id: str, note: str | None, now: datetime) -> ExpertRequestAdminOut:
    request = session.get(ExpertRequestRow, request_id)
    if request is None:
        raise HTTPException(404, "expert request not found")
    if request.status == "resolved":
        raise HTTPException(409, "expert request already closed")
    cleaned = (note or "").strip() or None
    request.status, request.resolved_at = "resolved", now
    request.resolution = {"note": cleaned, "via": "admin"}
    write_audit(session, "expert_request.resolve", "expert_request", request.id, {"has_note": cleaned is not None})
    session.commit()
    return _expert_out(session, [request])[0]


# ------------------------------------------------------------------------------------------------- demo clock
def clock_out(clock: Clock) -> DemoClockOut:
    return DemoClockOut(now=clock.now(), fixed=clock.is_fixed)


def set_demo_clock(session: Session, clock: Clock, value: datetime | None, allow_fixed: bool = True) -> DemoClockOut:
    """`allow_fixed` False (production) only accepts 'back to the real clock': a frozen date would mislead every farmer."""
    if value is not None and not allow_fixed:
        raise HTTPException(409, "the demo clock cannot be fixed in production (ALLOW_DEMO_CLOCK_IN_PROD=1 changes that)")
    save_demo_clock(session, value)
    apply_demo_clock(clock, value)
    write_audit(session, "clock.set", "demo_clock", None, {"now": clock.now().isoformat() if value else None})
    session.commit()
    return clock_out(clock)


# ------------------------------------------------------------------------------------------------- products
def _overrides(session: Session) -> dict[str, ProductOverrideRow]:
    return {o.product_id: o for o in session.scalars(select(ProductOverrideRow)).all()}


def _product_out(product: Any, override: ProductOverrideRow | None) -> ProductAdminOut:
    return ProductAdminOut(
        product_id=product.product_id, crop=product.crop, active_ingredient=product.active_ingredient, stage=product.stage,
        targets=list(product.targets), dose_text=product.dose_text, waiting_period_days=product.waiting_period_days,
        ban_status=product.ban_status, enabled=override.enabled if override else True,
    )


def list_products(session: Session, data_dir: Path, crop: str | None) -> list[ProductAdminOut]:
    overrides = _overrides(session)
    wanted = crop.strip().lower() if crop else None
    return [_product_out(p, overrides.get(p.product_id)) for p in load_product_master(data_dir).values()
            if wanted is None or p.crop.lower() == wanted]


def product_notes(session: Session) -> dict[str, str]:
    return {pid: o.note for pid, o in _overrides(session).items() if o.note}


def patch_product(session: Session, data_dir: Path, product_id: str, body: ProductAdminPatch, now: datetime) -> ProductAdminOut:
    product = load_product_master(data_dir).get(product_id)
    if product is None:
        raise HTTPException(404, "product not found")
    row = session.get(ProductOverrideRow, product_id)
    if row is None:
        row = ProductOverrideRow(product_id=product_id, enabled=body.enabled, note=body.note, updated_at=now)
        session.add(row)
    else:
        row.enabled, row.updated_at = body.enabled, now
        if body.note is not None:
            row.note = body.note
    write_audit(session, "product.enable" if body.enabled else "product.disable", "product", product_id, {"note": body.note})
    session.commit()
    return _product_out(product, row)


# ------------------------------------------------------------------------------------------------- farmers, alerts, audit
USERNAME_TAKEN = "that username is already used by another farmer"
PHONE_TAKEN = "that phone number already belongs to another farmer"


def _farmer_out(f: FarmerRow, last_scan: datetime | None) -> FarmerAdminOut:
    return FarmerAdminOut(id=f.id, name=f.name, district=f.district, village=f.village, primary_crop=f.primary_crop,
                          language="en" if f.language == "en" else "hi", last_scan_at=as_ist(last_scan), username=f.username,
                          has_login=bool(f.username and f.password_hash))


def _last_scan(session: Session, farmer_id: str) -> datetime | None:
    return session.scalar(select(func.max(ScanRow.created_at)).where(ScanRow.farmer_id == farmer_id))


def list_farmers(session: Session, limit: int) -> list[FarmerAdminOut]:
    last_scan = dict(session.execute(select(ScanRow.farmer_id, func.max(ScanRow.created_at)).group_by(ScanRow.farmer_id)).all())
    rows = session.scalars(select(FarmerRow).order_by(FarmerRow.id).limit(clamp(limit, 500))).all()
    return [_farmer_out(f, last_scan.get(f.id)) for f in rows]


def _username_owner(session: Session, username: str) -> str | None:
    return session.scalar(select(FarmerRow.id).where(FarmerRow.username == username))


def set_farmer_login(session: Session, farmer_id: str, body: FarmerLoginIn) -> FarmerAdminOut:
    """Give a farmer a username and a new password. The farmer's old sessions end (a reset usually means a lost phone).
    The audit entry names the username, never the password."""
    farmer = session.get(FarmerRow, farmer_id)
    if farmer is None:
        raise HTTPException(404, "farmer not found")
    owner = _username_owner(session, body.username)
    if owner is not None and owner != farmer.id:
        raise HTTPException(409, USERNAME_TAKEN)
    farmer.username, farmer.password_hash = body.username, hash_password(body.password)
    revoked = session.execute(update(RefreshTokenRow).where(RefreshTokenRow.farmer_id == farmer.id,
                                                            RefreshTokenRow.revoked.is_(False)).values(revoked=True)).rowcount
    write_audit(session, "farmer.set_login", "farmer", farmer.id, {"username": body.username, "sessions_ended": revoked})
    try:
        session.commit()
    except IntegrityError:                                         # another admin took the name between the check and the save
        session.rollback()
        raise HTTPException(409, USERNAME_TAKEN) from None
    return _farmer_out(farmer, _last_scan(session, farmer.id))


def _next_farmer_id(session: Session) -> str:
    numbers = [int(m.group(1)) for fid in session.scalars(select(FarmerRow.id)).all() if (m := re.fullmatch(r"F(\d+)", fid))]
    return f"F{max(numbers, default=0) + 1:03d}"


def create_farmer(session: Session, body: FarmerCreateIn, now: datetime) -> FarmerAdminOut:
    """Add a farmer with a login (ids are F051, F052 ... after the existing ones). 409 for a taken username or phone number."""
    if _username_owner(session, body.username) is not None:
        raise HTTPException(409, USERNAME_TAKEN)
    if session.scalar(select(FarmerRow.id).where(FarmerRow.phone == body.phone)) is not None:
        raise HTTPException(409, PHONE_TAKEN)
    crops = list(dict.fromkeys([body.primary_crop, *body.other_crops]))
    password_hash = hash_password(body.password)
    for _attempt in range(3):                                      # the id comes from a count: retry when two admins collide
        farmer = FarmerRow(id=_next_farmer_id(session), name=body.name, phone=body.phone, username=body.username,
                           password_hash=password_hash, language=body.language, district=body.district, village=body.village,
                           elevation_m=body.elevation_m, phenology_band=body.phenology_band, crops=crops,
                           primary_crop=body.primary_crop, created_at=now)
        session.add(farmer)
        write_audit(session, "farmer.create", "farmer", farmer.id, {"username": body.username, "language": body.language})
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if _username_owner(session, body.username) is not None:
                raise HTTPException(409, USERNAME_TAKEN) from None
            if session.scalar(select(FarmerRow.id).where(FarmerRow.phone == body.phone)) is not None:
                raise HTTPException(409, PHONE_TAKEN) from None
            continue
        return _farmer_out(farmer, None)
    raise HTTPException(409, "the farmer could not be saved; please try again")


def alert_out(row: AlertRow) -> AdminAlertOut:
    return AdminAlertOut(
        id=row.id, farmer_id=row.farmer_id, kind=row.kind, level=Severity(row.level),
        title=LocalizedText.model_validate(row.title or {}), body=LocalizedText.model_validate(row.body or {}),
        dedupe_key=row.dedupe_key, created_at=_ist(row.created_at), pushed_at=as_ist(row.pushed_at), read_at=as_ist(row.read_at),
    )


def list_alerts(session: Session, limit: int, farmer_id: str | None = None) -> list[AdminAlertOut]:
    query = select(AlertRow).order_by(AlertRow.created_at.desc(), AlertRow.id).limit(clamp(limit))
    if farmer_id:
        query = query.where(AlertRow.farmer_id == farmer_id)
    return [alert_out(r) for r in session.scalars(query).all()]


def list_audit(session: Session, limit: int) -> list[AuditOut]:
    rows = session.scalars(select(AuditLogRow).order_by(AuditLogRow.at.desc(), AuditLogRow.id).limit(clamp(limit))).all()
    return [AuditOut(id=r.id, at=_utc(r.at), actor=r.actor, action=r.action, entity=r.entity, entity_id=r.entity_id,
                     detail=r.detail or {}) for r in rows]


def dashboard_counts(session: Session) -> dict[str, int]:
    def count(model: Any, *where: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model).where(*where)) or 0)

    return {
        "open_reviews": count(ReviewTaskRow, ReviewTaskRow.status == "open"),
        "open_expert_requests": count(ExpertRequestRow, ExpertRequestRow.status == "open"),
        "farmers": count(FarmerRow),
        "alerts": count(AlertRow),
        "unpushed_alerts": count(AlertRow, AlertRow.pushed_at.is_(None)),
        "disabled_products": count(ProductOverrideRow, ProductOverrideRow.enabled.is_(False)),
    }


def photo_file(session: Session, storage_dir: Path, scan_id: str, index: int) -> Path | None:
    """Resolved path of a scan photo inside storage_dir, or None when it does not exist or would escape the directory."""
    scan = session.get(ScanRow, scan_id)
    paths = (scan.photo_paths if scan else None) or []
    if index < 0 or index >= len(paths):
        return None
    try:
        base = storage_dir.resolve()
        candidate = (base / str(paths[index])).resolve()
    except (OSError, ValueError):
        return None
    if base not in candidate.parents or not candidate.is_file():
        return None
    return candidate
