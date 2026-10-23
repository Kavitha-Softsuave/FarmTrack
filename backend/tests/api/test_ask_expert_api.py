import pytest
from sqlalchemy import select

from app.db.models import ExpertRequestRow, ReviewTaskRow
from app.db.session import session_scope
from app.domain.types import AskResult, CropResult
from app.security.ratelimit import RateLimiters, SlidingWindowLimiter
from tests.imaging import photo_files


def ask(client, auth, **body):
    return client.post("/v1/ask", json={"question": "How do I protect apple from scab?", "language": "en", **body}, headers=auth)


# ------------------------------------------------------------------------------------------------ /v1/ask
def test_ask_returns_the_answer_citations_and_speech(api_client, auth, fake_container):
    response = ask(api_client, auth)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Use the approved schedule." and body["language"] == "en" and body["refused"] is False
    assert body["citations"] == [{"note_id": "N1", "source": "HP 2026 schedule"}]
    assert body["spoken"]["text"] == {"en": "Use the approved schedule.", "hi": ""}
    assert body["spoken"]["audio"]["en"]["url"].startswith("/audio/") and body["spoken"]["audio"]["hi"] is None
    assert fake_container.ask_service.calls == [("How do I protect apple from scab?", "en", "Apple")]      # default: the farmer's main crop


def test_ask_in_hindi_speaks_the_hindi_text(api_client, auth, fake_container):
    fake_container.ask_service.result = AskResult(answer="सेब के लिए सलाह।", language="hi")
    body = ask(api_client, auth, language="hi").json()
    assert body["spoken"]["text"] == {"en": "", "hi": "सेब के लिए सलाह।"}
    assert body["spoken"]["audio"]["en"] is None and body["spoken"]["audio"]["hi"]["url"].startswith("/audio/")


def test_a_refusal_is_passed_through_untouched(api_client, auth, fake_container):
    fake_container.ask_service.result = AskResult(answer="Please ask a farm expert.", language="en", refused=True)
    body = ask(api_client, auth, question="Which medicine for pea rust?").json()
    assert body["refused"] is True and body["answer"] == "Please ask a farm expert." and body["citations"] == []
    assert body["spoken"]["text"]["en"] == "Please ask a farm expert."


def test_crop_id_is_normalised_before_the_service(api_client, auth, fake_container):
    ask(api_client, auth, crop_id="apple")
    ask(api_client, auth, crop_id="Dragonfruit")
    assert [call[2] for call in fake_container.ask_service.calls] == ["Apple", "Dragonfruit"]


def test_a_farmer_without_a_main_crop_sends_no_crop(api_client, auth, fake_container):
    from app.db.models import FarmerRow
    from app.db.session import session_scope

    with session_scope() as db:
        db.get(FarmerRow, "F001").primary_crop = None
        db.commit()
    ask(api_client, auth)
    assert fake_container.ask_service.calls[0][2] is None


def test_question_is_trimmed(api_client, auth, fake_container):
    ask(api_client, auth, question="   when to spray?   ")
    assert fake_container.ask_service.calls[0][0] == "when to spray?"


@pytest.mark.parametrize("body", [{"question": "x"}, {"question": "x" * 501}, {"question": "   "}, {"question": "ok?", "language": "fr"},
                                  {"question": "ok?", "crop_id": "../x"}, {}])
def test_ask_validates_input(api_client, auth, body):
    assert api_client.post("/v1/ask", json=body, headers=auth).status_code == 422


def test_ask_service_failure_is_a_503_without_leaking_the_question(api_client, auth, fake_container, caplog):
    fake_container.ask_service.raises = RuntimeError("vector store down")
    response = ask(api_client, auth, question="my private orchard question")
    assert response.status_code == 503 and response.json()["code"] == "ask_unavailable"
    assert "vector store" not in response.text
    assert "private orchard question" not in caplog.text


def test_ask_is_rate_limited_per_farmer(api_client, auth, login, api_app):
    limiters = RateLimiters.default()
    limiters.ask_farmer = SlidingWindowLimiter(2, 600)
    api_app.state.limiters = limiters
    assert [ask(api_client, auth).status_code for _ in range(3)] == [200, 200, 429]
    assert ask(api_client, login("+910000000002")).status_code == 200


