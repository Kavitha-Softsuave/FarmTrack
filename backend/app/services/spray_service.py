"""Spray diary: the 'Sprayed' tick. Saves the entry, runs the hard spray checks, mirrors it to Zoho (best effort)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import SprayLogIn, SprayLogOut, WarningOut
from app.db.models import AdviceRow, SprayLogRow
from app.db.repo import sortable_id
from app.domain.types import FarmerProfile, Severity, SprayRecord
from app.integrations.reference import load_product_master
from app.integrations.zoho_rows import build_record, is_nutrient_text
from app.security.errors import ApiError
from app.services import texts
from app.services.catalogue import load_catalogue
from app.services.container import Container
from app.services.history import merged_history
from app.services.presenters import ist, warning_out
from app.services.product_match import ProductMatcher
from app.services.prompts import PromptBook
from app.services.speech import speak, without_typed_text

logger = logging.getLogger(__name__)

_PRODUCT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,10}$")
_CROP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$")
MAX_BACKDATE = timedelta(days=400)
FUTURE_TOLERANCE = timedelta(hours=1)
PRODUCT_NOT_RECOGNISED = "PRODUCT_NOT_RECOGNISED"


@dataclass(frozen=True)
class _Choice:
    """The medicine of a diary entry. `product_id` None means that only the typed text is known."""
    product_id: str | None = None
    brand: str | None = None                  # the typed brand name, when free text was matched through a brand
    unrecognised: bool = False                # typed text that could not be matched (and is not a nutrient): warn the farmer


class SprayService:
    def __init__(self, container: Container, db: Session) -> None:
        self.c = container
        self.db = db

    def find_by_request_id(self, farmer: FarmerProfile, client_request_id: str | None) -> SprayLogOut | None:
        """The stored answer for an entry this farmer already sent with this Idempotency-Key (None: no key, or a new one)."""
        row = self._by_request_id(farmer, client_request_id)
        return self._replay(row) if row is not None else None

    def create(self, farmer: FarmerProfile, body: SprayLogIn, client_request_id: str | None = None) -> SprayLogOut:
        now = self.c.clock.now()
        crop_id = self._crop(body.crop_id)
        advice_products = self._advice_products(farmer, body.advice_id)
        free_text = (body.free_text or "").strip() or None
        choice = self._choose(body.product_id, advice_products, free_text, crop_id)
        if not (choice.product_id or free_text):
            raise ApiError(422, "spray_needs_product", "Say which medicine was sprayed.")
        sprayed_at = self._sprayed_at(body.sprayed_at, now)
        product_id = choice.product_id
        product = load_product_master(self.c.settings.data_dir).get(product_id or "")
        product_name = self._product_name(product_id, advice_products) or (product.active_ingredient if product else None)
        if choice.brand and product_name:
            product_name = f"{choice.brand} ({product_name})"[:120]          # what the farmer typed, and what it is
        product_name = (product_name or free_text or "")[:120] or None       # the column is 120 wide (free_text may be 200)
        record = build_record(sprayed_at, free_text or product_name, None, choice.brand or product_name, product, source="app")
        history, _zoho_ok = merged_history(self.c, self.db, farmer, now)
        warnings = self._check(farmer, record, history, now)
        if choice.unrecognised:
            warnings.append(WarningOut(code=PRODUCT_NOT_RECOGNISED, level=Severity.yellow, text=texts.PRODUCT_NOT_RECOGNISED))

        row = SprayLogRow(id=sortable_id(), farmer_id=farmer.id, crop_id=crop_id, advice_id=body.advice_id,
                          product_id=product_id, product_name=product_name, free_text=free_text, sprayed_at=sprayed_at,
                          notes=(body.notes or "").strip() or None, synced_to_zoho=False,
                          warnings=[w.model_dump(mode="json") for w in warnings], created_at=now,
                          client_request_id=client_request_id)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            stored = self._by_request_id(farmer, client_request_id)             # lost the race to a twin with the same key
            if stored is None:
                raise
            logger.info("spray log lost the race to its twin farmer=%s: returning the stored entry", farmer.id)
            return self._replay(stored)

        row.synced_to_zoho = self._write_zoho(farmer, record)
        self.db.commit()
        return self._out(row, warnings, with_spoken=True)

    def list_logs(self, farmer: FarmerProfile, limit: int) -> list[SprayLogOut]:
        stmt = (select(SprayLogRow).where(SprayLogRow.farmer_id == farmer.id)
                .order_by(SprayLogRow.sprayed_at.desc(), SprayLogRow.id.desc()).limit(max(1, min(limit, 200))))
        return [self._out(r, [WarningOut.model_validate(w) for w in r.warnings or []], with_spoken=False)
                for r in self.db.scalars(stmt)]

    # ------------------------------------------------------------------ internals
    def _crop(self, raw: str) -> str:
        crop = raw.strip()
        if not _CROP_RE.match(crop):
            raise ApiError(422, "invalid_crop", "The crop name is not valid.")
        return load_catalogue(str(self.c.settings.data_dir)).canonical_crop(crop) or crop

    def _advice_products(self, farmer: FarmerProfile, advice_id: str | None) -> list[dict]:
        if advice_id is None:
            return []
        advice = self.db.get(AdviceRow, advice_id)
        if advice is None or advice.farmer_id != farmer.id:
            raise ApiError(404, "advice_not_found", "That advice was not found.")
        return list(advice.payload.get("products") or [])

    def _choose(self, requested: str | None, advice_products: list[dict], free_text: str | None, crop_id: str) -> _Choice:
        """Which medicine the entry is about. Never trusts an id blindly and never guesses an ambiguous name.

        1. A product_id must be one of the advice's products or be in the product master (the approved catalogue). An unknown
           id is ignored when the farmer also typed a name, and refused otherwise.
        2. Only an advice_id (the 'I sprayed this' tick): the advice's first product, the one that was read aloud. An advice
           without products (the expert route) gives nothing, so the entry needs a typed name.
        3. Typed text is matched against the catalogue (brand, active ingredient, id). No exact match: no product, and a yellow
           PRODUCT_NOT_RECOGNISED warning (not for nutrients, which are not pesticides).
        """
        if requested is not None:
            if not _PRODUCT_ID_RE.match(requested):
                raise ApiError(422, "invalid_product", "The product id is not valid.")
            advised = {str(p.get("product_id")) for p in advice_products}
            if requested in advised or requested in load_product_master(self.c.settings.data_dir):
                return _Choice(product_id=requested)
            if free_text is None:
                raise ApiError(422, "unknown_product", "That medicine is not in the approved list.")
            logger.info("unknown product id ignored, the typed name is used")
        elif advice_products and free_text is None:
            return _Choice(product_id=str(advice_products[0]["product_id"]))
        if free_text is None:
            return _Choice()
        match = ProductMatcher(self.c.settings.data_dir).resolve(free_text, crop_id)
        if match.status == "resolved":
            return _Choice(product_id=match.product_id, brand=free_text[:60] if match.via == "brand" else None)
        return _Choice(unrecognised=not is_nutrient_text(free_text))

    @staticmethod
    def _product_name(product_id: str | None, advice_products: list[dict]) -> str | None:
        for product in advice_products:
            if product.get("product_id") == product_id:
                return (product.get("active_ingredient") or {}).get("en")
        return None

    def _by_request_id(self, farmer: FarmerProfile, client_request_id: str | None) -> SprayLogRow | None:
        if client_request_id is None:
            return None
        return self.db.scalars(select(SprayLogRow).where(SprayLogRow.farmer_id == farmer.id,
                                                         SprayLogRow.client_request_id == client_request_id)).first()

    def _replay(self, row: SprayLogRow) -> SprayLogOut:
        return self._out(row, [WarningOut.model_validate(w) for w in row.warnings or []], with_spoken=True)

    def _sprayed_at(self, requested: datetime | None, now: datetime) -> datetime:
        if requested is None:
            return ist(now)
        value = ist(requested)
        if value < now - MAX_BACKDATE:
            raise ApiError(422, "sprayed_at_too_old", "The spray date is too far in the past.")
        # With the frozen demo clock a real phone clock is always "in the future", so only check against a moving clock.
        if not self.c.clock.is_fixed and value > now + FUTURE_TOLERANCE:
            raise ApiError(422, "sprayed_at_in_future", "The spray date cannot be in the future.")
        return value

    def _check(self, farmer: FarmerProfile, record: SprayRecord, history: list[SprayRecord], now: datetime) -> list[WarningOut]:
        try:
            return [warning_out(w) for w in self.c.rules.check_spray(farmer, record, history, now)]
        except Exception:
            logger.exception("spray check failed; entry saved without warnings farmer=%s", farmer.id)
            return []

    def _write_zoho(self, farmer: FarmerProfile, record: SprayRecord) -> bool:
        try:
            return bool(self.c.zoho.write_spray(farmer.id, record))
        except Exception:
            logger.exception("zoho spray write failed farmer=%s", farmer.id)
            return False

    def _out(self, row: SprayLogRow, warnings: list[WarningOut], with_spoken: bool) -> SprayLogOut:
        spoken = None
        if with_spoken:
            book = PromptBook(self.c.settings.voice_dir)
            text = book.get("diary_saved", texts.DIARY_SAVED_FALLBACK)
            if warnings:
                # The spoken copy never carries what the farmer typed (a warning may echo a typed medicine name): see speech.py
                heard = without_typed_text(warnings[0].text, (row.free_text, row.product_name if row.product_id is None else None))
                text = book.join(text, book.get("diary_warning", texts.DIARY_WARNING_LEAD_FALLBACK), heard)
            spoken = speak(self.c.audio, text)
        return SprayLogOut(id=row.id, crop_id=row.crop_id, product_id=row.product_id, product_name=row.product_name,
                           sprayed_at=ist(row.sprayed_at), advice_id=row.advice_id, warnings=warnings,
                           synced_to_zoho=row.synced_to_zoho, spoken=spoken)
