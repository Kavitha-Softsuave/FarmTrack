"""Photo upload validation through the HTTP API."""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db.models import ScanRow
from app.db.session import session_scope
from app.domain.types import QualityResult
from app.main import create_app
from tests.fakes import make_container
from tests.imaging import make_jpeg, photo_files


def scan(client, auth, files):
    return client.post("/v1/scans", files=files, headers=auth)


@pytest.fixture
def small_client(api_settings, fake_container, monkeypatch):
    """An app whose limits are 2 photos of at most 1 MB (so the body limit is 3 MB)."""
    settings = api_settings.model_copy(update={"max_upload_mb": 1, "max_photos_per_scan": 2})
    container = make_container(settings)
    application = create_app(settings, container_factory=lambda _s: container)
    application.state.container = container
    with TestClient(application, raise_server_exceptions=False) as client:
        body = client.post("/v1/auth/otp/request", json={"phone": "+910000000001"}).json()
        token = client.post("/v1/auth/otp/verify", json={"request_id": body["request_id"], "otp": body["dev_otp"]}).json()
        yield client, {"Authorization": f"Bearer {token['access_token']}"}


def test_exif_gps_is_stripped_from_the_stored_photo(api_client, auth, api_settings):
    raw = make_jpeg(exif=True)
    assert b"FakeCameraMaker" in raw
    body = scan(api_client, auth, [("photos", ("leaf.jpg", raw, "image/jpeg"))]).json()
    with session_scope() as db:
        path = api_settings.storage_dir / db.get(ScanRow, body["id"]).photo_paths[0]
    stored = path.read_bytes()
    assert b"FakeCameraMaker" not in stored and b"Exif" not in stored
    image = Image.open(io.BytesIO(stored))
    assert image.format == "JPEG" and len(image.getexif()) == 0


def test_the_vision_models_receive_the_cleaned_jpeg_not_the_upload(api_client, auth, fake_container):
    seen = []
    fake_container.quality.check = lambda data: seen.append(data) or QualityResult(usable=True)
    png = io.BytesIO()
    Image.new("RGB", (64, 64), "green").save(png, format="PNG")
    assert scan(api_client, auth, [("photos", ("leaf.png", png.getvalue(), "image/png"))]).status_code == 200
    assert seen[0][:3] == b"\xff\xd8\xff"


@pytest.mark.parametrize("name,payload,mime", [
    ("notes.txt", b"hello world", "text/plain"),
    ("fake.jpg", b"definitely not a jpeg", "image/jpeg"),
    ("doc.pdf", b"%PDF-1.4 something", "application/pdf"),
    ("empty.jpg", b"", "image/jpeg"),
    ("script.jpg", b"<script>alert(1)</script>", "image/jpeg"),
])
def test_non_images_are_rejected_with_400(api_client, auth, name, payload, mime):
    response = scan(api_client, auth, [("photos", (name, payload, mime))])
    assert response.status_code == 400 and response.json()["code"] == "invalid_image"
    with session_scope() as db:
        assert db.scalars(select(ScanRow)).all() == []


def test_a_good_photo_next_to_a_bad_one_rejects_the_whole_request(api_client, auth):
    files = photo_files(1) + [("photos", ("bad.jpg", b"junk", "image/jpeg"))]
    response = scan(api_client, auth, files)
    assert response.status_code == 400 and response.json()["details"]["index"] == 1


def test_gif_is_rejected(api_client, auth):
    gif = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(gif, format="GIF")
    assert scan(api_client, auth, [("photos", ("a.gif", gif.getvalue(), "image/gif"))]).status_code == 400


def test_too_many_photos_is_400(api_client, auth):
    response = scan(api_client, auth, photo_files(5))
    assert response.status_code == 400 and response.json()["code"] == "too_many_photos"
    assert response.json()["details"] == {"max_photos": 4}
    assert scan(api_client, auth, photo_files(4)).status_code == 200


def test_no_photos_is_a_validation_error(api_client, auth):
    assert api_client.post("/v1/scans", headers=auth).status_code == 422
    assert api_client.post("/v1/scans", data={"client_crop": "Apple"}, headers=auth).status_code == 422


def test_an_oversized_photo_is_413(small_client):
    client, auth = small_client
    big = b"\xff\xd8\xff" + b"0" * (1024 * 1024 + 100)                    # 1 MB + a bit, under the 3 MB body limit
    response = scan(client, auth, [("photos", ("big.jpg", big, "image/jpeg"))])
    assert response.status_code == 413 and response.json()["code"] == "photo_too_large"


def test_an_oversized_body_is_rejected_before_parsing(small_client):
    client, auth = small_client
    response = client.post("/v1/scans", content=b"x" * (4 * 1024 * 1024), headers={**auth, "content-type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413 and response.json()["code"] == "payload_too_large"


def test_a_streamed_body_without_content_length_is_cut_off(small_client):
    client, auth = small_client
    crlf = b"\r\n"

    def multipart_stream():                                              # valid multipart, 6.5 MB, chunked transfer encoding
        yield (b"--B" + crlf + b'Content-Disposition: form-data; name="photos"; filename="a.jpg"' + crlf
               + b"Content-Type: image/jpeg" + crlf + crlf)
        for _ in range(100):
            yield b"x" * 65536
        yield crlf + b"--B--" + crlf

    response = client.post("/v1/scans", content=multipart_stream(), headers={**auth, "content-type": "multipart/form-data; boundary=B"})
    assert response.status_code == 413 and response.json()["code"] == "payload_too_large"


def test_json_bodies_have_a_much_smaller_limit_than_photo_uploads(api_client, auth):
    big = '{"question": "' + "x" * (2 * 1024 * 1024) + '"}'
    response = api_client.post("/v1/ask", content=big, headers={**auth, "content-type": "application/json"})
    assert response.status_code == 413 and response.json()["details"] == {"max_bytes": 1024 * 1024}


def test_photo_limit_follows_the_setting(small_client):
    client, auth = small_client
    assert scan(client, auth, photo_files(3)).json()["code"] == "too_many_photos"
    assert scan(client, auth, photo_files(2)).status_code == 200


def test_decompression_bomb_dimensions_are_rejected(api_client, auth, monkeypatch):
    import app.security.uploads as uploads

    monkeypatch.setattr(uploads, "MAX_PIXELS", 100)
    response = scan(api_client, auth, photo_files(1, size=(50, 50)))
    assert response.status_code == 400 and response.json()["code"] == "image_too_large_dimensions"
