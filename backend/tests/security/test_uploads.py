import io

import pytest
from fastapi import UploadFile
from PIL import Image

from app.security.errors import ApiError
from app.security.uploads import MAX_LONG_EDGE, process_uploads, read_limited, sanitize_image
from tests.fakes import plain_settings
from tests.imaging import make_jpeg


def upload(data: bytes, name: str = "p.jpg") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


def test_exif_and_gps_are_stripped_and_orientation_applied():
    raw = make_jpeg(size=(320, 240), exif=True)
    assert b"FakeCameraMaker" in raw and Image.open(io.BytesIO(raw)).getexif().get(0x8825)       # precondition: the input has GPS
    clean = sanitize_image(raw)
    out = Image.open(io.BytesIO(clean.data))
    assert out.format == "JPEG"
    assert len(out.getexif()) == 0 and "exif" not in out.info
    assert b"FakeCameraMaker" not in clean.data and b"Exif" not in clean.data
    assert (clean.width, clean.height) == (240, 320)                    # orientation 6 rotated the pixels, then the tag was dropped


def test_png_is_reencoded_as_jpeg_and_alpha_is_flattened_onto_white():
    image = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    clean = sanitize_image(buffer.getvalue())
    out = Image.open(io.BytesIO(clean.data))
    assert out.format == "JPEG" and out.mode == "RGB"
    assert min(out.getpixel((25, 25))) > 240


def test_large_photo_is_downscaled():
    clean = sanitize_image(make_jpeg(size=(4000, 3000)))
    assert max(clean.width, clean.height) == MAX_LONG_EDGE


@pytest.mark.parametrize("payload", [b"not an image at all", b"%PDF-1.7 fake", b"GIF89a\x01\x00\x01\x00", b"<svg xmlns='x'/>", b""])
def test_non_images_are_rejected(payload):
    with pytest.raises(ApiError) as caught:
        sanitize_image(payload)
    assert caught.value.status_code == 400 and caught.value.code == "invalid_image"


def test_gif_and_webp_are_not_accepted_even_when_valid():
    for fmt in ("GIF", "WEBP", "BMP"):
        buffer = io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(buffer, format=fmt)
        with pytest.raises(ApiError):
            sanitize_image(buffer.getvalue())


def test_truncated_jpeg_is_rejected():
    raw = make_jpeg(size=(800, 600))
    with pytest.raises(ApiError):
        sanitize_image(raw[: len(raw) // 2])


def test_pixel_bomb_is_rejected(monkeypatch):
    import app.security.uploads as uploads

    monkeypatch.setattr(uploads, "MAX_PIXELS", 1000)
    with pytest.raises(ApiError) as caught:
        sanitize_image(make_jpeg(size=(100, 100)))
    assert caught.value.code == "image_too_large_dimensions"


def test_read_limited_stops_at_the_limit():
    with pytest.raises(ApiError) as caught:
        read_limited(upload(b"x" * 5000), 4096)
    assert caught.value.status_code == 413 and caught.value.code == "photo_too_large"
    assert read_limited(upload(b"x" * 4096), 4096) == b"x" * 4096


def test_process_uploads_enforces_count_size_and_content():
    settings = plain_settings(max_photos_per_scan=2, max_upload_mb=1)
    good = make_jpeg()
    assert len(process_uploads([upload(good), upload(good)], settings)) == 2
    with pytest.raises(ApiError) as caught:
        process_uploads([], settings)
    assert caught.value.code == "no_photos"
    with pytest.raises(ApiError) as caught:
        process_uploads([upload(good)] * 3, settings)
    assert caught.value.code == "too_many_photos"
    with pytest.raises(ApiError) as caught:
        process_uploads([upload(good), upload(good)], settings, already_stored=1)
    assert caught.value.code == "too_many_photos"
    with pytest.raises(ApiError) as caught:
        process_uploads([upload(good), upload(b"junk")], settings)
    assert caught.value.code == "invalid_image" and caught.value.details["index"] == 1
    with pytest.raises(ApiError) as caught:
        process_uploads([upload(b"\xff\xd8" + b"0" * (1024 * 1024 + 10))], settings)
    assert caught.value.status_code == 413
