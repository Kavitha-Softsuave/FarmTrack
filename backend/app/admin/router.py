"""Admin API (X-Admin-Key) plus the server-rendered admin pages.

`router` is what app.main includes: it holds the JSON API under /admin/api/v1 (guarded by require_admin) and the HTML pages under
/admin (guarded by a signed cookie, see app.admin.pages). Handlers read the dependency container from `app.state.container` and
may call `app.state.release_advice(session, task, body) -> bool`, a hook the platform sets so that resolving a review task with
release_advice=true re-runs the rules with the confirmed disease and sends the advice to the farmer.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.admin import service
from app.admin.auth import settings_of
from app.admin.models import (
    AdminAlertOut,
    AuditOut,
    ExpertRequestAdminOut,
    ExpertRequestResolveIn,
    FarmerCreateIn,
    FarmerLoginIn,
    RunNowOut,
)
from app.admin.pages import container_of, photo_response
from app.admin.pages import router as pages_router
from app.alerts.evaluator import run_once
from app.api.deps import get_db, require_admin
from app.api.schemas import (
    DemoClockIn,
    DemoClockOut,
    FarmerAdminOut,
    ProductAdminOut,
    ProductAdminPatch,
    ReviewResolveIn,
    ReviewTaskOut,
)
from app.clock import get_clock

PHOTO_BASE = "/admin/api/v1/photos"

api_router = APIRouter(prefix="/admin/api/v1", tags=["admin"], dependencies=[Depends(require_admin)])


def _clock(request: Request):  # noqa: ANN202
    container = getattr(request.app.state, "container", None)
    return container.clock if container is not None else get_clock()


@api_router.get("/review-tasks", response_model=list[ReviewTaskOut])
def list_review_tasks(status: str = "open", limit: int = 50, db: Session = Depends(get_db)) -> list[ReviewTaskOut]:
    return service.list_review_tasks(db, status, limit, PHOTO_BASE)


@api_router.post("/review-tasks/{task_id}/resolve", response_model=ReviewTaskOut)
def resolve_review_task(task_id: str, body: ReviewResolveIn, request: Request, db: Session = Depends(get_db)) -> ReviewTaskOut:
    hook = getattr(request.app.state, "release_advice", None)
    return service.resolve_review_task(db, task_id, body, _clock(request).now(), settings_of(request).data_dir, hook, PHOTO_BASE)


@api_router.get("/expert-requests", response_model=list[ExpertRequestAdminOut])
def list_expert_requests(status: str = "open", limit: int = 50, db: Session = Depends(get_db)) -> list[ExpertRequestAdminOut]:
    """Farmers' 'ask a farm expert' requests, with or without a scan (a request without a scan is not a review task)."""
    return service.list_expert_requests(db, status, limit)


@api_router.post("/expert-requests/{request_id}/resolve", response_model=ExpertRequestAdminOut)
def resolve_expert_request(request_id: str, body: ExpertRequestResolveIn, request: Request,
                           db: Session = Depends(get_db)) -> ExpertRequestAdminOut:
    """Mark a request answered/closed, with an optional staff note (kept in the record; the farmer is not messaged)."""
    return service.resolve_expert_request(db, request_id, body.note, _clock(request).now())


@api_router.get("/photos/{scan_id}/{index}", include_in_schema=False)
def review_photo(scan_id: str, index: int, request: Request, db: Session = Depends(get_db)) -> FileResponse:
    return photo_response(request, db, scan_id, index)


@api_router.get("/settings/demo-clock", response_model=DemoClockOut)
def get_demo_clock(request: Request) -> DemoClockOut:
    return service.clock_out(_clock(request))


@api_router.put("/settings/demo-clock", response_model=DemoClockOut)
def set_demo_clock(body: DemoClockIn, request: Request, db: Session = Depends(get_db)) -> DemoClockOut:
    settings = settings_of(request)
    return service.set_demo_clock(db, _clock(request), body.now, allow_fixed=not settings.is_prod or settings.allow_demo_clock_in_prod)


@api_router.get("/products", response_model=list[ProductAdminOut])
def list_products(request: Request, crop: str | None = None, db: Session = Depends(get_db)) -> list[ProductAdminOut]:
    return service.list_products(db, settings_of(request).data_dir, crop)


@api_router.patch("/products/{product_id}", response_model=ProductAdminOut)
def patch_product(product_id: str, body: ProductAdminPatch, request: Request, db: Session = Depends(get_db)) -> ProductAdminOut:
    now: datetime = _clock(request).now()
    return service.patch_product(db, settings_of(request).data_dir, product_id, body, now)


@api_router.get("/farmers", response_model=list[FarmerAdminOut])
def list_farmers(limit: int = 100, db: Session = Depends(get_db)) -> list[FarmerAdminOut]:
    return service.list_farmers(db, limit)


@api_router.post("/farmers", response_model=FarmerAdminOut, status_code=201)
def create_farmer(body: FarmerCreateIn, request: Request, db: Session = Depends(get_db)) -> FarmerAdminOut:
    """Add a farmer with a username and password (409: the username or the phone number is already used)."""
    return service.create_farmer(db, body, _clock(request).now())


@api_router.post("/farmers/{farmer_id}/login", response_model=FarmerAdminOut)
def set_farmer_login(farmer_id: str, body: FarmerLoginIn, db: Session = Depends(get_db)) -> FarmerAdminOut:
    """Set or reset a farmer's username and password (409: username taken; the farmer's old sessions end)."""
    return service.set_farmer_login(db, farmer_id, body)


@api_router.get("/alerts", response_model=list[AdminAlertOut])
def list_alerts(limit: int = 100, farmer_id: str | None = None, db: Session = Depends(get_db)) -> list[AdminAlertOut]:
    return service.list_alerts(db, limit, farmer_id)


@api_router.post("/alerts/run-now", response_model=RunNowOut)
def run_alerts_now(request: Request, db: Session = Depends(get_db)) -> RunNowOut:
    created = run_once(db, container_of(request))
    service.write_audit(db, "alerts.run_now", detail={"created": len(created)})
    db.commit()
    return RunNowOut(created=len(created), alerts=[service.alert_out(a) for a in created])


@api_router.get("/audit", response_model=list[AuditOut])
def list_audit(limit: int = 100, db: Session = Depends(get_db)) -> list[AuditOut]:
    return service.list_audit(db, limit)


router = APIRouter()
router.include_router(api_router)
router.include_router(pages_router)