def test_ask_audio_failure_still_answers(api_client, auth, fake_container):
    fake_container.audio.fail = True
    body = ask(api_client, auth).json()
    assert body["answer"] and body["spoken"]["audio"] == {"hi": None, "en": None}


# ------------------------------------------------------------------------------------------------ /v1/expert-requests
def test_expert_request_about_a_scan_creates_a_review_task(api_client, auth):
    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    response = api_client.post("/v1/expert-requests", json={"scan_id": scan["id"], "message": "Leaves are curling"}, headers=auth)
    assert response.status_code == 200 and response.json()["status"] == "open"
    with session_scope() as db:
        request = db.scalars(select(ExpertRequestRow)).one()
        assert request.id == response.json()["id"] and request.farmer_id == "F001" and request.message == "Leaves are curling"
        task = db.scalars(select(ReviewTaskRow)).one()
        assert task.scan_id == scan["id"] and task.farmer_id == "F001" and task.status == "open"
        assert task.reason == "farmer_request: Leaves are curling"


def test_expert_request_reuses_the_open_task_and_keeps_the_reason(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(crop_id=None, unknown=True)
    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    api_client.post("/v1/expert-requests", json={"scan_id": scan["id"], "message": "please call"}, headers=auth)
    with session_scope() as db:
        task = db.scalars(select(ReviewTaskRow)).one()
        assert task.reason == "farmer_request: please call; was: crop_unknown"
    # the farmer asked for a human: a later automatic result must not close the task behind their back
    fake_container.crop_identifier.result = CropResult(crop_id="Apple", confidence=0.95)
    api_client.post(f"/v1/scans/{scan['id']}/photos", files=photo_files(1), headers=auth)
    with session_scope() as db:
        assert db.scalars(select(ReviewTaskRow)).one().status == "open"


def test_asking_twice_does_not_duplicate_the_task(api_client, auth):
    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    for _ in range(2):
        api_client.post("/v1/expert-requests", json={"scan_id": scan["id"]}, headers=auth)
    with session_scope() as db:
        assert len(db.scalars(select(ReviewTaskRow)).all()) == 1
        assert len(db.scalars(select(ExpertRequestRow)).all()) == 2


def test_expert_request_without_a_scan_is_stored(api_client, auth):
    response = api_client.post("/v1/expert-requests", json={"message": "Need advice on pruning"}, headers=auth)
    assert response.status_code == 200
    with session_scope() as db:
        assert db.scalars(select(ExpertRequestRow)).one().scan_id is None
        assert db.scalars(select(ReviewTaskRow)).all() == []                   # a task needs a scan (FK): staff see the row itself in the admin 'Expert requests' page


def test_expert_request_for_someone_elses_scan_is_404(api_client, auth, login):
    scan = api_client.post("/v1/scans", files=photo_files(1), headers=auth).json()
    response = api_client.post("/v1/expert-requests", json={"scan_id": scan["id"]}, headers=login("+910000000002"))
    assert response.status_code == 404
    assert api_client.post("/v1/expert-requests", json={"scan_id": "0" * 32}, headers=auth).status_code == 404
    with session_scope() as db:
        assert db.scalars(select(ExpertRequestRow)).all() == []


def test_expert_request_message_limit(api_client, auth):
    assert api_client.post("/v1/expert-requests", json={"message": "m" * 501}, headers=auth).status_code == 422


def test_expert_request_can_name_the_crop(api_client, auth):
    assert api_client.post("/v1/expert-requests", json={"message": "pruning", "crop_id": "apple"}, headers=auth).status_code == 200
    assert api_client.post("/v1/expert-requests", json={"message": "x", "crop_id": "Dragonfruit"}, headers=auth).status_code == 200
    assert api_client.post("/v1/expert-requests", json={"message": "x", "crop_id": "  "}, headers=auth).status_code == 200
    with session_scope() as db:
        assert [r.crop_id for r in db.scalars(select(ExpertRequestRow).order_by(ExpertRequestRow.id))] == ["Apple", "Dragonfruit", None]


@pytest.mark.parametrize("crop_id", ["../x", "1apple", "a" * 41])
def test_expert_request_refuses_a_bad_crop_name(api_client, auth, crop_id):
    assert api_client.post("/v1/expert-requests", json={"message": "x", "crop_id": crop_id}, headers=auth).status_code == 422
    with session_scope() as db:
        assert db.scalars(select(ExpertRequestRow)).all() == []
