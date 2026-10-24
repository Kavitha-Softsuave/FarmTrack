"""Admin training photos: labelled leaf photos uploaded by staff, kept on the backend for later model training.

Every photo goes through the same checks as a farmer's scan photo (`app.security.uploads`): size limit (MAX_UPLOAD_MB), real image
sniffing by decoding with Pillow (the file name, extension and Content-Type header are never trusted), pixel limit, metadata removal.
The stored file is the cleaned JPEG (long edge at most 2048 px, no EXIF/GPS), named after its own SHA-256, so an upload name can never
become a path. A second upload of the same picture is reported as a duplicate and not stored again.

Layout on disk: <storage_dir>/training_uploads/<class>/<sha16>.jpg ; "write into the training folder" copies to
<training_export_dir>/<class>/adm_<sha16>.jpg (the data/training/photos/<class>/ layout) and appends to ../admin_uploads.csv.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.service import write_audit
from app.config import Settings
from app.db.models import TrainingPhotoRow
from app.security.errors import ApiError
from app.security.paths import UnsafePathError, safe_join
from app.security.uploads import read_limited, sanitize_image

MAX_FILES_PER_UPLOAD = 20
CLASS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$")
FIELD_LIMITS = {"crop": 40, "leaf_id": 60, "source": 200, "licence": 80, "confirmed_by": 80}
MAIN_APPLE_CLASSES = ("Apple___Apple_scab", "Apple___Marssonina_blotch", "Apple___Alternaria_leaf_spot", "Apple___healthy")
OTHER = "__other__"                                   # the form value that means "use the free class name"
SOURCES_CSV_FIELDS = ["file", "class", "source_url", "licence", "author", "note"]
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_NAME_KEEP = re.compile(r"[^A-Za-z0-9._ -]")


class TrainingError(ValueError):
    """A problem with the form values (never with a single file: those are reported per file)."""


@dataclass(frozen=True)
class FileResult:
    name: str
    status: str                  # stored | duplicate | rejected
    message: str


@dataclass(frozen=True)
class UploadMeta:
    class_label: str
    crop: str | None
    leaf_id: str | None
    source: str | None
    licence: str | None
    confirmed_by: str | None


def safe_name(raw: str | None) -> str:
    """A display-only version of an uploaded file name: no directories, no control characters, a short harmless character set."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = _NAME_KEEP.sub("_", _CONTROL.sub("", name)).strip(" .")
    return (name or "photo")[:120]


def clean_text(value: str | None, field: str) -> str | None:
    text = _CONTROL.sub(" ", value or "").strip()
    if len(text) > FIELD_LIMITS[field]:
        raise TrainingError(f"{field} is too long (at most {FIELD_LIMITS[field]} characters)")
    return text or None


def class_options(disease_options: tuple[tuple[str, str], ...]) -> list[tuple[str, str]]:
    """(folder name, label) for the class drop-down: the four main apple classes first, then the other catalogue entries."""
    names = dict(disease_options)
    main = [(c, names.get(c, c)) for c in MAIN_APPLE_CLASSES]
    rest = [(c, label) for c, label in disease_options if c not in MAIN_APPLE_CLASSES]
    return main + sorted(rest)


def resolve_class(choice: str, other: str, known: set[str]) -> str:
    """The class folder name from the form: a catalogue id, or a free name when the choice is OTHER. Anything else is refused."""
    if choice == OTHER:
        label = re.sub(r"\s+", "_", other.strip())
        if not CLASS_RE.match(label):
            raise TrainingError("The other class name needs 1-60 characters: letters, digits, underscore, hyphen")
        return label
    if choice not in known or not CLASS_RE.match(choice):
        raise TrainingError("Choose a class from the list")
    return choice


def build_meta(class_label: str, form: dict[str, str]) -> UploadMeta:
    return UploadMeta(class_label, *(clean_text(form.get(k), k) for k in ("crop", "leaf_id", "source", "licence", "confirmed_by")))


def _root(settings: Settings) -> Path:
    return settings.storage_dir / "training_uploads"


def store_uploads(db: Session, settings: Settings, files: list[UploadFile], meta: UploadMeta, now: datetime) -> list[FileResult]:
    """Validate and store each file. One bad file never stops the others; every outcome is reported."""
    if not files or not any((f.filename or "") for f in files):
        raise TrainingError("Choose at least one photo")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise TrainingError(f"At most {MAX_FILES_PER_UPLOAD} photos per upload: send the rest in another batch")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    results: list[FileResult] = []
    for upload in files:
        name = safe_name(upload.filename)
        try:
            raw = read_limited(upload, max_bytes)
            if not raw:
                raise ApiError(400, "invalid_image", "The file is empty.")
            image = sanitize_image(raw)
        except ApiError as exc:
            results.append(FileResult(name, "rejected", exc.message))
            continue
        results.append(_store_one(db, settings, name, image.data, image.width, image.height, meta, now))
    db.commit()
    return results


