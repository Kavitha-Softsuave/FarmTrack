from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_db
from app.api.schemas import ErrorOut, LoginIn, OtpRequestIn, OtpRequestOut, OtpVerifyIn, RefreshIn, TokenOut
from app.db.models import FarmerRow
from app.db.repo import farmer_profile
from app.security.errors import ApiError
from app.services.auth_service import AuthService
from app.services.presenters import farmer_out

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def get_auth_service(request: Request, db: Session = Depends(get_db)) -> AuthService:
    state = request.app.state
    return AuthService(db, state.settings, state.sms_sender, state.limiters)


def _token_out(farmer: FarmerRow, access: str, refresh: str, expires_in: int) -> TokenOut:
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=expires_in, farmer=farmer_out(farmer_profile(farmer)))


def require_otp_login(request: Request) -> None:
    """The OTP login is kept in the code but off for the MVP (OTP_LOGIN_ENABLED): its routes then look like they do not exist."""
    if not request.app.state.settings.otp_login_enabled:
        raise ApiError(404, "not_found", "Not found.")


@router.post("/login", response_model=TokenOut, responses={401: {"model": ErrorOut}, 422: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def login(body: LoginIn, request: Request, auth: AuthService = Depends(get_auth_service)) -> TokenOut:
    """Log in with username and password (the username is not case-sensitive).

    Returns the tokens and the farmer, like the OTP login. A wrong username and a wrong password give the same 401
    `invalid_credentials`; too many tries give 429 `rate_limited` with a Retry-After header."""
    farmer = auth.login(body.username, body.password, client_ip(request), body.device_id)
    access, refresh, expires_in = auth.issue_tokens(farmer, body.device_id)
    return _token_out(farmer, access, refresh, expires_in)


@router.post("/otp/request", response_model=OtpRequestOut, dependencies=[Depends(require_otp_login)],
             responses={404: {"model": ErrorOut}, 429: {"model": ErrorOut}, 503: {"model": ErrorOut}})
def request_otp(body: OtpRequestIn, request: Request, auth: AuthService = Depends(get_auth_service)) -> OtpRequestOut:
    """Send a one-time code by SMS (dev: fixed code, returned as dev_otp when env != prod). Switched off (404) unless OTP_LOGIN_ENABLED.

    The answer is the same for a registered and an unregistered number; only registered numbers receive an SMS."""
    return auth.request_otp(body.phone, client_ip(request))


@router.post("/otp/verify", response_model=TokenOut, dependencies=[Depends(require_otp_login)],
             responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def verify_otp(body: OtpVerifyIn, request: Request, auth: AuthService = Depends(get_auth_service)) -> TokenOut:
    farmer = auth.verify_otp(body.request_id, body.otp, client_ip(request), body.device_id)
    access, refresh, expires_in = auth.issue_tokens(farmer, body.device_id)
    return _token_out(farmer, access, refresh, expires_in)


@router.post("/refresh", response_model=TokenOut, responses={401: {"model": ErrorOut}, 429: {"model": ErrorOut}})
def refresh(body: RefreshIn, request: Request, auth: AuthService = Depends(get_auth_service)) -> TokenOut:
    """Rotate the refresh token: the old one stops working, a new pair is returned."""
    farmer, access, new_refresh, expires_in = auth.rotate_refresh(body.refresh_token, client_ip(request))
    return _token_out(farmer, access, new_refresh, expires_in)


@router.post("/logout", status_code=204)
def logout(body: RefreshIn, auth: AuthService = Depends(get_auth_service)) -> Response:
    """Revoke the refresh token (always 204). The short-lived access token simply runs out."""
    auth.revoke_refresh(body.refresh_token)
    return Response(status_code=204)
