from datetime import timedelta

import pytest

from app.db.models import ScanRow, SprayLogRow
from app.db.session import init_db, session_scope
from app.domain.types import LocalizedText, SprayRecord
from app.services.history import merged_history
from app.services.photo_store import PhotoStore
from app.services.prompts import PromptBook
from tests.fakes import NOW, FakeZoho, make_container, plain_settings


# ------------------------------------------------------------------------------------------------ photo store
def test_save_load_delete_round_trip(tmp_path):
    store = PhotoStore(tmp_path)
    relative = store.save("F001", "s" * 32, b"jpeg-bytes")
    assert relative.startswith("photos/F001/" + "s" * 32 + "/") and relative.endswith(".jpg") and "\\" not in relative
    assert store.load(relative) == b"jpeg-bytes"
    store.delete([relative])
    assert store.load(relative) is None
    store.delete([relative])                                # deleting twice is fine


def test_names_are_random_and_never_taken_from_user_input(tmp_path):
    store = PhotoStore(tmp_path)
    assert len({store.save("F001", "s" * 32, b"x") for _ in range(20)}) == 20


@pytest.mark.parametrize("relative", ["../outside.jpg", "photos/../../outside.jpg", "/etc/passwd", "photos/F001/\x00.jpg"])
def test_paths_outside_the_storage_directory_are_never_read_or_deleted(tmp_path, relative):
    outside = tmp_path.parent / "outside.jpg"
    outside.write_bytes(b"keep me")
    store = PhotoStore(tmp_path / "storage")
    (tmp_path / "storage").mkdir()
    assert store.load(relative) is None
    store.delete([relative])
    assert outside.read_bytes() == b"keep me"


def test_a_save_with_a_hostile_farmer_or_scan_id_is_refused(tmp_path):
    from app.security.paths import UnsafePathError

    store = PhotoStore(tmp_path / "storage")
    with pytest.raises(UnsafePathError):
        store.save("../../evil", "s" * 32, b"x")
    assert not (tmp_path / "evil").exists()


def test_retention_purges_old_photos_and_keeps_the_result(api_settings):
    init_db()
    store = PhotoStore(api_settings.storage_dir)
    old, recent = store.save("F001", "o" * 32, b"old"), store.save("F001", "n" * 32, b"new")
    from app.db.seed import seed_farmers

    with session_scope() as db:
        seed_farmers(db, api_settings.data_dir, NOW)
        for scan_id, created, path in (("o" * 32, NOW - timedelta(days=400), old), ("n" * 32, NOW - timedelta(days=10), recent)):
            db.add(ScanRow(id=scan_id, farmer_id="F001", created_at=created, status="ok", result={"id": scan_id}, photo_paths=[path]))
        db.commit()
        assert store.purge_expired(db, NOW, api_settings.photo_retention_days) == 1
        assert db.get(ScanRow, "o" * 32).photo_paths == [] and db.get(ScanRow, "o" * 32).result == {"id": "o" * 32}
        assert db.get(ScanRow, "n" * 32).photo_paths == [recent]
        assert store.purge_expired(db, NOW, api_settings.photo_retention_days) == 0
    assert store.load(old) is None and store.load(recent) == b"new"


def test_a_scan_whose_photos_were_purged_cannot_be_reevaluated(api_client, auth, api_settings):
    from tests.imaging import photo_files

    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    with session_scope() as db:
        PhotoStore(api_settings.storage_dir).purge_expired(db, NOW + timedelta(days=400), api_settings.photo_retention_days)
    response = api_client.post(f"/v1/scans/{scan['id']}/crop", json={"crop_id": "Tomato"}, headers=auth)
    assert response.status_code == 409 and response.json()["code"] == "photos_unavailable"
    assert api_client.get(f"/v1/scans/{scan['id']}", headers=auth).json() == scan          # the stored result is still there


def test_new_photos_can_be_added_after_the_old_ones_were_purged(api_client, auth, api_settings):
    from tests.imaging import photo_files

    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    with session_scope() as db:
        PhotoStore(api_settings.storage_dir).purge_expired(db, NOW + timedelta(days=400), api_settings.photo_retention_days)
    response = api_client.post(f"/v1/scans/{scan['id']}/photos", files=photo_files(1), headers=auth)
    assert response.status_code == 200 and response.json()["photos"] == 1


