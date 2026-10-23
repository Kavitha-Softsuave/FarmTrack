"""Image helpers for the upload tests."""
from __future__ import annotations

import io

from PIL import Image


def make_jpeg(color: tuple[int, int, int] = (60, 140, 60), size: tuple[int, int] = (320, 240), exif: bool = False,
              fmt: str = "JPEG") -> bytes:
    """A small real image. exif=True embeds an orientation tag and GPS data (to prove the upload path strips them)."""
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    if fmt == "JPEG" and exif:
        data = Image.Exif()
        data[0x0112] = 6                                          # orientation: rotate 90
        data[0x010F] = "FakeCameraMaker"
        data[0x8825] = {1: "N", 2: (31.0, 6.0, 30.0), 3: "E", 4: (77.0, 21.0, 36.0)}        # GPS IFD
        image.save(buffer, format="JPEG", exif=data)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


def photo_files(count: int = 1, **kwargs) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("photos", (f"leaf{i}.jpg", make_jpeg(**kwargs), "image/jpeg")) for i in range(count)]
