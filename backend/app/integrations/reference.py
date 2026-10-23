"""Cached loaders for the reference and demo data under settings.data_dir (plain CSV/JSON: no pandas in the app).

Everything returned here is read-only: do not mutate the cached objects.
"""
from __future__ import annotations

import csv
import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from app.integrations.normalise import normalise_frac


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


# ------------------------------------------------------------------------------------------------- product master
@dataclass(frozen=True)
class ProductRef:
    product_id: str
    crop: str
    active_ingredient: str
    active_ingredient_hi: str | None
    formulation: str | None
    brand_example: str | None
    category: str
    frac_irac_code: str | None
    stage: str | None
    targets: tuple[str, ...]
    dose_min: float | None
    dose_max: float | None
    dose_unit: str | None
    waiting_period_days: int | None
    ban_status: str

    @property
    def dose_text(self) -> str | None:
        if self.dose_min is None:
            return None
        low, high = _fmt_num(self.dose_min), _fmt_num(self.dose_max if self.dose_max is not None else self.dose_min)
        amount = low if low == high else f"{low}-{high}"
        return f"{amount} {self.dose_unit}".strip() if self.dose_unit else amount


def _fmt_num(value: float | None) -> str:
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


@lru_cache(maxsize=4)
def _product_master(data_dir: Path) -> Mapping[str, ProductRef]:
    out: dict[str, ProductRef] = {}
    for row in read_csv(data_dir / "reference" / "product_master.csv"):
        out[row["product_id"]] = ProductRef(
            product_id=row["product_id"],
            crop=row["crop"],
            active_ingredient=row["active_ingredient"],
            active_ingredient_hi=row.get("active_ingredient_hi") or None,
            formulation=row.get("formulation") or None,
            brand_example=row.get("brand_example") or None,
            category=row["category"],
            frac_irac_code=normalise_frac(row.get("frac_irac_code")),
            stage=row.get("stage") or None,
            targets=tuple(t for t in row.get("targets", "").split(";") if t),
            dose_min=_float(row.get("dose_min")),
            dose_max=_float(row.get("dose_max")),
            dose_unit=row.get("dose_unit") or None,
            waiting_period_days=_int(row.get("waiting_period_days")),
            ban_status=row.get("ban_status") or "registered",
        )
    return MappingProxyType(out)


def load_product_master(data_dir: Path) -> Mapping[str, ProductRef]:
    return _product_master(Path(data_dir))


# ------------------------------------------------------------------------------------------------- stations
@dataclass(frozen=True)
class Station:
    station_id: str
    village: str
    district: str
    lat: float
    lon: float
    grid_lat: float
    grid_lon: float
    elevation_m: float | None


@lru_cache(maxsize=4)
def _stations(data_dir: Path) -> Mapping[str, Station]:
    out: dict[str, Station] = {}
    for row in read_csv(data_dir / "weather" / "stations.csv"):
        lat, lon = float(row["lat_approx"]), float(row["lon_approx"])
        out[row["station_id"]] = Station(
            station_id=row["station_id"], village=row["village"], district=row["district"], lat=lat, lon=lon,
            grid_lat=_float(row.get("grid_lat")) or lat, grid_lon=_float(row.get("grid_lon")) or lon,
            elevation_m=_float(row.get("grid_elevation_m")),
        )
    return MappingProxyType(out)


def load_stations(data_dir: Path) -> Mapping[str, Station]:
    return _stations(Path(data_dir))


def nearest_station(stations: Mapping[str, Station], lat: float, lon: float) -> Station | None:
    """Closest station by equirectangular distance (good enough inside one Himalayan state)."""
    if not stations:
        return None
    scale = math.cos(math.radians(lat))
    return min(stations.values(), key=lambda s: (s.lat - lat) ** 2 + ((s.lon - lon) * scale) ** 2)


# ------------------------------------------------------------------------------------------------- stage calendar
@lru_cache(maxsize=4)
def _harvest_days(data_dir: Path) -> Mapping[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for row in read_csv(data_dir / "reference" / "stage_calendar.csv"):
        doy = _int(row.get("typical_doy"))
        if row["stage_id"] == "harvest" and doy is not None:
            out[(row["band_id"], row.get("cultivar", ""))] = doy
    return MappingProxyType(out)


def harvest_day_of_year(data_dir: Path, band: str | None, cultivar: str | None) -> int | None:
    """Estimated apple harvest day-of-year for an elevation band and cultivar (median of the band when the cultivar is unknown)."""
    if not band:
        return None
    days = _harvest_days(Path(data_dir))
    if cultivar and (band, cultivar) in days:
        return days[(band, cultivar)]
    in_band = [doy for (b, _), doy in days.items() if b == band]
    return int(statistics.median(in_band)) if in_band else None


# ------------------------------------------------------------------------------------------------- disease catalogue
@lru_cache(maxsize=4)
def _diseases(data_dir: Path) -> tuple[tuple[str, str], ...]:
    rows = read_csv(data_dir / "reference" / "disease_catalogue.csv")
    return tuple((r["disease_id"], r.get("name_en", "")) for r in rows)


def load_disease_options(data_dir: Path) -> tuple[tuple[str, str], ...]:
    """(disease_id, english name) pairs for the admin review form."""
    return _diseases(Path(data_dir))
