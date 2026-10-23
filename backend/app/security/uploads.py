"""Photo upload validation. Accept real JPEG/PNG only, decode with Pillow, re-encode to JPEG and drop all metadata.

Re-encoding strips EXIF (including GPS), ICC profiles and PNG text chunks, and neutralises polyglot or malformed files.
The camera's EXIF orientation is applied to the pixels first so photos are not stored sideways.
"""
from __future__ import annotations

import io
import threading
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.security.errors import ApiError

ALLOWED_FORMATS = ("JPEG", "PNG")
MAX_PIXELS = 40_000_000          # decompression-bomb guard (a 12 MP phone photo is 12 million)
MAX_LONG_EDGE = 2048
JPEG_QUALITY = 88
_CHUNK = 1024 * 1024

ImageFile.LOAD_TRUNCATED_IMAGES = False


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    width: int
    height: int


def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks and stop as soon as it exceeds `max_bytes`."""
    buffer = bytearray()
    while chunk := upload.file.read(_CHUNK):
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise ApiError(413, "photo_too_large", f"A photo is larger than {max_bytes // (1024 * 1024)} MB.",
                           {"max_bytes": max_bytes})
    return bytes(buffer)


# A small file can decode into a very large picture (a 130 KB PNG of 40 megapixels needs ~250 MB and ~0.8 s). Without a bound a
# handful of parallel uploads exhausts the memory of the whole API process, so only a few images are decoded at the same time
# (the others wait their turn in their own request thread).
MAX_PARALLEL_DECODES = 3
_decode_slots = threading.BoundedSemaphore(MAX_PARALLEL_DECODES)


def sanitize_image(raw: bytes) -> CleanImage:
    with _decode_slots:
        return _sanitize_image(raw)


def _sanitize_image(raw: bytes) -> CleanImage:
    try:
        with Image.open(io.BytesIO(raw), formats=ALLOWED_FORMATS) as img:
            if img.width * img.height > MAX_PIXELS:
                raise ApiError(400, "image_too_large_dimensions", "The photo has too many pixels.")
            img.load()
            oriented = ImageOps.exif_transpose(img)
            rgb = _to_rgb(oriented, owned=oriented is not img)
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ApiError(400, "invalid_image", "Upload a JPEG or PNG photo.") from exc
    rgb.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)      # no exif=/icc_profile= argument: metadata dropped
    return CleanImage(out.getvalue(), rgb.width, rgb.height)


def _to_rgb(img: Image.Image, owned: bool = False) -> Image.Image:
    """`owned`: `img` is already a private copy (not the file-backed original), so an RGB picture needs no second copy."""
    if img.mode == "RGB":
        return img if owned else img.copy()
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img.convert("RGB")


def process_uploads(files: list[UploadFile], settings: Settings, already_stored: int = 0) -> list[CleanImage]:
    """Validate a batch: count, size, decodability. `already_stored` counts photos the scan already has (add-photos)."""
    if not files:
        raise ApiError(400, "no_photos", "Send at least one photo.")
    if len(files) + already_stored > settings.max_photos_per_scan:
        raise ApiError(400, "too_many_photos", f"A scan can have at most {settings.max_photos_per_scan} photos.",
                       {"max_photos": settings.max_photos_per_scan})
    max_bytes = settings.max_upload_mb * 1024 * 1024
    cleaned: list[CleanImage] = []
    for index, upload in enumerate(files):
        raw = read_limited(upload, max_bytes)
        if not raw:
            raise ApiError(400, "invalid_image", "A photo is empty.", {"index": index})
        try:
            cleaned.append(sanitize_image(raw))
        except ApiError as exc:
            raise ApiError(exc.status_code, exc.code, exc.message, {**(exc.details or {}), "index": index}) from exc
    return cleaned
