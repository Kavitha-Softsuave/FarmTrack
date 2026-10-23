"""Server-rendered admin pages (Jinja2, no JavaScript, no build step). Cookie login + CSRF: see app.admin.auth.

Routes live under /admin. Every page is rendered through `render`, which adds the security headers. Texts that depend on a query
parameter come from fixed tables (MESSAGES), never from the parameter itself, so nothing is reflected into the page.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin import service
from app.admin.auth import (
    COOKIE_NAME,
    COOKIE_PATH,
    SESSION_SECONDS,
    AdminSession,
    check_origin,
    csrf_protect,
    csrf_token,
    issue_session,
    key_matches,
    login_throttle,
    optional_session,
    require_session,
    settings_of,
)
from app.admin.models import ExpertRequestResolveIn, FarmerCreateIn, FarmerLoginIn
from app.alerts.evaluator import run_once
from app.api.deps import get_db
from app.api.schemas import ProductAdminPatch, ReviewResolveIn
from app.clock import IST, get_clock
from app.integrations.reference import load_disease_options, load_product_master

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(HERE / "templates"))
router = APIRouter(prefix="/admin", include_in_schema=False)

PHOTO_BASE = "/admin/photos"
PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": ("default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
                                "base-uri 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
NAV = (("dashboard", "Dashboard"), ("review", "Review queue"), ("expert-requests", "Expert requests"), ("farmers", "Farmers"), ("products", "Approved products"),
       ("alerts", "Alerts"), ("clock", "Demo clock"), ("audit", "Audit log"))
MESSAGES = {
    "resolved": "Review task resolved.",
    "request_closed": "Expert request closed.",
    "request_already_closed": "That request was already closed.",
    "request_invalid": "The note was not accepted. Keep it under 500 characters.",
    "product_updated": "Product setting saved.",
    "clock_set": "Demo clock updated.",
    "alerts_run": "Alert run finished.",
    "bad_time": "That date and time could not be read. Use the date and time picker.",
    "clock_in_prod": "The date cannot be fixed in production: every farmer would get advice for the wrong season.",
    "login_saved": "Login saved. The farmer must use the new username and password.",
    "login_invalid": "The login was not accepted. The username needs 3-40 characters (a-z, 0-9, dot, underscore, hyphen) "
                     "and the password at least 6 characters.",
    "username_taken": "That username is already used by another farmer.",
    "phone_taken": "That phone number already belongs to another farmer.",
    "farmer_created": "Farmer added. Give them the username and password.",
    "farmer_invalid": "The farmer was not added. Check the name, phone number, crop, username and password (at least 6 characters).",
    "not_found": "That item no longer exists.",
    "already_resolved": "That review task was already resolved.",
    "invalid": "Some of the values were not accepted. Check the disease and the note length.",
    "release_failed": "The advice could not be released, so the task stays open.",
    "failed": "The action failed. Nothing was changed.",
    "no_container": "The alert service is not running in this process.",
}
_ERROR_FOR_STATUS = {404: "not_found", 409: "already_resolved", 422: "invalid", 502: "release_failed"}


def container_of(request: Request):  # noqa: ANN201
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(503, "the service container is not available")
    return container


def _clock(request: Request):  # noqa: ANN202
    container = getattr(request.app.state, "container", None)
    return container.clock if container is not None else get_clock()


def render(request: Request, name: str, session: AdminSession | None, status_code: int = 200, **context: object) -> HTMLResponse:
    query = request.query_params
    flash = None
    if query.get("ok") in MESSAGES:
        text = MESSAGES[query["ok"]]
        if query["ok"] == "alerts_run" and query.get("n", "").isdigit():
            text = f"Alert run finished: {int(query['n'])} new alerts."
        flash = ("ok", text)
    elif query.get("err") in MESSAGES:
        flash = ("error", MESSAGES[query["err"]])
    context.update(csrf=csrf_token(settings_of(request), session) if session else "", logged_in=session is not None, nav=NAV, flash=flash,
                   page=name.removesuffix(".html"))
    response = templates.TemplateResponse(request, name, context, status_code=status_code)
    response.headers.update(SECURITY_HEADERS)
    return response


def redirect(path: str, **params: object) -> RedirectResponse:
    query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
    return RedirectResponse(f"{path}?{query}" if query else path, status_code=303, headers=SECURITY_HEADERS)


# ------------------------------------------------------------------------------------------------- shared with the API router
def photo_response(request: Request, db: Session, scan_id: str, index: int) -> FileResponse:
    path = service.photo_file(db, settings_of(request).storage_dir, scan_id, index)
    media_type = PHOTO_TYPES.get(path.suffix.lower()) if path else None
    if path is None or media_type is None:
        raise HTTPException(404, "photo not found")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


# ------------------------------------------------------------------------------------------------- login
@router.get("")
def home(session: AdminSession | None = Depends(optional_session)) -> RedirectResponse:
    return redirect("/admin/dashboard" if session else "/admin/login")


@router.get("/static/admin.css")
def stylesheet() -> FileResponse:
    return FileResponse(HERE / "static" / "admin.css", media_type="text/css", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/login")
def login_form(request: Request, session: AdminSession | None = Depends(optional_session)) -> Response:
    if session:
        return redirect("/admin/dashboard")
    return render(request, "login.html", None)


@router.post("/login")
def login(request: Request, admin_key: str = Form("")) -> Response:
    check_origin(request)
    who = request.client.host if request.client else "unknown"
    if login_throttle.blocked(who):
        return render(request, "login.html", None, status_code=429, error="Too many failed attempts. Wait a few minutes and try again.")
    settings = settings_of(request)
    if not key_matches(settings, admin_key):
        login_throttle.fail(who)
        return render(request, "login.html", None, status_code=401, error="That admin key is not correct.")
    login_throttle.reset(who)
    response = redirect("/admin/dashboard")
    response.set_cookie(COOKIE_NAME, issue_session(settings), max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                        secure=settings.is_prod, path=COOKIE_PATH)
    return response


@router.post("/logout")
def logout(_: AdminSession = Depends(csrf_protect)) -> RedirectResponse:
    response = redirect("/admin/login")
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
    return response


# ------------------------------------------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(request: Request, session: AdminSession = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    return render(request, "dashboard.html", session, counts=service.dashboard_counts(db), clock=service.clock_out(_clock(request)),
                  alerts=service.list_alerts(db, 5), audit=service.list_audit(db, 5))


# ------------------------------------------------------------------------------------------------- review queue
@router.get("/review")
def review(request: Request, status: str = "open", session: AdminSession = Depends(require_session),
           db: Session = Depends(get_db)) -> Response:
    status = status if status in service.REVIEW_STATUSES else "open"
    data_dir = settings_of(request).data_dir
    crops = sorted({p.crop for p in load_product_master(data_dir).values()})
    return render(request, "review.html", session, status=status, tasks=service.list_review_tasks(db, status, 50, PHOTO_BASE),
                  crops=crops, diseases=load_disease_options(data_dir))


@router.post("/review/{task_id}/resolve")
def review_resolve(task_id: str, request: Request, confirmed_crop: str = Form(""), confirmed_disease: str = Form(""),
                   note: str = Form(""), release_advice: str = Form(""), _: AdminSession = Depends(csrf_protect),
                   db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        body = ReviewResolveIn(confirmed_crop=confirmed_crop.strip() or None, confirmed_disease=confirmed_disease.strip() or None,
                               note=note.strip() or None, release_advice=bool(release_advice))
        service.resolve_review_task(db, task_id, body, _clock(request).now(), settings_of(request).data_dir,
                                    getattr(request.app.state, "release_advice", None), PHOTO_BASE)
    except ValidationError:
        return redirect("/admin/review", err="invalid")
    except HTTPException as exc:
        return redirect("/admin/review", err=_ERROR_FOR_STATUS.get(exc.status_code, "failed"))
    return redirect("/admin/review", ok="resolved")


@router.get("/photos/{scan_id}/{index}")
def photo(scan_id: str, index: int, request: Request, _: AdminSession = Depends(require_session),
          db: Session = Depends(get_db)) -> FileResponse:
    return photo_response(request, db, scan_id, index)


# ------------------------------------------------------------------------------------------------- expert requests
@router.get("/expert-requests")
def expert_requests(request: Request, status: str = "open", session: AdminSession = Depends(require_session),
                    db: Session = Depends(get_db)) -> Response:
    status = status if status in service.REVIEW_STATUSES else "open"
    return render(request, "expert-requests.html", session, status=status, requests=service.list_expert_requests(db, status, 100))


@router.post("/expert-requests/{request_id}/resolve")
def expert_request_resolve(request_id: str, request: Request, note: str = Form(""), _: AdminSession = Depends(csrf_protect),
                           db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        body = ExpertRequestResolveIn(note=note.strip() or None)
        service.resolve_expert_request(db, request_id, body.note, _clock(request).now())
    except ValidationError:
        return redirect("/admin/expert-requests", err="request_invalid")
    except HTTPException as exc:
        return redirect("/admin/expert-requests", err={404: "not_found", 409: "request_already_closed"}.get(exc.status_code, "failed"))
    return redirect("/admin/expert-requests", ok="request_closed")


# ------------------------------------------------------------------------------------------------- farmers, products
@router.get("/farmers")
def farmers(request: Request, session: AdminSession = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    crops = sorted({p.crop for p in load_product_master(settings_of(request).data_dir).values()})
    return render(request, "farmers.html", session, farmers=service.list_farmers(db, 500), crops=crops)


@router.post("/farmers/{farmer_id}/login")
def farmer_set_login(farmer_id: str, username: str = Form(""), password: str = Form(""), _: AdminSession = Depends(csrf_protect),
                     db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        service.set_farmer_login(db, farmer_id, FarmerLoginIn(username=username, password=password))
    except ValidationError:
        return redirect("/admin/farmers", err="login_invalid")
    except HTTPException as exc:
        taken = exc.status_code == 409 and exc.detail == service.USERNAME_TAKEN
        return redirect("/admin/farmers", err="username_taken" if taken else _ERROR_FOR_STATUS.get(exc.status_code, "failed"))
    return redirect("/admin/farmers", ok="login_saved")


@router.post("/farmers")
def farmer_create(request: Request, name: str = Form(""), phone: str = Form(""), language: str = Form("hi"), district: str = Form(""),
                  village: str = Form(""), primary_crop: str = Form(""), other_crops: str = Form(""), phenology_band: str = Form(""),
                  elevation_m: str = Form(""), username: str = Form(""), password: str = Form(""),
                  _: AdminSession = Depends(csrf_protect), db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        elevation = float(elevation_m) if elevation_m.strip() else None
        body = FarmerCreateIn(name=name, phone=phone, language=language, district=district, village=village,  # type: ignore[arg-type]
                              primary_crop=primary_crop, other_crops=[c for c in other_crops.replace(";", ",").split(",")],
                              phenology_band=phenology_band, elevation_m=elevation, username=username, password=password)
        service.create_farmer(db, body, _clock(request).now())
    except (ValidationError, ValueError):
        return redirect("/admin/farmers", err="farmer_invalid")
    except HTTPException as exc:
        return redirect("/admin/farmers", err={service.PHONE_TAKEN: "phone_taken", service.USERNAME_TAKEN: "username_taken"}.get(
            str(exc.detail), "failed"))
    return redirect("/admin/farmers", ok="farmer_created")


@router.get("/products")
def products(request: Request, crop: str = "", session: AdminSession = Depends(require_session),
             db: Session = Depends(get_db)) -> Response:
    data_dir = settings_of(request).data_dir
    crops = sorted({p.crop for p in load_product_master(data_dir).values()})
    crop = crop if crop in crops else ""
    return render(request, "products.html", session, crop=crop, crops=crops, products=service.list_products(db, data_dir, crop or None),
                  notes=service.product_notes(db))


@router.post("/products/{product_id}/toggle")
def product_toggle(product_id: str, request: Request, enabled: str = Form(""), note: str = Form(""), crop: str = Form(""),
                   _: AdminSession = Depends(csrf_protect), db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        body = ProductAdminPatch(enabled=enabled == "1", note=note.strip()[:300] or None)
        service.patch_product(db, settings_of(request).data_dir, product_id, body, _clock(request).now())
    except (ValidationError, HTTPException) as exc:
        code = _ERROR_FOR_STATUS.get(exc.status_code, "failed") if isinstance(exc, HTTPException) else "invalid"
        return redirect("/admin/products", err=code, crop=crop)
    return redirect("/admin/products", ok="product_updated", crop=crop)


# ------------------------------------------------------------------------------------------------- alerts
@router.get("/alerts")
def alerts(request: Request, session: AdminSession = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    return render(request, "alerts.html", session, alerts=service.list_alerts(db, 100))


@router.post("/alerts/run-now")
def alerts_run_now(request: Request, _: AdminSession = Depends(csrf_protect), db: Session = Depends(get_db)) -> RedirectResponse:
    if getattr(request.app.state, "container", None) is None:
        return redirect("/admin/alerts", err="no_container")
    try:
        created = run_once(db, container_of(request))
        service.write_audit(db, "alerts.run_now", detail={"created": len(created)})
        db.commit()
    except Exception:
        db.rollback()
        log.exception("admin alert run failed")
        return redirect("/admin/alerts", err="failed")
    return redirect("/admin/alerts", ok="alerts_run", n=len(created))


# ------------------------------------------------------------------------------------------------- demo clock
@router.get("/clock")
def clock_page(request: Request, session: AdminSession = Depends(require_session)) -> Response:
    current = service.clock_out(_clock(request))
    return render(request, "clock.html", session, clock=current, picker_value=current.now.astimezone(IST).strftime("%Y-%m-%dT%H:%M"))


@router.post("/clock")
def clock_save(request: Request, now: str = Form(""), action: str = Form("set"), _: AdminSession = Depends(csrf_protect),
               db: Session = Depends(get_db)) -> RedirectResponse:
    value: datetime | None = None
    if action != "real":
        try:
            value = datetime.fromisoformat(now.strip()).replace(tzinfo=IST)
        except ValueError:
            return redirect("/admin/clock", err="bad_time")
    settings = settings_of(request)
    if value is not None and settings.is_prod and not settings.allow_demo_clock_in_prod:
        return redirect("/admin/clock", err="clock_in_prod")
    service.set_demo_clock(db, _clock(request), value)
    return redirect("/admin/clock", ok="clock_set")


# ------------------------------------------------------------------------------------------------- audit
@router.get("/audit")
def audit(request: Request, session: AdminSession = Depends(require_session), db: Session = Depends(get_db)) -> Response:
    return render(request, "audit.html", session, entries=service.list_audit(db, 100))
