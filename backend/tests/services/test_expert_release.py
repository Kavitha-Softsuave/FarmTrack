"""The admin 'send the advice to the farmer' hook (app.state.release_advice) re-runs the rules on the agronomist's confirmation."""
import pytest
from sqlalchemy import select

from app.db.models import AdviceRow, AlertRow, DeviceRow, ReviewTaskRow, ScanRow
from app.db.session import session_scope
from app.domain.types import CropResult
from tests.fakes import SCAB, rule_output
from tests.imaging import photo_files


@pytest.fixture
def expert_case(api_client, auth, fake_container):
    """A scan the rules sent to the expert queue (low confidence), plus a registered phone for the push."""
    api_client.post("/v1/devices", json={"platform": "android", "push_token": "tok-F001"}, headers=auth)
    fake_container.rules.output = rule_output("expert_review")
    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    assert scan["status"] == "needs_expert" and scan["review_task_id"]
    return scan


def resolve(client, api_settings, task_id, **body):
    return client.post(f"/admin/api/v1/review-tasks/{task_id}/resolve", json=body, headers={"X-Admin-Key": api_settings.admin_api_key})


def test_the_hook_is_installed_at_startup(api_app, api_client):
    assert callable(api_app.state.release_advice)


def test_release_replaces_the_result_and_notifies_the_farmer(api_client, auth, api_settings, fake_container, expert_case):
    fake_container.rules.output = rule_output("advice")                    # with the confirmed disease the rules now give advice
    response = resolve(api_client, api_settings, expert_case["review_task_id"], confirmed_disease=SCAB, release_advice=True, note="scab")
    assert response.status_code == 200 and response.json()["status"] == "resolved"
    rule_in = fake_container.rules.inputs[-1]
    assert rule_in.disease_id == SCAB and rule_in.disease_confidence == 1.0 and rule_in.crop_id == "Apple"
    stored = api_client.get(f"/v1/scans/{expert_case['id']}", headers=auth).json()
    assert stored["status"] == "ok" and stored["id"] == expert_case["id"] and stored["review_task_id"] is None
    assert stored["advice"]["products"][0]["product_id"] == "P012" and stored["crop"]["source"] == "expert_confirmed"
    assert stored["disease"]["confidence"] == 1.0 and stored["created_at"] == expert_case["created_at"]
    assert [s["action"] for s in stored["next_steps"]] == ["mark_sprayed", "done"]
    with session_scope() as db:
        assert len(db.scalars(select(AdviceRow).where(AdviceRow.scan_id == expert_case["id"])).all()) == 2    # history is kept
        task = db.scalars(select(ReviewTaskRow)).one()
        assert task.status == "resolved" and task.resolution["release_status"] == "released"
        alert = db.scalars(select(AlertRow)).one()
        assert alert.farmer_id == "F001" and alert.kind == "expert_advice" and alert.payload == {"scan_id": expert_case["id"]}
    token, title, _body, data = fake_container.push.sent[0]
    assert token == "tok-F001" and data == {"kind": "expert_advice", "scan_id": expert_case["id"]} and title
    alerts = api_client.get("/v1/alerts", headers=auth).json()
    assert alerts["unread"] == 1 and alerts["items"][0]["kind"] == "expert_advice"


def test_release_is_refused_when_the_rules_still_say_no(api_client, auth, api_settings, fake_container, expert_case):
    before = api_client.get(f"/v1/scans/{expert_case['id']}", headers=auth).json()
    response = resolve(api_client, api_settings, expert_case["review_task_id"], confirmed_disease="Apple___Marssonina_blotch",
                       release_advice=True)
    assert response.status_code == 502                                         # the admin service's answer to a failed release
    assert api_client.get(f"/v1/scans/{expert_case['id']}", headers=auth).json() == before
    with session_scope() as db:
        assert db.scalars(select(ReviewTaskRow)).one().status == "open"
        assert db.scalars(select(AlertRow)).all() == []
    assert fake_container.push.sent == []


def test_a_confirmed_crop_overrides_the_detected_one(api_client, auth, api_settings, fake_container, expert_case):
    fake_container.rules.output = rule_output("advice", crop_id="Tomato")
    resolve(api_client, api_settings, expert_case["review_task_id"], confirmed_crop="tomato", release_advice=True)
    assert fake_container.rules.inputs[-1].crop_id == "Tomato"
    assert api_client.get(f"/v1/scans/{expert_case['id']}", headers=auth).json()["crop"]["crop_id"] == "Tomato"


def test_an_unconfirmed_disease_keeps_the_models_confidence(api_client, auth, api_settings, fake_container, expert_case):
    fake_container.rules.output = rule_output("advice")
    resolve(api_client, api_settings, expert_case["review_task_id"], confirmed_crop="Apple", release_advice=True)
    assert fake_container.rules.inputs[-1].disease_confidence == 0.9           # the classifier's own score, not 1.0


def test_resolving_without_release_leaves_the_scan_alone(api_client, auth, api_settings, expert_case):
    before = api_client.get(f"/v1/scans/{expert_case['id']}", headers=auth).json()
    assert resolve(api_client, api_settings, expert_case["review_task_id"], confirmed_disease=SCAB, note="seen").status_code == 200
    assert api_client.get(f"/v1/scans/{expert_case['id']}", headers=auth).json() == before


def test_release_without_a_known_crop_is_refused(api_client, auth, api_settings, fake_container):
    fake_container.crop_identifier.result = CropResult(crop_id=None, unknown=True)
    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    response = resolve(api_client, api_settings, scan["review_task_id"], confirmed_disease=SCAB, release_advice=True)
    assert response.status_code == 502


def test_push_failure_does_not_undo_the_release(api_client, auth, api_settings, fake_container, expert_case):
    def boom(*_a, **_k):
        raise RuntimeError("fcm down")

    fake_container.push.send = boom
    fake_container.rules.output = rule_output("advice")
    assert resolve(api_client, api_settings, expert_case["review_task_id"], confirmed_disease=SCAB, release_advice=True).status_code == 200
    assert api_client.get(f"/v1/scans/{expert_case['id']}", headers=auth).json()["status"] == "ok"


def test_the_release_hook_ignores_a_missing_scan(api_app, api_client, api_settings, fake_container):
    from app.api.schemas import ReviewResolveIn

    with session_scope() as db:
        task = ReviewTaskRow(id="t" * 32, scan_id="0" * 32, farmer_id="F001", status="open", reason="x", created_at=fake_container.clock.now())
        assert api_app.state.release_advice(db, task, ReviewResolveIn(confirmed_disease=SCAB, release_advice=True)) is False


def test_stored_scan_row_reflects_the_release(api_client, auth, api_settings, fake_container, expert_case):
    fake_container.rules.output = rule_output("advice")
    resolve(api_client, api_settings, expert_case["review_task_id"], confirmed_disease=SCAB, release_advice=True)
    with session_scope() as db:
        row = db.get(ScanRow, expert_case["id"])
        assert row.status == "ok" and row.crop_confirmed is True and row.crop_source == "expert_confirmed" and row.route == "auto_advice"
        assert db.scalars(select(DeviceRow)).one().push_token == "tok-F001"