def _store_one(db: Session, settings: Settings, name: str, data: bytes, width: int, height: int, meta: UploadMeta,
               now: datetime) -> FileResult:
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalars(select(TrainingPhotoRow).where(TrainingPhotoRow.sha256 == digest)).first()
    if existing is not None:
        return FileResult(name, "duplicate", f"Already stored under {existing.class_label}.")
    relative = f"training_uploads/{meta.class_label}/{digest[:16]}.jpg"
    try:
        target = safe_join(settings.storage_dir, *relative.split("/"))
    except UnsafePathError:
        return FileResult(name, "rejected", "The class name is not allowed.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    try:
        with db.begin_nested():
            row = TrainingPhotoRow(class_label=meta.class_label, crop=meta.crop, leaf_id=meta.leaf_id, source=meta.source,
                                   licence=meta.licence, confirmed_by=meta.confirmed_by, original_name=name, sha256=digest,
                                   path=relative, width=width, height=height, size_bytes=len(data), created_at=now)
            db.add(row)
            db.flush()
            write_audit(db, "training.upload", "training_photo", row.id,
                        {"class": meta.class_label, "sha256": digest[:16], "bytes": len(data), "confirmed_by": meta.confirmed_by})
    except IntegrityError:                                     # a twin request stored the same picture a moment ago
        return FileResult(name, "duplicate", "Already stored.")
    return FileResult(name, "stored", f"Stored under {meta.class_label}.")


# ------------------------------------------------------------------------------------------------- list, show, delete
def class_counts(db: Session) -> list[tuple[str, int]]:
    rows = db.execute(select(TrainingPhotoRow.class_label, func.count()).group_by(TrainingPhotoRow.class_label)
                      .order_by(TrainingPhotoRow.class_label)).all()
    return [(label, int(n)) for label, n in rows]


def list_photos(db: Session, class_label: str = "", limit: int = 60, offset: int = 0) -> list[TrainingPhotoRow]:
    stmt = select(TrainingPhotoRow).order_by(TrainingPhotoRow.created_at.desc(), TrainingPhotoRow.id)
    if class_label:
        stmt = stmt.where(TrainingPhotoRow.class_label == class_label)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


def count_photos(db: Session, class_label: str = "") -> int:
    stmt = select(func.count()).select_from(TrainingPhotoRow)
    if class_label:
        stmt = stmt.where(TrainingPhotoRow.class_label == class_label)
    return int(db.scalar(stmt) or 0)


def photo_path(db: Session, settings: Settings, photo_id: str) -> Path | None:
    row = db.get(TrainingPhotoRow, photo_id)
    if row is None:
        return None
    try:
        path = safe_join(settings.storage_dir, *row.path.split("/"))
    except UnsafePathError:
        return None
    return path if path.is_file() else None


def delete_photo(db: Session, settings: Settings, photo_id: str) -> bool:
    row = db.get(TrainingPhotoRow, photo_id)
    if row is None:
        return False
    try:
        safe_join(settings.storage_dir, *row.path.split("/")).unlink(missing_ok=True)
    except (UnsafePathError, OSError):
        pass                                                   # the record goes anyway; a stray file is harmless and unreachable
    write_audit(db, "training.delete", "training_photo", row.id, {"class": row.class_label, "sha256": row.sha256[:16]})
    db.delete(row)
    db.commit()
    return True


# ------------------------------------------------------------------------------------------------- export
def _csv_text(rows: list[TrainingPhotoRow], file_for: dict[str, str]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(SOURCES_CSV_FIELDS)
    for r in rows:
        note = "; ".join(p for p in (f"crop={r.crop}" if r.crop else "", f"leaf_id={r.leaf_id}" if r.leaf_id else "",
                                     "admin upload") if p)
        writer.writerow([file_for[r.id], r.class_label, r.source or "", r.licence or "", r.confirmed_by or "", note])
    return out.getvalue()


def export_zip(db: Session, settings: Settings, class_label: str = "") -> Path:
    """A ZIP (<class>/<file>.jpg + sources.csv) in a temporary file; the caller deletes it after sending."""
    rows = list_photos(db, class_label, limit=100_000)
    handle = tempfile.NamedTemporaryFile(prefix="training-", suffix=".zip", delete=False)  # noqa: SIM115
    handle.close()
    names: dict[str, str] = {}
    with zipfile.ZipFile(handle.name, "w", zipfile.ZIP_STORED) as archive:
        for row in rows:
            source = photo_path(db, settings, row.id)
            if source is None:
                continue
            names[row.id] = f"{row.class_label}/adm_{row.sha256[:16]}.jpg"
            archive.write(source, names[row.id])
        archive.writestr("sources.csv", _csv_text([r for r in rows if r.id in names], names))
    write_audit(db, "training.export_zip", detail={"photos": len(names), "class": class_label or "all"})
    db.commit()
    return Path(handle.name)


def export_to_folder(db: Session, settings: Settings, now: datetime) -> tuple[int, int]:
    """Copy every photo not yet written into <training_export_dir>/<class>/ (existing files are left alone).
    Returns (copied, already_there)."""
    target_root = settings.training_export_dir
    copied = already = 0
    new_rows: list[TrainingPhotoRow] = []
    files: dict[str, str] = {}
    for row in list_photos(db, limit=1_000_000):
        source = photo_path(db, settings, row.id)
        if source is None:
            continue
        relative = f"{row.class_label}/adm_{row.sha256[:16]}.jpg"
        try:
            target = safe_join(target_root, *relative.split("/"))
        except UnsafePathError:
            continue
        if target.exists():
            already += 1
            if row.exported_at is None:
                row.exported_at = now
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        row.exported_at = now
        copied += 1
        new_rows.append(row)
        files[row.id] = relative
    if new_rows:
        log_path = target_root.parent / "admin_uploads.csv"
        fresh = not log_path.exists()
        body = _csv_text(new_rows, files)
        with log_path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(body if fresh else body.split("\n", 1)[1])
    write_audit(db, "training.export_folder", detail={"copied": copied, "already_there": already})
    db.commit()
    return copied, already
