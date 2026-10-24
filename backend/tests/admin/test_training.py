"""Admin training photos: upload, validation, dedupe, list/preview/delete, ZIP and folder export, farmer photo list, voice page."""
import io
import re
import zipfile
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.admin import training
from app.config import get_settings
from app.db.models import AuditLogRow, ScanRow, TrainingPhotoRow
from tests.admin.conftest import seed
from tests.admin.test_pages import csrf_from, login
from tests.imaging import make_jpeg
from tests.integrations.fakes import NOW, farmer_row

SCAB = "Apple___Apple_scab"


@pytest.fixture
def authed(client):
    login(client)
    return client


def upload(client, files, **fields):
    data = {"csrf": csrf_from(client, "/admin/training"), "class_choice": SCAB, **fields}
    return client.post("/admin/training/upload", data=data,
                       files=[("photos", (name, content, ctype)) for name, content, ctype in files])


def photo(color, name="leaf.jpg", ctype="image/jpeg", fmt="JPEG"):
    return (name, make_jpeg(color=color, fmt=fmt), ctype)


@pytest.fixture
def export_dir(tmp_path, monkeypatch):
    target = tmp_path / "training" / "photos"
    monkeypatch.setenv("TRAINING_EXPORT_DIR", str(target))
    get_settings.cache_clear()
    return target


def rows(db):
    db.expire_all()
    return list(db.scalars(select(TrainingPhotoRow).order_by(TrainingPhotoRow.created_at)))


# ------------------------------------------------------------------------------------------------- upload
def test_page_needs_a_login_and_lists_the_four_apple_classes(client, authed):
    html = client.get("/admin/training").text
    for label in ("Apple scab", "Marssonina blotch", "Alternaria leaf blotch", "Healthy apple leaf", "Other class"):
        assert label in html
    assert 'enctype="multipart/form-data"' in html and "multiple" in html


