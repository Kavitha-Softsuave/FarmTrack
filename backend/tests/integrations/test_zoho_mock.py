import csv
import json
import re
from datetime import datetime

import pytest

from app.clock import IST
from app.config import Settings
from app.domain.types import SprayRecord
from app.integrations.reference import load_product_master
from app.integrations.zoho_mock import MockZohoAdapter
from app.integrations.zoho_rows import is_nutrient_text, parse_active_ingredient, record_from_row

DATA = Settings(_env_file=None).data_dir
ROWS = list(csv.DictReader((DATA / "mock_zoho" / "advisory_rows_flat.csv").open(encoding="utf-8-sig")))
PRODUCTS = load_product_master(DATA)


@pytest.fixture(scope="module")
def zoho(tmp_path_factory) -> MockZohoAdapter:
    return MockZohoAdapter(DATA, tmp_path_factory.mktemp("zoho_store"))


def _busiest_farmer() -> str:
    counts: dict[str, int] = {}
    for row in ROWS:
        if row["row_kind"] == "self_spray":
            counts[row["farmer_id"]] = counts.get(row["farmer_id"], 0) + 1
    return max(counts, key=counts.__getitem__)


BUSY = _busiest_farmer()


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=IST)


# ------------------------------------------------------------------------------------------------- farmers
def test_get_farmer_normalises_phone_and_maps_fields(zoho):
    farmer = zoho.get_farmer("F008")
    assert farmer is not None
    assert farmer.phone == "+910000000008"
    assert (farmer.station_id, farmer.phenology_band, farmer.primary_crop) == ("ST02", "B1", "Apple")
    assert farmer.crops == ["Apple"] and farmer.language == "en"
    assert farmer.lat == pytest.approx(31.31) and farmer.lon == pytest.approx(77.46)    # station coordinates


def test_get_farmer_unknown_is_none(zoho):
    assert zoho.get_farmer("F999") is None


def test_multi_crop_farmer(zoho):
    rows = list(csv.DictReader((DATA / "farmers.csv").open(encoding="utf-8-sig")))
    multi = next(r for r in rows if r["other_crops"])
    farmer = zoho.get_farmer(multi["farmer_id"])
    assert farmer.crops[0] == multi["primary_crop"]
    assert set(farmer.crops) == {multi["primary_crop"], *multi["other_crops"].split(";")}


# ------------------------------------------------------------------------------------------------- history
def test_history_never_after_until(zoho):
    full = zoho.get_history(BUSY)
    assert len(full) > 5
    cutoff = full[4].sprayed_at
    clipped = zoho.get_history(BUSY, cutoff)
    assert clipped and all(r.sprayed_at <= cutoff for r in clipped)
    assert len(clipped) < len(full)
    assert zoho.get_history(BUSY, full[0].sprayed_at.replace(year=2020)) == []


def test_history_until_boundary_is_inclusive_and_naive_means_ist(zoho):
    first = zoho.get_history(BUSY)[0]
    assert zoho.get_history(BUSY, first.sprayed_at)[0].sprayed_at == first.sprayed_at
    naive = first.sprayed_at.replace(tzinfo=None)
    assert len(zoho.get_history(BUSY, naive)) == len(zoho.get_history(BUSY, first.sprayed_at))


def test_history_is_sorted_even_when_rows_are_not(zoho):
    for fid in {r["farmer_id"] for r in ROWS}:
        times = [r.sprayed_at for r in zoho.get_history(fid)]
        assert times == sorted(times)


def test_advisor_rows_are_ignored(zoho):
    self_spray = [r for r in ROWS if r["row_kind"] == "self_spray"]
    advisors = [r for r in ROWS if r["row_kind"] == "advisor"]
    assert advisors, "the demo data must contain advisor rows for this test to mean anything"
    total = sum(len(zoho.get_history(fid)) for fid in {r["farmer_id"] for r in ROWS})
    assert total == len(self_spray)


def test_dated_by_spray_datetime_helper(zoho):
    row = next(r for r in ROWS if r["row_kind"] == "self_spray" and r["_product_id"])
    expected = at(row["_spray_datetime"])
    assert expected in {r.sprayed_at for r in zoho.get_history(row["farmer_id"])}


def test_product_id_maps_to_product_master(zoho):
    records = [r for r in zoho.get_history("F008") if r.product_id]
    assert records
    for record in records:
        product = PRODUCTS[record.product_id]
        assert record.active_ingredient == product.active_ingredient
        assert record.frac_irac_code == product.frac_irac_code
        assert record.category == product.category


def test_frac_values_are_normalised_everywhere(zoho):
    codes = [r.frac_irac_code for fid in {x["farmer_id"] for x in ROWS} for r in zoho.get_history(fid) if r.frac_irac_code]
    assert codes
    for code in codes:
        assert " " not in code and not code.upper().startswith("IRAC")
        assert not re.search(r"(^|\+)M\d($|\+)", code), f"short M code left in {code}"


def test_s5_off_label_rows_are_parsed_from_free_text(zoho):
    history = {r.trade_name: r for r in zoho.get_history("F008") if r.product_id is None}
    assert set(history) == {"Meothrin", "Syngenta Miravis Duo", "Trot"}
    meothrin, miravis, trot = history["Meothrin"], history["Syngenta Miravis Duo"], history["Trot"]
    assert (meothrin.active_ingredient, meothrin.frac_irac_code, meothrin.category) == ("Fenpropathrin", "3A", "insecticide")
    assert (miravis.active_ingredient, miravis.frac_irac_code, miravis.category) == (
        "Pydiflumetofen + Difenoconazole", "7+3", "fungicide")
    assert (trot.active_ingredient, trot.frac_irac_code, trot.category) == ("Thiamethoxam", "4A", "insecticide")
    assert not any(r.nutrient for r in history.values())
    assert miravis.sprayed_at == at("2026-06-28T09:30:00")