# ------------------------------------------------------------------------------------------------ history
@pytest.fixture
def farmer_and_container(api_settings):
    init_db()
    from app.db.repo import farmer_profile
    from app.db.seed import seed_farmers

    with session_scope() as db:
        seed_farmers(db, api_settings.data_dir, NOW)
        from app.db.models import FarmerRow

        return farmer_profile(db.get(FarmerRow, "F001")), make_container(api_settings)


def test_merged_history_orders_dedupes_and_ignores_the_future(farmer_and_container):
    farmer, container = farmer_and_container
    container.zoho.history = [SprayRecord(sprayed_at=NOW - timedelta(days=9), product_id="P001"),
                              SprayRecord(sprayed_at=NOW - timedelta(days=3), product_id="P012")]
    with session_scope() as db:
        for days, product in ((3, "P012"), (1, "P002"), (-2, "P005")):        # the first duplicates a Zoho row; the last is in the future
            db.add(SprayLogRow(farmer_id="F001", crop_id="Apple", product_id=product, sprayed_at=NOW - timedelta(days=days),
                               created_at=NOW, warnings=[], id=f"{days + 10:032d}"))
        db.commit()
        records, zoho_ok = merged_history(container, db, farmer, NOW)
    assert zoho_ok is True
    assert [(r.product_id, r.source) for r in records] == [("P001", "zoho"), ("P012", "zoho"), ("P002", "app")]


def test_merged_history_reports_a_zoho_outage(farmer_and_container):
    farmer, container = farmer_and_container
    container.zoho = FakeZoho()
    container.zoho.history_raises = RuntimeError("zoho down")
    with session_scope() as db:
        db.add(SprayLogRow(farmer_id="F001", crop_id="Apple", product_id="P002", sprayed_at=NOW - timedelta(days=1), created_at=NOW,
                           warnings=[], id="1" * 32))
        db.commit()
        records, zoho_ok = merged_history(container, db, farmer, NOW)
    assert zoho_ok is False and [r.product_id for r in records] == ["P002"]       # the diary alone is still used


# ------------------------------------------------------------------------------------------------ prompts
def test_prompt_book_reads_texts_and_falls_back(voice_dir):
    book = PromptBook(voice_dir)
    assert book.get("crop_confirm_prompt") == LocalizedText(en="Is this the right crop?", hi="क्या यह सही फसल है?")
    fallback = LocalizedText(en="fallback", hi="विकल्प")
    assert book.get("no_such_prompt", fallback) == fallback and book.get("no_such_prompt") == LocalizedText()


def test_prompt_book_survives_a_missing_or_broken_file(tmp_path):
    assert PromptBook(tmp_path / "nowhere").get("x") == LocalizedText()
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "prompts.json").write_text("{not json", encoding="utf-8")
    assert PromptBook(broken).get("x", LocalizedText(en="ok")).en == "ok"


def test_prompt_book_join_skips_empty_parts(voice_dir):
    joined = PromptBook(voice_dir).join(LocalizedText(en="One.", hi="एक।"), LocalizedText(), LocalizedText(en="Two.", hi="दो।"))
    assert joined == LocalizedText(en="One. Two.", hi="एक। दो।")


def test_the_real_prompt_file_has_every_id_the_pipeline_speaks():
    """voice/prompts.json is owned by the VOICE agent; the pipeline and next_steps rely on these ids existing."""
    book = PromptBook(plain_settings().voice_dir)
    needed = ["crop_confirm_prompt", "crop_is_unknown", "result_expert", "result_no_data", "result_not_disease", "crop_tap_yes",
              "scan_add_more", "diary_tick_sprayed", "result_next_diary", "diary_saved", "diary_warning", "field_stale", "field_no_data",
              "scan_retake_blurry", "scan_retake_dark", "scan_retake_far", "scan_retake_no_leaf", "crop_is_apple", "crop_is_tomato"]
    assert [i for i in needed if not book.get(i).en or not book.get(i).hi] == []
