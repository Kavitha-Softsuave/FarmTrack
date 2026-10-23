from datetime import datetime, timedelta

from app.clock import IST
from app.config import Settings
from app.db.models import SprayLogRow
from app.domain.types import SprayRecord
from app.integrations.history import merge_history, records_from_spray_logs
from app.integrations.reference import load_product_master

PRODUCTS = load_product_master(Settings(_env_file=None).data_dir)
T0 = datetime(2026, 5, 1, 9, 30, tzinfo=IST)


def rec(minutes: int = 0, product_id: str | None = "P001", active: str | None = "Captan", source: str = "zoho") -> SprayRecord:
    return SprayRecord(sprayed_at=T0 + timedelta(minutes=minutes), product_id=product_id, active_ingredient=active, source=source)


def test_app_entry_already_in_zoho_is_counted_once():
    merged = merge_history([rec(source="zoho")], [rec(source="app")])
    assert len(merged) == 1 and merged[0].source == "zoho"


def test_same_minute_different_seconds_still_matches():
    app = rec(source="app")
    app.sprayed_at = app.sprayed_at.replace(second=42)
    assert len(merge_history([rec()], [app])) == 1


def test_different_product_or_time_is_kept_and_result_is_sorted():
    merged = merge_history([rec(10)], [rec(0, "P002", "Dodine", "app"), rec(10, "P002", "Dodine", "app"), rec(60, source="app")])
    assert [(m.product_id, m.sprayed_at) for m in merged] == [
        ("P002", T0), ("P001", T0 + timedelta(minutes=10)), ("P002", T0 + timedelta(minutes=10)), ("P001", T0 + timedelta(minutes=60))]


def test_free_text_entries_match_on_the_ingredient_name():
    zoho = [rec(0, None, "Captan")]
    app = [rec(0, None, "captan", "app")]
    assert len(merge_history(zoho, app)) == 1


def test_records_from_spray_logs_use_the_product_master_and_respect_until():
    rows = [
        SprayLogRow(farmer_id="F1", crop_id="Apple", product_id="P001", sprayed_at=T0, created_at=T0),
        SprayLogRow(farmer_id="F1", crop_id="Apple", product_id=None, free_text="Zinc, Boron", sprayed_at=T0, created_at=T0),
        SprayLogRow(farmer_id="F1", crop_id="Apple", product_id=None, free_text="Fenpropathrin 30% EC", product_name="Meothrin",
                    sprayed_at=T0 + timedelta(days=3), created_at=T0),
    ]
    records = records_from_spray_logs(rows, PRODUCTS, until=T0 + timedelta(days=1))
    assert len(records) == 2 and all(r.source == "app" for r in records)
    captan, nutrient = records
    assert captan.product_id == "P001" and captan.active_ingredient == "Captan" and captan.category == "fungicide"
    assert nutrient.nutrient is True
    assert len(records_from_spray_logs(rows, PRODUCTS)) == 3


def test_naive_database_datetimes_are_read_as_ist():
    row = SprayLogRow(farmer_id="F1", crop_id="Apple", product_id="P001", sprayed_at=T0.replace(tzinfo=None), created_at=T0)
    assert records_from_spray_logs([row], PRODUCTS)[0].sprayed_at == T0
