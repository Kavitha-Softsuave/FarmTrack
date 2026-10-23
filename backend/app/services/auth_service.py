"""Username + password login (the MVP login), the phone + OTP login (kept, off by default), JWT access tokens and rotating
refresh tokens.

Password login: the password is stored only as a salted PBKDF2 hash; an unknown user and a wrong password get the identical 401
and cost about the same time; attempts are rate limited per IP and wrong passwords per username.

OTP security properties: the OTP is stored only as a peppered hash, expires, allows a few attempts and works once (atomic UPDATE);
an unknown phone gets the same response as a known one (no account enumeration) but no SMS; refresh tokens are opaque, stored
hashed, rotated on every use, and a replayed (already rotated) token revokes that device's tokens.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session

from app.api.schemas import OtpRequestOut
from app.config import Settings
from app.db.models import FarmerRow, OtpRequestRow, RefreshTokenRow, new_id
from app.db.repo import get_farmer_by_phone, get_farmer_by_username, get_farmer_row
from app.security import timeutil
from app.security.errors import ApiError
from app.security.otp import dev_fixed_code, generate_code, hash_otp, otp_matches
from app.security.passwords import burn_password_check, normalize_username, verify_password
from app.security.phone import normalize_phone
from app.security.ratelimit import RateLimiters, enforce, enforce_open
from app.security.sms import SmsSender
from app.security.tokens import create_access_token, hash_refresh_token, new_refresh_token

logger = logging.getLogger(__name__)

MAX_ACTIVE_REFRESH_TOKENS = 10
MAX_DEVICE_ID_LENGTH = 80
_STALE_OTP_AFTER = timedelta(days=1)


class AuthService:
    def __init__(self, db: Session, settings: Settings, sms: SmsSender, limiters: RateLimiters) -> None:
        self.db = db
        self.settings = settings
        self.sms = sms
        self.limiters = limiters

    # ------------------------------------------------------------------ username + password
    def login(self, username: str, password: str, ip: str, device_id: str | None) -> FarmerRow:
        """Check the credentials and return the farmer (the caller issues the tokens). Any failure is the same 401."""
        _clean_device_id(device_id)                      # a bad device_id is a 422 whatever the credentials are
        enforce(self.limiters.login_ip, ip)
        name = username.strip().lower()
        enforce_open(self.limiters.login_user_fail, name, "Too many wrong passwords for this username. Please try again later.")
        valid_name = normalize_username(name)
        farmer = get_farmer_by_username(self.db, valid_name) if valid_name else None
        if farmer is not None and farmer.password_hash:
            if verify_password(password, farmer.password_hash):
                return farmer
        else:
            burn_password_check(password)                # nothing to compare: spend the same time as a real check
        self.limiters.login_user_fail.hit(name)
        raise ApiError(401, "invalid_credentials", "The username or password is not correct.")

    # ------------------------------------------------------------------ OTP
    def request_otp(self, raw_phone: str, ip: str) -> OtpRequestOut:
        phone = normalize_phone(raw_phone)
        if phone is None:
            raise ApiError(422, "invalid_phone", "Enter a valid phone number.")
        enforce(self.limiters.otp_ip, ip)
        enforce(self.limiters.otp_phone, phone, "Too many codes requested for this number. Please wait a few minutes.")

        farmer = get_farmer_by_phone(self.db, phone)
        fixed = dev_fixed_code(self.settings) if farmer else None
        code = fixed or generate_code()
        now = timeutil.utcnow()
        self.db.execute(update(OtpRequestRow).where(OtpRequestRow.phone == phone, OtpRequestRow.consumed.is_(False))
                        .values(consumed=True))                                  # only the newest code is valid
        self.db.execute(delete(OtpRequestRow).where(OtpRequestRow.expires_at < now - _STALE_OTP_AFTER))
        request_id = new_id()
        self.db.add(OtpRequestRow(id=request_id, phone=phone, otp_hash=hash_otp(self.settings, request_id, code),
                                  expires_at=now + timedelta(seconds=self.settings.otp_ttl_seconds), attempts=0,
                                  consumed=False, created_at=now))
        self.db.commit()

        if farmer is not None:
            try:
                self.sms.send(phone, f"Your FarmTrack code is {code}. It is valid for "
                                     f"{max(self.settings.otp_ttl_seconds // 60, 1)} minutes. Do not share it.")
            except Exception:
                logger.exception("sms delivery failed")
                raise ApiError(503, "sms_unavailable", "We could not send the code. Please try again.") from None
        else:
            logger.info("otp requested for an unregistered number (no sms sent)")
        return OtpRequestOut(request_id=request_id, expires_in=self.settings.otp_ttl_seconds,
                             dev_otp=fixed if farmer is not None else None)

    def verify_otp(self, request_id: str, code: str, ip: str, device_id: str | None) -> FarmerRow:
        enforce(self.limiters.verify_ip, ip)
        _clean_device_id(device_id)                      # reject a bad device_id before the code is consumed
        row = self.db.get(OtpRequestRow, request_id)
        if row is None:
            raise ApiError(400, "invalid_otp", "That code is not correct.")
        if row.consumed:
            raise ApiError(400, "otp_already_used", "That code was already used or replaced. Please ask for a new code.")
        if timeutil.as_utc(row.expires_at) <= timeutil.utcnow():
            raise ApiError(400, "otp_expired", "That code has expired. Please ask for a new code.")
        if row.attempts >= self.settings.otp_max_attempts:
            raise ApiError(400, "otp_attempts_exceeded", "Too many wrong tries. Please ask for a new code.")
        # Wrong codes per phone over ALL its code requests; refused before the code is compared, so the right code
        # cannot out-guess the limit either.
        enforce_open(self.limiters.verify_phone_fail, row.phone, "Too many wrong codes for this number. Please try again later.")
        # The attempt is counted BEFORE the code is compared and the cap is part of the same UPDATE: parallel guesses cannot
        # get more than OTP_MAX_ATTEMPTS comparisons (a read-compare-increment sequence lets a burst through).
        taken = cast(CursorResult, self.db.execute(
            update(OtpRequestRow).where(OtpRequestRow.id == row.id, OtpRequestRow.consumed.is_(False),
                                        OtpRequestRow.attempts < self.settings.otp_max_attempts)
            .values(attempts=OtpRequestRow.attempts + 1)))
        self.db.commit()
        self.db.refresh(row)
        if taken.rowcount != 1:
            if row.consumed:
                raise ApiError(400, "otp_already_used", "That code was already used or replaced. Please ask for a new code.")
            raise ApiError(400, "otp_attempts_exceeded", "Too many wrong tries. Please ask for a new code.")
        if not otp_matches(self.settings, row.id, code, row.otp_hash):
            self.limiters.verify_phone_fail.hit(row.phone)
            left = max(self.settings.otp_max_attempts - row.attempts, 0)
            raise ApiError(400, "invalid_otp", "That code is not correct.", {"attempts_left": left})
        claimed = cast(CursorResult, self.db.execute(
            update(OtpRequestRow).where(OtpRequestRow.id == row.id, OtpRequestRow.consumed.is_(False)).values(consumed=True)))
        self.db.commit()
        if claimed.rowcount != 1:                                                # lost a race with a parallel verify
            raise ApiError(400, "otp_already_used", "That code was already used or replaced. Please ask for a new code.")
        farmer = get_farmer_by_phone(self.db, row.phone)
        if farmer is None:
            raise ApiError(400, "invalid_otp", "That code is not correct.")
        return farmer

    # ------------------------------------------------------------------ tokens
    def issue_tokens(self, farmer: FarmerRow, device_id: str | None) -> tuple[str, str, int]:
        """Return (access_token, refresh_token, expires_in) and record the session."""
        device = _clean_device_id(device_id)
        now = timeutil.utcnow()
        if device is not None:                                                   # one live session per device
            self.db.execute(update(RefreshTokenRow).where(RefreshTokenRow.farmer_id == farmer.id,
                                                          RefreshTokenRow.device_id == device).values(revoked=True))
        refresh = new_refresh_token()
        self.db.add(RefreshTokenRow(id=new_id(), farmer_id=farmer.id, token_hash=hash_refresh_token(self.settings, refresh),
                                    device_id=device, revoked=False,
                                    expires_at=now + timedelta(days=self.settings.refresh_token_days)))
        self._cap_sessions(farmer.id)
        farmer.last_seen_at = now
        self.db.commit()
        access, expires_in = create_access_token(self.settings, farmer.id)
        return access, refresh, expires_in

    def rotate_refresh(self, raw_token: str, ip: str) -> tuple[FarmerRow, str, str, int]:
        enforce(self.limiters.refresh_ip, ip)
        invalid = ApiError(401, "invalid_refresh_token", "Please log in again.")
        row = self.db.scalars(select(RefreshTokenRow).where(
            RefreshTokenRow.token_hash == hash_refresh_token(self.settings, raw_token))).first()
        if row is None:
            raise invalid
        if row.revoked:
            self._revoke_device_sessions(row)                                    # replayed token: treat the family as stolen
            logger.warning("refresh token reuse detected farmer=%s", row.farmer_id)
            raise invalid
        if timeutil.as_utc(row.expires_at) <= timeutil.utcnow():
            raise ApiError(401, "refresh_token_expired", "Your session has expired. Please log in again.")
        claimed = cast(CursorResult, self.db.execute(
            update(RefreshTokenRow).where(RefreshTokenRow.id == row.id, RefreshTokenRow.revoked.is_(False)).values(revoked=True)))
        self.db.commit()
        if claimed.rowcount != 1:
            raise invalid
        farmer = get_farmer_row(self.db, row.farmer_id)
        if farmer is None:
            raise invalid
        access, refresh, expires_in = self.issue_tokens(farmer, row.device_id)
        return farmer, access, refresh, expires_in

    def revoke_refresh(self, raw_token: str) -> None:
        """Log out: the refresh token stops working (unknown or already revoked tokens are ignored, so the answer never leaks)."""
        self.db.execute(update(RefreshTokenRow).where(RefreshTokenRow.token_hash == hash_refresh_token(self.settings, raw_token))
                        .values(revoked=True))
        self.db.commit()

    # ------------------------------------------------------------------ internals
    def _revoke_device_sessions(self, row: RefreshTokenRow) -> None:
        condition = RefreshTokenRow.device_id.is_(None) if row.device_id is None else RefreshTokenRow.device_id == row.device_id
        self.db.execute(update(RefreshTokenRow).where(RefreshTokenRow.farmer_id == row.farmer_id, condition).values(revoked=True))
        self.db.commit()

    def _cap_sessions(self, farmer_id: str) -> None:
        self.db.flush()
        live = self.db.scalars(select(RefreshTokenRow).where(RefreshTokenRow.farmer_id == farmer_id,
                                                             RefreshTokenRow.revoked.is_(False))
                               .order_by(RefreshTokenRow.expires_at.desc())).all()
        for old in live[MAX_ACTIVE_REFRESH_TOKENS:]:
            old.revoked = True


def _clean_device_id(device_id: str | None) -> str | None:
    if device_id is None:
        return None
    cleaned = "".join(ch for ch in device_id.strip() if ch.isprintable())
    if not cleaned:
        return None
    if len(cleaned) > MAX_DEVICE_ID_LENGTH:
        raise ApiError(422, "invalid_device_id", f"device_id must be at most {MAX_DEVICE_ID_LENGTH} characters.")
    return cleaned
