"""Zoho CRM v6 adapter (India data centre). SKELETON: NEVER RUN AGAINST A REAL ZOHO ORG.

Everything marked ASSUMED below (module and field API names, how a farmer id maps to a Contact, the subform update shape) must be
checked against the client's org before use. See docs/design-notes/integrations.md ("Zoho assumptions").

Configuration (Settings fields, so environment variables and the .env file both work):
  ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN   self-client OAuth credentials (required)
  ZOHO_ACCOUNTS_URL   default https://accounts.zoho.in     (India data centre)
  ZOHO_API_BASE       default https://www.zohoapis.in/crm/v6
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.clock import IST
from app.config import Settings
from app.domain.types import FarmerProfile, SprayRecord
from app.integrations.errors import NotConfigured, ZohoError
from app.integrations.normalise import normalise_phone
from app.integrations.reference import load_product_master
from app.integrations.zoho_rows import record_from_row

log = logging.getLogger(__name__)

CONTACTS = "Contacts"            # ASSUMED module for farmers
FARMER_CODE_FIELD = "Farmer_ID"  # ASSUMED custom field holding the app's farmer id (F001...)
ADVISORY_SUBFORM = "Advisory"    # ASSUMED subform API name (mock_zoho/contacts.json uses the same)
_REFRESH_MARGIN_S = 60
_SAFE_ID = re.compile(r"[A-Za-z0-9_\-]{1,40}")


@dataclass(frozen=True)
class ZohoConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    accounts_url: str = "https://accounts.zoho.in"
    api_base: str = "https://www.zohoapis.in/crm/v6"

    @classmethod
    def from_settings(cls, settings: Settings) -> ZohoConfig:
        values = {"ZOHO_CLIENT_ID": settings.zoho_client_id, "ZOHO_CLIENT_SECRET": settings.zoho_client_secret,
                  "ZOHO_REFRESH_TOKEN": settings.zoho_refresh_token}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise NotConfigured("Zoho is selected (ZOHO_PROVIDER=real) but these variables are not set: " + ", ".join(missing))
        return cls(
            client_id=str(settings.zoho_client_id), client_secret=str(settings.zoho_client_secret),
            refresh_token=str(settings.zoho_refresh_token),
            accounts_url=settings.zoho_accounts_url.rstrip("/"), api_base=settings.zoho_api_base.rstrip("/"),
        )

    @classmethod
    def from_env(cls) -> ZohoConfig:
        """The process environment only (no .env file): what a container sees."""
        return cls.from_settings(Settings(_env_file=None))  # type: ignore[call-arg]


class RealZohoAdapter:
    def __init__(self, config: ZohoConfig, data_dir: Path, client: httpx.Client | None = None,
                 monotonic=time.monotonic) -> None:  # noqa: ANN001
        self._cfg = config
        self._products = load_product_master(Path(data_dir))
        self._http = client or httpx.Client(timeout=15.0)
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_expires = 0.0

    # ------------------------------------------------------------------------------------------ http
    def _access_token(self) -> str:
        with self._lock:
            if self._token and self._monotonic() < self._token_expires - _REFRESH_MARGIN_S:
                return self._token
            try:
                resp = self._http.post(f"{self._cfg.accounts_url}/oauth/v2/token", data={
                    "grant_type": "refresh_token", "client_id": self._cfg.client_id,
                    "client_secret": self._cfg.client_secret, "refresh_token": self._cfg.refresh_token})
                body = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ZohoError(f"Zoho token request failed: {type(exc).__name__}") from exc
            token = body.get("access_token") if isinstance(body, dict) else None
            if resp.status_code != 200 or not token:
                raise ZohoError(f"Zoho token request refused (HTTP {resp.status_code})")
            self._token = token
            self._token_expires = self._monotonic() + float(body.get("expires_in", 3600))
            return token

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Zoho-oauthtoken {self._access_token()}"}
        try:
            resp = self._http.request(method, f"{self._cfg.api_base}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ZohoError(f"Zoho request failed: {type(exc).__name__}") from exc
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise ZohoError(f"Zoho {method} {path.split('?')[0]} returned HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise ZohoError("Zoho returned a non-JSON answer") from exc
        return body if isinstance(body, dict) else {}

    def _contact(self, farmer_id: str, fields: str) -> dict[str, Any] | None:
        if not _SAFE_ID.fullmatch(farmer_id):     # the id goes into a Zoho search criteria string: no brackets, commas or quotes
            return None
        body =self._request("GET", f"/{CONTACTS}/search", params={"criteria": f"({FARMER_CODE_FIELD}:equals:{farmer_id})",
                                                                    "fields": fields})
        data = body.get("data") or []
        return data[0] if data else None

    # ------------------------------------------------------------------------------------------ ZohoAdapter
    def get_farmer(self, farmer_id: str) -> FarmerProfile | None:
        contact = self._contact(farmer_id, "id,First_Name,Last_Name,Mobile,Mailing_City,District,Primary_Crop,Variety_Mix")
        if contact is None:
            return None
        name = " ".join(p for p in (contact.get("First_Name"), contact.get("Last_Name")) if p) or farmer_id
        primary = contact.get("Primary_Crop") or None
        return FarmerProfile(id=farmer_id, name=name, phone=normalise_phone(contact.get("Mobile")), district=contact.get("District"),
                             village=contact.get("Mailing_City"), crops=[primary] if primary else [], primary_crop=primary,
                             zoho_contact_id=str(contact.get("id") or "") or None)

    def get_history(self, farmer_id: str, until: datetime | None = None) -> list[SprayRecord]:
        contact = self._contact(farmer_id, f"id,{ADVISORY_SUBFORM}")
        if contact is None:
            return []
        if until is not None and until.tzinfo is None:
            until = until.replace(tzinfo=IST)
        records = []
        for row in contact.get(ADVISORY_SUBFORM) or []:
            record = record_from_row({k: "" if v is None else str(v) for k, v in row.items()}, self._products)
            if record is not None and (until is None or record.sprayed_at <= until):
                records.append(record)
        return sorted(records, key=lambda r: r.sprayed_at)

    def write_spray(self, farmer_id: str, record: SprayRecord) -> bool:
        """Appends one Advisory row. ASSUMED: new subform rows (no id) are appended and existing rows are kept."""
        try:
            contact = self._contact(farmer_id, "id")
            if contact is None:
                return False
            row = {"Self_Spray_Dt": record.sprayed_at.strftime("%d/%m/%Y"),
                   "Self_Sprayed": record.active_ingredient or record.trade_name or "",
                   "Self_Spray_Frac_Group": record.frac_irac_code or "",
                   "Self_Spray_Trade_Name": record.trade_name or ""}
            self._request("PUT", f"/{CONTACTS}/{contact['id']}", json={"data": [{ADVISORY_SUBFORM: [row]}]})
            return True
        except ZohoError as exc:
            log.warning("zoho write_spray failed: %s", exc)
            return False

    def write_diagnosis(self, farmer_id: str, payload: dict[str, Any]) -> bool:
        """Adds a Note on the Contact. ASSUMED: the Notes API with a Parent_Id module reference (v6 shape)."""
        try:
            contact = self._contact(farmer_id, "id")
            if contact is None:
                return False
            note = {"Note_Title": f"FarmTrack diagnosis {payload.get('disease_id') or ''}".strip(),
                    "Note_Content": str(payload)[:30000],
                    "Parent_Id": {"module": {"api_name": CONTACTS}, "id": contact["id"]}}
            self._request("POST", "/Notes", json={"data": [note]})
            return True
        except ZohoError as exc:
            log.warning("zoho write_diagnosis failed: %s", exc)
            return False
