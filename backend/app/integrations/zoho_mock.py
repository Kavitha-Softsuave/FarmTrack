"""Mock Zoho CRM backed by the demo files (data/farmers.csv, data/mock_zoho/advisory_rows_flat.csv).

Reads are served from the seeded files. Writes go to JSONL files under `store_dir` and are NOT echoed back by get_history:
sprays the app logs live in the app database, and callers merge both sources (see app.integrations.history.merge_history).
"""
from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.clock import IST
from app.domain.types import FarmerProfile, SprayRecord
from app.integrations.normalise import normalise_phone
from app.integrations.reference import load_product_master, load_stations, read_csv
from app.integrations.zoho_rows import record_from_row

log = logging.getLogger(__name__)

_Data = tuple[dict[str, dict[str, str]], dict[str, list[SprayRecord]]]


class MockZohoAdapter:
    def __init__(self, data_dir: Path, store_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._store_dir = Path(store_dir)
        self._lock = threading.Lock()
        self._data: _Data | None = None

    # ------------------------------------------------------------------------------------------ loading
    def _load(self) -> _Data:
        with self._lock:
            if self._data is None:
                self._data = self._read_files()
            return self._data

    def _read_files(self) -> _Data:
        farmers = {r["farmer_id"]: r for r in read_csv(self._data_dir / "farmers.csv")}
        products = load_product_master(self._data_dir)
        history: dict[str, list[SprayRecord]] = defaultdict(list)
        skipped = 0
        for row in read_csv(self._data_dir / "mock_zoho" / "advisory_rows_flat.csv"):
            if row.get("row_kind") != "self_spray":
                continue
            record = record_from_row(row, products)
            if record is None:
                skipped += 1
                continue
            history[row["farmer_id"]].append(record)
        for records in history.values():
            records.sort(key=lambda r: r.sprayed_at)
        if skipped:
            log.warning("mock zoho: %d spray rows without a usable date were ignored", skipped)
        return farmers, dict(history)

    # ------------------------------------------------------------------------------------------ ZohoAdapter
    def get_farmer(self, farmer_id: str) -> FarmerProfile | None:
        row = self._load()[0].get(farmer_id)
        if row is None:
            return None
        station = load_stations(self._data_dir).get(row.get("station_id", ""))
        primary = row.get("primary_crop") or None
        crops = [c for c in [primary, *row.get("other_crops", "").split(";")] if c]
        elevation = row.get("orchard_elevation_m")
        return FarmerProfile(
            id=row["farmer_id"],
            name=row["name"],
            phone=normalise_phone(row.get("phone")),
            language="en" if row.get("preferred_language") == "en" else "hi",
            district=row.get("district") or None,
            village=row.get("village") or None,
            station_id=row.get("station_id") or None,
            elevation_m=float(elevation) if elevation else None,
            phenology_band=row.get("phenology_band") or None,
            crops=list(dict.fromkeys(crops)),
            primary_crop=primary,
            primary_variety=row.get("primary_variety") or None,
            zoho_contact_id=row.get("zoho_contact_id") or None,
            lat=station.lat if station else None,
            lon=station.lon if station else None,
        )

    def get_history(self, farmer_id: str, until: datetime | None = None) -> list[SprayRecord]:
        if until is not None and until.tzinfo is None:
            until = until.replace(tzinfo=IST)
        records = self._load()[1].get(farmer_id, [])
        return [r.model_copy() for r in records if until is None or r.sprayed_at <= until]

    def write_spray(self, farmer_id: str, record: SprayRecord) -> bool:
        return self._append("sprays.jsonl", farmer_id, record.model_dump(mode="json"))

    def write_diagnosis(self, farmer_id: str, payload: dict[str, Any]) -> bool:
        return self._append("diagnoses.jsonl", farmer_id, payload)

    # ------------------------------------------------------------------------------------------ storage
    def _append(self, filename: str, farmer_id: str, body: dict[str, Any]) -> bool:
        if farmer_id not in self._load()[0]:
            log.warning("mock zoho: write for unknown farmer %s refused", farmer_id)
            return False
        line = json.dumps({"farmer_id": farmer_id, "written_at": datetime.now(UTC).isoformat(), "data": body},
                          ensure_ascii=False, default=str)
        with self._lock:
            self._store_dir.mkdir(parents=True, exist_ok=True)
            with (self._store_dir / filename).open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return True
