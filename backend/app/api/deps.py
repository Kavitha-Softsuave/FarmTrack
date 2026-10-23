"""FastAPI dependencies: database session, current farmer, admin key, shared app objects."""
from __future__ import annotations

import hmac
from collections.abc import Iterator

from fastapi import Depends, Header, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.repo import farmer_profile, get_farmer_row
from app.db.session import get_session_factory
from app.domain.types import FarmerProfile
from app.security.errors import ApiError
from app.security.ratelimit import RateLimiters, enforce, enforce_open
from app.security.tokens import decode_access_token
from app.services.container import Container

bearer_scheme = HTTPBearer(auto_error=False, description="Access token from /v1/auth/otp/verify")


def get_db() -> Iterator[Session]:
    """One session per request. Services commit explicitly before the response is built; an error rolls back."""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise ApiError(503, "service_unavailable", "The service is starting. Please try again in a moment.")
    return container


def get_limiters(request: Request) -> RateLimiters:
    return request.app.state.limiters


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def get_current_farmer(request: Request, creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
                       db: Session = Depends(get_db)) -> FarmerProfile:
    if creds is None or creds.scheme.lower() != "bearer":
        raise ApiError(401, "not_authenticated", "Please log in.", headers={"WWW-Authenticate": "Bearer"})
    farmer_id = decode_access_token(request.app.state.settings, creds.credentials)
    row = get_farmer_row(db, farmer_id)
    if row is None:
        raise ApiError(401, "invalid_token", "Your session is not valid. Please log in again.",
                       headers={"WWW-Authenticate": "Bearer"})
    return farmer_profile(row)


def require_admin(request: Request, x_admin_key: str | None = Header(default=None)) -> None:
    """X-Admin-Key must equal settings.admin_api_key (constant-time). Missing -> 401, wrong -> 403; wrong keys are rate limited."""
    settings: Settings = request.app.state.settings
    if not x_admin_key:
        raise ApiError(401, "admin_key_required", "The X-Admin-Key header is required.")
    limiters: RateLimiters | None = getattr(request.app.state, "limiters", None)
    too_many = "Too many wrong admin keys. Please wait."
    if limiters is not None:
        enforce_open(limiters.admin_fail_ip, client_ip(request), too_many)     # refuse BEFORE comparing: no out-guessing the limit
    if hmac.compare_digest(x_admin_key.encode("utf-8"), settings.admin_api_key.encode("utf-8")):
        return
    if limiters is not None:
        enforce(limiters.admin_fail_ip, client_ip(request), too_many)           # record this failure
    raise ApiError(403, "invalid_admin_key", "The admin key is not valid.")
