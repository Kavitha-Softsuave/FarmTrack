import json
from datetime import timedelta

from app.alerts.maintenance import purge_expired_photos, sync_unsynced_sprays
from app.db.models import ScanRow, SprayLogRow
from app.integrations.factory import build_zoho
from tests.integrations.fakes import NOW, FakeZoho, farmer_row, make_container, make_settings, spray_log_row


def seed(db, *rows):
    for row in rows:
        db.add(row)
        db.flush()
    db.commit()


class RecordingZoho(FakeZoho):
    def __init__(self, result=True, raises=False):
        super().__init__()
        self.result, self.fail = result, raises
        self.written = []

    def write_spray(self, farmer_id, record):
        if self.fail:
            raise RuntimeError("zoho down")
        self.written.append((farmer_id, record))
        return self.result


# ------------------------------------------------------------------------------------------------- zoho retry
def test_unsynced_sprays_are_sent_and_marked(db, tmp_path):
    seed(db, farmer_row("F901"), spray_log_row("F901", NOW - timedelta(days=2), product_id="P001", synced_to_zoho=False),
         spray_log_row("F901", NOW - timedelta(days=1), product_id="P002", synced_to_zoho=True))
    zoho = RecordingZoho()
    assert sync_unsynced_sprays(db, make_container(tmp_path, zoho=zoho)) == 1
    assert [(f, r.product_id, r.source) for f, r in zoho.written] == [("F901", "P001", "app")]
    assert [r.synced_to_zoho for r in db.query(SprayLogRow).order_by(SprayLogRow.sprayed_at)] == [True, True]
    assert sync_unsynced_sprays(db, make_container(tmp_path, zoho=zoho)) == 0                    # nothing left to send


def test_failed_or_refused_writes_stay_queued(db, tmp_path):
    seed(db, farmer_row("F901"), spray_log_row("F901", NOW, product_id="P001", synced_to_zoho=False))
    for zoho in (RecordingZoho(result=False), RecordingZoho(raises=True)):
        assert sync_unsynced_sprays(db, make_container(tmp_path, zoho=zoho)) == 0
        assert db.query(SprayLogRow).one().synced_to_zoho is False


def test_one_bad_entry_does_not_block_the_others(db, tmp_path):
    seed(db, farmer_row("F901"), spray_log_row("F901", NOW - timedelta(days=2), product_id="P001", synced_to_zoho=False),
         spray_log_row("F901", NOW - timedelta(days=1), product_id="P002", synced_to_zoho=False))

    class FirstFails(RecordingZoho):
        def write_spray(self, farmer_id, record):
            if record.product_id == "P001":
                raise RuntimeError("bad row")
            return super().write_spray(farmer_id, record)

    assert sync_unsynced_sprays(db, make_container(tmp_path, zoho=FirstFails())) == 1
    assert [r.synced_to_zoho for r in db.query(SprayLogRow).order_by(SprayLogRow.sprayed_at)] == [False, True]


def test_batch_limit_is_honoured(db, tmp_path):
    seed(db, farmer_row("F901"), *(spray_log_row("F901", NOW - timedelta(days=i), product_id="P001", synced_to_zoho=False)
                                  for i in range(1, 4)))
    assert sync_unsynced_sprays(db, make_container(tmp_path, zoho=RecordingZoho()), limit=2) == 2


def test_retry_writes_to_the_mock_zoho_store(db, tmp_path):
    settings = make_settings(tmp_path)
    container = make_container(tmp_path, zoho=build_zoho(settings))
    seed(db, farmer_row("F001"), spray_log_row("F001", NOW, product_id="P001", synced_to_zoho=False))
    assert sync_unsynced_sprays(db, container) == 1
    line = json.loads((settings.storage_dir / "zoho_mock" / "sprays.jsonl").read_text(encoding="utf-8"))
    assert line["farmer_id"] == "F001" and line["data"]["product_id"] == "P001"


# ------------------------------------------------------------------------------------------------- photo retention
def scan(scan_id: str, created, paths: list[str]) -> ScanRow:
    return ScanRow(id=scan_id, farmer_id="F901", created_at=created, status="ok", photo_paths=paths, result={})


def test_old_photos_are_deleted_and_recent_ones_kept(db, tmp_path):
    container = make_container(tmp_path)
    storage = container.settings.storage_dir
    files = {"old": "photos/F901/old/a.jpg", "new": "photos/F901/new/b.jpg"}
    for relative in files.values():
        path = storage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"jpeg")
    seed(db, farmer_row("F901"), scan("old", NOW - timedelta(days=container.settings.photo_retention_days + 5), [files["old"]]),
         scan("new", NOW - timedelta(days=10), [files["new"]]))
    assert purge_expired_photos(db, container) == 1
    assert not (storage / files["old"]).exists() and (storage / files["new"]).exists()
    db.expire_all()
    assert db.get(ScanRow, "old").photo_paths == [] and db.get(ScanRow, "new").photo_paths == [files["new"]]
    assert purge_expired_photos(db, container) == 0