def test_s9_nutrients_are_flagged_and_not_given_a_group(zoho):
    on_day = [r for r in zoho.get_history("F011") if r.sprayed_at.date().isoformat() == "2026-04-14"]
    by_text = {r.active_ingredient: r for r in on_day}
    assert {"Carbendazim", "Zinc, Boron", "12.61.00"} <= set(by_text)
    assert by_text["Carbendazim"].nutrient is False and by_text["Carbendazim"].frac_irac_code == "1"
    for name in ("Zinc, Boron", "12.61.00"):
        record = by_text[name]
        assert record.nutrient is True
        assert record.frac_irac_code is None and record.category is None and record.product_id is None


def test_every_nutrient_row_in_the_data_is_flagged(zoho):
    nutrient_rows = [r for r in ROWS if r["row_kind"] == "self_spray" and r["_nutrient"] == "true"]
    assert nutrient_rows
    for row in nutrient_rows:
        record = record_from_row(row, PRODUCTS)
        assert record is not None and record.nutrient, row["Self_Sprayed"]


def test_rain_since_last_spray_is_read_when_present(zoho):
    row = next(r for r in ROWS if r["row_kind"] == "self_spray" and r["Total_Rainfall_Since_Last_Spray"])
    record = record_from_row(row, PRODUCTS)
    assert record.rain_mm_since == pytest.approx(float(row["Total_Rainfall_Since_Last_Spray"]))
    blank = next(r for r in ROWS if r["row_kind"] == "self_spray" and not r["Total_Rainfall_Since_Last_Spray"])
    assert record_from_row(blank, PRODUCTS).rain_mm_since is None


def test_row_without_iso_helper_falls_back_to_the_typed_date():
    row = {"row_kind": "self_spray", "Self_Spray_Dt": "14/04/2026", "Self_Sprayed": "Carbendazim", "Self_Spray_Frac_Group": "1"}
    record = record_from_row(row, PRODUCTS)
    assert record.sprayed_at == at("2026-04-14T12:00:00")
    assert record_from_row({"row_kind": "self_spray", "Self_Sprayed": "x"}, PRODUCTS) is None      # no usable date
    assert record_from_row({**row, "row_kind": "advisor"}, PRODUCTS) is None


def test_history_returns_copies(zoho):
    zoho.get_history(BUSY)[0].nutrient = True
    assert zoho.get_history(BUSY)[0].nutrient is False


@pytest.mark.parametrize("text,expected", [
    ("Fenpropathrin 30% EC", "Fenpropathrin"),
    ("Thiamethoxam 30% FS", "Thiamethoxam"),
    ("Pydiflumetofen 6.89% SC Difenoconazole 11.49% SC", "Pydiflumetofen + Difenoconazole"),
    ("Carbendazim 12% + Mancozeb 63% WP", "Carbendazim + Mancozeb"),
    ("hexaconazole + zineb", "Hexaconazole + Zineb"),
    ("captan 50 WP", "Captan"),
    ("Ziram 27% SC", "Ziram"),
    ("thiophanate-methyl", "Thiophanate-methyl"),
    ("", None),
    (None, None),
])
def test_parse_active_ingredient(text, expected):
    assert parse_active_ingredient(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Zinc, Boron", True), ("12.61.00", True), ("12-61-00", True), ("12 61 00", True), ("Urea", True), ("urea 5% floor spray", True),
    ("Calcium nitrate", True), ("19.19.19", True), ("Carbendazim", False), ("Zineb", False), ("Ziram 27% SC", False),
    ("Mancozeb 75 WP", False), ("", False), (None, False),
])
def test_is_nutrient_text(text, expected):
    assert is_nutrient_text(text) is expected


# ------------------------------------------------------------------------------------------------- writes
def test_writes_append_jsonl_and_are_not_echoed_by_history(tmp_path):
    zoho = MockZohoAdapter(DATA, tmp_path / "store")
    record = SprayRecord(sprayed_at=at("2026-05-12T09:00:00"), product_id="P001", active_ingredient="Captan", source="app")
    before = len(zoho.get_history("F001"))
    assert zoho.write_spray("F001", record) is True
    assert zoho.write_spray("F001", record) is True
    assert zoho.write_diagnosis("F001", {"scan_id": "s1", "disease_id": "Apple___Apple_scab", "note": "नमस्ते"}) is True
    lines = (tmp_path / "store" / "sprays.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["farmer_id"] == "F001" and first["data"]["product_id"] == "P001"
    diagnosis = json.loads((tmp_path / "store" / "diagnoses.jsonl").read_text(encoding="utf-8"))
    assert diagnosis["data"]["note"] == "नमस्ते"
    assert len(zoho.get_history("F001")) == before


def test_write_for_unknown_farmer_is_refused(tmp_path):
    zoho = MockZohoAdapter(DATA, tmp_path / "store")
    record = SprayRecord(sprayed_at=at("2026-05-12T09:00:00"))
    assert zoho.write_spray("F999", record) is False
    assert zoho.write_diagnosis("F999", {}) is False
    assert not (tmp_path / "store").exists()