def test_signed_out_gets_redirected(client):
    for path in ("/admin/training", "/admin/uploads", "/admin/voice", "/admin/training/export.zip", "/admin/training/x/image"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/admin/login", path


def test_upload_stores_files_rows_and_an_audit_entry(client, authed, db, tmp_path):
    response = upload(client, [photo((200, 30, 30), "a.jpg"), photo((30, 200, 30), "b.png", "image/png", "PNG")],
                      crop="Apple", leaf_id="T7-L3", source="Theog orchard", licence="own photo", confirmed_by="Dr Rana")
    assert response.status_code == 200 and response.text.count("stored</span>") == 2
    stored = rows(db)
    assert len(stored) == 2 and {r.class_label for r in stored} == {SCAB}
    first = stored[0]
    assert (first.crop, first.leaf_id, first.source, first.licence, first.confirmed_by) == ("Apple", "T7-L3", "Theog orchard", "own photo", "Dr Rana")
    on_disk = tmp_path / "storage" / first.path
    assert on_disk.is_file() and on_disk.read_bytes()[:2] == b"\xff\xd8" and first.path.startswith(f"training_uploads/{SCAB}/")
    assert first.size_bytes == on_disk.stat().st_size and first.sha256 and first.width == 320
    actions = [a.action for a in db.scalars(select(AuditLogRow))]
    assert actions.count("training.upload") == 2


def test_exif_and_gps_are_removed_from_the_stored_file(client, authed, db, tmp_path):
    upload(client, [("gps.jpg", make_jpeg(exif=True), "image/jpeg")])
    data = (tmp_path / "storage" / rows(db)[0].path).read_bytes()
    assert b"FakeCameraMaker" not in data and b"Exif" not in data


def test_duplicates_are_reported_and_not_stored_twice(client, authed, db):
    same = photo((10, 10, 200))
    assert "stored</span>" in upload(client, [same]).text
    again = upload(client, [same, ("copy.jpg", same[1], "image/jpeg")], class_choice="Apple___healthy")
    assert again.text.count("duplicate</span>") == 2 and "Already stored under Apple___Apple_scab" in again.text
    assert len(rows(db)) == 1


def test_a_file_that_is_not_an_image_is_rejected_whatever_its_name_and_type(client, authed, db):
    fake = ("virus.jpg", b"<?php echo 1; ?>" + b"x" * 200, "image/jpeg")
    gif = ("anim.png", b"GIF89a" + b"\x00" * 64, "image/png")
    response = upload(client, [fake, gif, photo((90, 90, 90))])
    assert response.status_code == 200 and response.text.count("rejected</span>") == 2 and "stored</span>" in response.text
    assert len(rows(db)) == 1                                   # the good file was still stored


def test_oversize_files_are_rejected_with_the_scan_limit(client, authed, db, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    big = ("big.jpg", b"\xff\xd8\xff" + b"0" * (1024 * 1024 + 10), "image/jpeg")
    response = upload(client, [big])
    assert "rejected</span>" in response.text and "larger than 1 MB" in response.text and rows(db) == []


def test_hostile_file_names_are_neutralised(client, authed, db, tmp_path):
    upload(client, [("../../../etc/passwd.jpg", make_jpeg(color=(1, 2, 3)), "image/jpeg"),
                    ("..\\..\\evil\x00.jpg", make_jpeg(color=(3, 2, 1)), "image/jpeg")])
    stored = rows(db)
    assert len(stored) == 2
    for row in stored:
        assert "/" not in row.original_name and "\\" not in row.original_name and ".." not in row.path
        assert (tmp_path / "storage" / row.path).resolve().is_relative_to((tmp_path / "storage" / "training_uploads").resolve())
    assert training.safe_name("C:\\x\\y z.JPG") == "y z.JPG" and training.safe_name("") == "photo" and len(training.safe_name("a" * 500)) <= 120


@pytest.mark.parametrize("choice,other", [("", ""), ("Apple___Nope", ""), ("../etc", ""), ("__other__", ""), ("__other__", "../up"),
                                          ("__other__", "a/b"), ("__other__", "x" * 61)])
def test_bad_classes_are_refused_with_a_message(client, authed, db, choice, other):
    response = upload(client, [photo((5, 5, 5))], class_choice=choice, class_other=other)
    assert response.status_code == 400 and 'role="alert"' in response.text and rows(db) == []


def test_a_free_class_is_accepted_and_gets_its_own_folder(client, authed, db, tmp_path):
    response = upload(client, [photo((7, 70, 7))], class_choice="__other__", class_other="Apple Powdery mildew")
    assert response.status_code == 200
    row = rows(db)[0]
    assert row.class_label == "Apple_Powdery_mildew" and (tmp_path / "storage" / row.path).is_file()


def test_too_many_files_and_no_file_are_refused(client, authed, db):
    many = [photo((i, 100, 100), f"{i}.jpg") for i in range(training.MAX_FILES_PER_UPLOAD + 1)]
    assert upload(client, many).status_code == 400
    response = client.post("/admin/training/upload", data={"csrf": csrf_from(client, "/admin/training"), "class_choice": SCAB})
    assert response.status_code == 400 and rows(db) == []


def test_upload_needs_the_csrf_token(client, authed, db):
    response = client.post("/admin/training/upload", data={"csrf": "wrong", "class_choice": SCAB},
                           files=[("photos", ("a.jpg", make_jpeg(), "image/jpeg"))])
    assert response.status_code == 403 and rows(db) == []


def test_form_values_are_escaped_in_the_page(client, authed):
    html = upload(client, [], class_choice="", source='"><script>alert(1)</script>').text
    assert "<script>alert(1)</script>" not in html


# ------------------------------------------------------------------------------------------------- list, preview, delete
def test_list_filter_preview_and_delete(client, authed, db, tmp_path):
    upload(client, [photo((1, 1, 250))])
    upload(client, [photo((250, 1, 1))], class_choice="Apple___healthy")
    html = client.get("/admin/training").text
    assert "Apple___healthy" in html and "(2)" in html
    only = client.get("/admin/training?cls=Apple___healthy").text
    assert only.count("<figure>") == 1
    row = next(r for r in rows(db) if r.class_label == "Apple___healthy")
    image = client.get(f"/admin/training/{row.id}/image")
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg" and image.headers["x-content-type-options"] == "nosniff"
    path, row_id = tmp_path / "storage" / row.path, row.id
    response = client.post(f"/admin/training/{row_id}/delete", data={"csrf": csrf_from(client, "/admin/training")}, follow_redirects=False)
    assert response.status_code == 303 and "ok=training_deleted" in response.headers["location"]
    assert not path.exists() and len(rows(db)) == 1
    assert "training.delete" in [a.action for a in db.scalars(select(AuditLogRow))]
    assert client.get(f"/admin/training/{row_id}/image").status_code == 404
    gone = client.post(f"/admin/training/{row_id}/delete", data={"csrf": csrf_from(client, "/admin/training")}, follow_redirects=False)
    assert "err=not_found" in gone.headers["location"]


def test_a_tampered_database_path_is_never_served(client, authed, db):
    upload(client, [photo((33, 33, 33))])
    row = rows(db)[0]
    row.path = "../../test.db"
    db.commit()
    assert client.get(f"/admin/training/{row.id}/image").status_code == 404


def test_deleting_a_photo_allows_uploading_it_again(client, authed, db):
    item = photo((44, 44, 200))
    upload(client, [item])
    client.post(f"/admin/training/{rows(db)[0].id}/delete", data={"csrf": csrf_from(client, "/admin/training")})
    assert "stored</span>" in upload(client, [item]).text


# ------------------------------------------------------------------------------------------------- export
def test_zip_export_has_the_class_folders_and_a_sources_file(client, authed, db):
    upload(client, [photo((9, 9, 200))], source="web", licence="CC BY 4.0", confirmed_by="Dr Rana")
    upload(client, [photo((200, 9, 9))], class_choice="Apple___healthy")
    response = client.get("/admin/training/export.zip")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert sum(n.startswith(f"{SCAB}/") for n in names) == 1 and sum(n.startswith("Apple___healthy/") for n in names) == 1
        text = archive.read("sources.csv").decode()
    assert text.splitlines()[0] == "file,class,source_url,licence,author,note" and "CC BY 4.0" in text and "Dr Rana" in text
    only = client.get("/admin/training/export.zip?cls=Apple___healthy")
    with zipfile.ZipFile(io.BytesIO(only.content)) as archive:
        assert [n for n in archive.namelist() if n.endswith(".jpg")] and not any(n.startswith(SCAB) for n in archive.namelist())


def test_folder_export_copies_once_and_logs_sources(client, authed, db, export_dir):
    upload(client, [photo((9, 9, 200))], source="web", licence="own", confirmed_by="Dr Rana")
    token = csrf_from(client, "/admin/training")
    first = client.post("/admin/training/export-folder", data={"csrf": token}, follow_redirects=False)
    assert "ok=training_folder" in first.headers["location"] and "n=1" in first.headers["location"]
    files = list((export_dir / SCAB).glob("adm_*.jpg"))
    assert len(files) == 1 and files[0].read_bytes()[:2] == b"\xff\xd8"
    log = (export_dir.parent / "admin_uploads.csv").read_text(encoding="utf-8")
    assert log.count("\n") == 2 and "Dr Rana" in log
    second = client.post("/admin/training/export-folder", data={"csrf": token}, follow_redirects=False)
    assert "n=0" in second.headers["location"] and "m=1" in second.headers["location"]
    assert (export_dir.parent / "admin_uploads.csv").read_text(encoding="utf-8").count("\n") == 2
    assert rows(db)[0].exported_at is not None
    assert "1 photos copied" in client.get(first.headers["location"]).text


# ------------------------------------------------------------------------------------------------- farmer photos
def test_farmer_photos_page_marks_offline_scans(client, authed, db):
    seed(db, farmer_row("F901"))
    seed(db, ScanRow(id="s-live", farmer_id="F901", created_at=NOW, status="ok", photo_paths=["photos/F901/s-live/a.jpg"], offline=False),
         ScanRow(id="s-off", farmer_id="F901", created_at=NOW + timedelta(hours=1), taken_at=NOW - timedelta(days=2), status="ok",
                 photo_paths=["photos/F901/s-off/a.jpg"], offline=True))
    everything = client.get("/admin/uploads").text
    assert "s-live" in everything and "s-off" in everything and "offline queue" in everything
    only = client.get("/admin/uploads?offline=1").text
    assert "s-off" in only and "s-live" not in only
    assert re.search(r'/admin/photos/s-off/0', only)


# ------------------------------------------------------------------------------------------------- voice page and dashboard
def test_voice_page_and_dashboard_show_the_tts_status(client, authed):
    page = client.get("/admin/voice").text
    assert "no TTS provider configured" in page and "Fixed prompts" in page and "GOOGLE_TTS_API_KEY" in page
    assert "No TTS provider configured" in client.get("/admin/dashboard").text


def test_voice_page_never_shows_the_key(client, authed, monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "AIza-secret-key-1234567890")
    get_settings.cache_clear()
    page = client.get("/admin/voice").text
    assert "Google TTS configured" in page and "AIza-secret" not in page and "set" in page


def test_dashboard_says_when_weather_is_off(client, authed, monkeypatch):
    assert '<span class="value">On</span>' in client.get("/admin/dashboard").text
    monkeypatch.setenv("WEATHER_ENABLED", "false")
    get_settings.cache_clear()
    assert "WEATHER_ENABLED=false" in client.get("/admin/dashboard").text
