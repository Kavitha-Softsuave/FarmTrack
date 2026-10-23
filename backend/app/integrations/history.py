"""Spray-history helpers shared by the alert evaluator and any caller that merges Zoho history with the app's own diary."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from app.db.models import SprayLogRow, as_ist
from app.domain.types import SprayRecord
from app.integrations.reference import ProductRef
from app.integrations.zoho_rows import build_record


def records_from_spray_logs(rows: Iterable[SprayLogRow], products: Mapping[str, ProductRef],
                            until: datetime | None = None) -> list[SprayRecord]:
    """App diary rows -> SprayRecord(source='app'), never dated after `until`."""
    out: list[SprayRecord] = []
    for row in rows:
        when = as_ist(row.sprayed_at)
        if when is None or (until is not None and when > until):
            continue
        text = row.free_text or row.product_name
        out.append(build_record(when, text, None, row.product_name, products.get(row.product_id or ""), source="app"))
    return out


def _fingerprint(record: SprayRecord) -> tuple:
    return (record.sprayed_at.replace(second=0, microsecond=0), record.product_id or (record.active_ingredient or "").lower())


def merge_history(zoho: Iterable[SprayRecord], app: Iterable[SprayRecord]) -> list[SprayRecord]:
    """Zoho + app diary, oldest first. An app entry already written to Zoho (same minute, same product) is counted once."""
    merged = list(zoho)
    seen = {_fingerprint(r) for r in merged}
    for record in app:
        key = _fingerprint(record)
        if key not in seen:
            merged.append(record)
            seen.add(key)
    return sorted(merged, key=lambda r: r.sprayed_at)
