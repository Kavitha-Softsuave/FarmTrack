"""Every branch of the scan pipeline, driven through the HTTP API with fake providers."""
import pytest
from sqlalchemy import select

from app.db.models import AdviceRow, AuditLogRow, ReviewTaskRow, ScanRow, SprayLogRow
from app.db.session import session_scope
from app.domain.types import (
    CropCandidate,
    CropResult,
    DiseaseCandidate,
    DiseaseResult,
    LocalizedText,
    QualityIssue,
    QualityResult,
    SprayRecord,
)
from app.security.ratelimit import RateLimiters, SlidingWindowLimiter
from tests.fakes import NOW, SCAB, lt, rule_output, sample_product, unusable
from tests.imaging import photo_files


def scan(client, auth, count=1, data=None):
    return client.post("/v1/scans", files=photo_files(count), data=data or {}, headers=auth)


# ------------------------------------------------------------------------------------------------ status: ok
def test_scab_scan_returns_full_advice(api_client, auth, fake_container):
    response = scan(api_client, auth)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["photos"] == 1 and body["review_task_id"] is None
    assert body["created_at"] == "2026-05-12T08:00:00+05:30"                       # the demo clock, not the wall clock
    assert body["crop"]["crop_id"] == "Apple" and body["crop"]["name"] == {"en": "Apple", "hi": "सेब"}
    assert body["disease"]["disease_id"] == SCAB and body["disease"]["name"]["en"] == "Apple scab"
    assert body["disease"]["route"] == "auto_advice" and body["quality"]["usable"] is True
    advice = body["advice"]
    assert advice["scan_id"] == body["id"] and advice["validated"] is True and advice["severity"] == "yellow"
    product = advice["products"][0]
    assert product["product_id"] == "P012" and product["active_ingredient"]["hi"] == "माइक्लोब्यूटानिल"
    assert product["dose_text"]["en"] == "80 g in 200 litres of water" and product["waiting_period_days"] == 21
    assert advice["timing"]["action"] == "spray_now"
    assert advice["sources"] == ["HP 2026 schedule", "NIPHM"]                       # unique, in note order
    assert advice["steps"] and advice["safety"] and advice["spoken"]["text"]["hi"] == "बोला advice"
    assert advice["spoken"]["audio"]["en"]["url"].startswith("/audio/")
    assert body["spoken"] == advice["spoken"]
    assert [(s["action"], s["prompt_id"]) for s in body["next_steps"]] == [
        ("mark_sprayed", "diary_tick_sprayed"), ("done", "result_next_diary")]


def test_get_returns_exactly_the_stored_result(api_client, auth, fake_container):
    created = scan(api_client, auth).json()
    fake_container.rules.output = rule_output("expert_review")        # the world changed; the stored answer must not
    again = api_client.get(f"/v1/scans/{created['id']}", headers=auth)
    assert again.status_code == 200 and again.json() == created


def test_pipeline_feeds_the_providers_correctly(api_client, auth, fake_container):
    fake_container.zoho.history = [SprayRecord(sprayed_at=NOW.replace(day=2), product_id="P003", frac_irac_code="M03")]
    scan(api_client, auth, count=2, data={"client_crop": "Apple", "client_confidence": "0.7"})
    crop_call = fake_container.crop_identifier.calls[0]
    assert crop_call == {"images": 2, "farmer_crops": ["Apple"], "client_guess": "Apple", "client_confidence": 0.7}
    assert fake_container.disease_classifier.calls == [{"images": 2, "crop_id": "Apple"}]
    rule_in = fake_container.rules.inputs[0]
    assert rule_in.farmer.id == "F001" and rule_in.language == "hi" and rule_in.now == NOW
    assert rule_in.crop_id == "Apple" and rule_in.disease_id == SCAB and rule_in.disease_confidence == 0.9
    assert [r.product_id for r in rule_in.history] == ["P003"] and rule_in.weather.station_id == "ST01"
    assert fake_container.zoho.history_calls == [NOW]                                # history is read up to the demo clock
    station, lat, lon, now = fake_container.weather.calls[0]
    assert station == "ST01" and lat and lon and now == NOW
    assert fake_container.kb.queries[0] == {"crop": "Apple", "disease_id": SCAB, "stage": "petal_fall", "product_ids": ["P012"]}


def test_history_merges_zoho_and_the_apps_own_diary(api_client, auth, fake_container):
    fake_container.zoho.history = [SprayRecord(sprayed_at=NOW.replace(day=2), product_id="P003")]
    with session_scope() as db:
        db.add(SprayLogRow(id="a" * 32, farmer_id="F001", crop_id="Apple", product_id="P012", product_name="Myclobutanil",
                           sprayed_at=NOW.replace(day=9), synced_to_zoho=False, warnings=[], created_at=NOW))
        db.add(SprayLogRow(id="b" * 32, farmer_id="F001", crop_id="Apple", product_id="P011", product_name="Later",
                           sprayed_at=NOW.replace(day=20), synced_to_zoho=False, warnings=[], created_at=NOW))   # after the clock
    scan(api_client, auth)
    history = fake_container.rules.inputs[0].history
    assert [r.product_id for r in history] == ["P003", "P012"] and history[1].source == "app"


def test_scan_is_persisted_with_advice_trace_and_audit(api_client, auth, fake_container, api_settings):
    body = scan(api_client, auth).json()
    with session_scope() as db:
        row = db.get(ScanRow, body["id"])
        assert row.status == "ok" and row.crop_id == "Apple" and row.disease_id == SCAB and row.route == "auto_advice"
        assert row.result["id"] == body["id"] and len(row.photo_paths) == 1
        advice = db.scalars(select(AdviceRow).where(AdviceRow.scan_id == body["id"])).one()
        assert advice.id == body["advice"]["id"] and advice.rule_trace == ["fake rule trace"] and advice.validated
        audit = db.scalars(select(AuditLogRow).where(AuditLogRow.entity_id == body["id"])).one()
        assert audit.actor == "F001" and audit.detail["status"] == "ok"
    stored = api_settings.storage_dir / row.photo_paths[0]
    assert stored.is_file() and stored.parent.name == body["id"]


def test_diagnosis_is_written_to_zoho(api_client, auth, fake_container):
    body = scan(api_client, auth).json()
    farmer_id, payload = fake_container.zoho.diagnoses[0]
    assert farmer_id == "F001" and payload["scan_id"] == body["id"] and payload["status"] == "ok"
    assert payload["disease_id"] == SCAB and payload["product_ids"] == ["P012"] and payload["route"] == "auto_advice"
    assert "phone" not in payload


# ------------------------------------------------------------------------------------------------ the other rule outcomes
@pytest.mark.parametrize("rule_status,scan_status,task,steps", [
    ("expert_review", "needs_expert", True, ["ask_expert", "add_photo"]),
    ("needs_more_info", "needs_expert", True, ["add_photo", "ask_expert"]),
    ("no_approved_data", "no_approved_data", False, ["ask_expert"]),
    ("not_a_disease", "not_a_disease", False, ["add_photo", "ask_expert"]),
])
def test_rule_status_maps_to_scan_status_and_never_shows_a_product(api_client, auth, fake_container, rule_status, scan_status,
                                                                  task, steps):
    # a faulty rules engine that attaches products to a non-advice outcome must still not leak them
    fake_container.rules.output = rule_output(rule_status, products=[sample_product()])
    body = scan(api_client, auth).json()
    assert body["status"] == scan_status
    assert body["advice"] is not None and body["advice"]["products"] == [] and body["advice"]["timing"] is None
    assert bool(body["review_task_id"]) is task
    assert [s["action"] for s in body["next_steps"]] == steps
    assert body["spoken"]["text"]["en"]
    with session_scope() as db:
        tasks = db.scalars(select(ReviewTaskRow).where(ReviewTaskRow.scan_id == body["id"])).all()
        assert len(tasks) == (1 if task else 0)
        if task:
            assert tasks[0].status == "open" and tasks[0].farmer_id == "F001"
            assert rule_status in tasks[0].reason and "low_confidence" in tasks[0].reason
        assert [p.get("product_id") for p in db.scalars(select(AdviceRow)).one().payload["products"]] == []


def test_zoho_diagnosis_is_written_for_every_rule_outcome_but_not_for_a_product_when_not_advised(api_client, auth, fake_container):
    fake_container.rules.output = rule_output("expert_review", products=[sample_product()])
    scan(api_client, auth)
    assert fake_container.zoho.diagnoses[0][1]["status"] == "needs_expert"
    assert fake_container.zoho.diagnoses[0][1]["product_ids"] == []


def test_result_speech_for_a_rule_outcome_is_the_composers_text(api_client, auth, fake_container):
    for status in ("expert_review", "no_approved_data", "not_a_disease"):
        fake_container.rules.output = rule_output(status)
        body = scan(api_client, auth).json()
        assert body["spoken"] == body["advice"]["spoken"] and body["spoken"]["text"]["en"] == f"Spoken {status}"


# ------------------------------------------------------------------------------------------------ photo quality
def test_all_photos_unusable_stops_before_the_crop_is_identified(api_client, auth, fake_container):
    from tests.fakes import FakeQuality

    fake_container.quality = FakeQuality([unusable(QualityIssue.blurry, "scan_retake_blurry")])
    body = scan(api_client, auth, count=2).json()
    assert body["status"] == "photo_unusable" and body["crop"] is None and body["disease"] is None and body["advice"] is None
    assert body["quality"] == {"usable": False, "issues": ["blurry"], "tip_prompt_id": "scan_retake_blurry"}
    assert body["next_steps"] == [{"action": "retake", "prompt_id": "scan_retake_blurry"}]
    assert body["spoken"]["text"]["en"] == "The photo is not clear."
    assert fake_container.crop_identifier.calls == [] and fake_container.rules.inputs == []
    assert fake_container.zoho.diagnoses == []
    with session_scope() as db:
        assert db.scalars(select(AdviceRow)).all() == []


def test_tip_is_derived_from_the_issue_when_the_checker_gives_none(api_client, auth, fake_container):
    from tests.fakes import FakeQuality

    fake_container.quality = FakeQuality([unusable(QualityIssue.too_bright, None)])
    body = scan(api_client, auth).json()
    assert body["quality"]["tip_prompt_id"] == "scan_retake_dark" and body["next_steps"][0]["prompt_id"] == "scan_retake_dark"


def test_one_good_photo_is_enough_and_only_good_photos_reach_the_models(api_client, auth, fake_container):
    from tests.fakes import FakeQuality

    fake_container.quality = FakeQuality([unusable(QualityIssue.blurry), QualityResult(usable=True)])
    body = scan(api_client, auth, count=2).json()
    assert body["status"] == "ok" and body["photos"] == 2 and body["quality"]["usable"] is True
    assert fake_container.crop_identifier.calls[0]["images"] == 1
    assert fake_container.disease_classifier.calls[0]["images"] == 1


# ------------------------------------------------------------------------------------------------ crop identification
def test_unknown_crop_goes_to_the_expert_without_a_disease_or_medicine(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(crop_id=None, unknown=True, confidence=0.1)
    body = scan(api_client, auth).json()
    assert body["status"] == "needs_expert" and body["crop"]["unknown"] is True and body["crop"]["crop_id"] is None
    assert body["disease"] is None and body["advice"] is None and body["review_task_id"]
    assert [s["action"] for s in body["next_steps"]] == ["ask_expert", "add_photo"]
    assert fake_container.disease_classifier.calls == [] and fake_container.rules.inputs == []
    with session_scope() as db:
        assert db.scalars(select(ReviewTaskRow)).one().reason == "crop_unknown"


def test_unsure_crop_asks_for_confirmation_before_any_disease_or_medicine(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(
        crop_id="Apple", confidence=0.55, needs_confirmation=True, source="server_model",
        candidates=[CropCandidate(crop_id="Apple", confidence=0.55), CropCandidate(crop_id="Pear", confidence=0.3)])
    body = scan(api_client, auth).json()
    assert body["status"] == "confirm_crop"
    assert body["crop"]["needs_confirmation"] is True and body["crop"]["crop_id"] == "Apple"
    assert [c["crop_id"] for c in body["crop"]["candidates"]] == ["Apple", "Pear"]
    assert body["disease"] is None and body["advice"] is None and body["review_task_id"] is None
    assert body["next_steps"] == [{"action": "confirm_crop", "prompt_id": "crop_confirm_prompt"}]      # the question, not the answer button
    assert body["spoken"]["text"]["en"] == "This looks like apple. Is this the right crop?"
    assert body["spoken"]["text"]["hi"] == "यह सेब की फसल लगती है। क्या यह सही फसल है?"
    assert fake_container.disease_classifier.calls == [] and fake_container.rules.inputs == []
    assert fake_container.zoho.diagnoses == []


def test_crop_without_a_reviewed_prompt_gets_a_generated_sentence(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(crop_id="Pear", confidence=0.5, needs_confirmation=True)
    text = scan(api_client, auth).json()["spoken"]["text"]
    assert text["en"].startswith("This looks like Pear.") and text["en"].endswith("Is this the right crop?")


@pytest.fixture
def unsure_scan(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(crop_id="Apple", confidence=0.55, needs_confirmation=True)
    return scan(api_client, auth).json()


def test_confirming_the_crop_continues_the_pipeline(api_client, auth, fake_container, unsure_scan):
    response = api_client.post(f"/v1/scans/{unsure_scan['id']}/crop", json={"crop_id": "apple"}, headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == unsure_scan["id"] and body["status"] == "ok" and body["created_at"] == unsure_scan["created_at"]
    assert body["crop"]["crop_id"] == "Apple" and body["crop"]["source"] == "farmer_confirmed" and body["crop"]["confidence"] == 1.0
    assert body["advice"]["products"][0]["product_id"] == "P012"
    assert fake_container.disease_classifier.calls == [{"images": 1, "crop_id": "Apple"}]       # photos re-read from storage
    assert api_client.get(f"/v1/scans/{unsure_scan['id']}", headers=auth).json() == body
    with session_scope() as db:
        row = db.get(ScanRow, unsure_scan["id"])
        assert row.crop_confirmed is True and row.crop_source == "farmer_confirmed" and row.status == "ok"


def test_confirming_twice_returns_the_same_answer_without_rerunning(api_client, auth, fake_container, unsure_scan):
    url = f"/v1/scans/{unsure_scan['id']}/crop"
    first = api_client.post(url, json={"crop_id": "Apple"}, headers=auth).json()
    calls = len(fake_container.rules.inputs)
    assert api_client.post(url, json={"crop_id": "Apple"}, headers=auth).json() == first
    assert len(fake_container.rules.inputs) == calls


def test_correcting_the_crop_runs_the_rules_for_the_corrected_crop(api_client, auth, fake_container, unsure_scan):
    fake_container.rules.output = rule_output("no_approved_data", crop_id="Pear")
    body = api_client.post(f"/v1/scans/{unsure_scan['id']}/crop", json={"crop_id": "Tomato"}, headers=auth).json()
    assert body["crop"]["crop_id"] == "Tomato" and body["status"] == "no_approved_data"
    assert fake_container.rules.inputs[-1].crop_id == "Tomato"
    assert fake_container.disease_classifier.calls[-1]["crop_id"] == "Tomato"


def test_crop_aliases_and_model_suggestions_are_accepted(api_client, auth, fake_container, unsure_scan):
    fake_container.rules.output = rule_output("no_approved_data", crop_id="Maize")
    body = api_client.post(f"/v1/scans/{unsure_scan['id']}/crop", json={"crop_id": "Corn"}, headers=auth).json()
    assert body["crop"]["crop_id"] == "Maize"                                          # alias -> catalogue spelling
    fake_container.crop_identifier.result = CropResult(
        crop_id="Apple", confidence=0.5, needs_confirmation=True,
        candidates=[CropCandidate(crop_id="Apple", confidence=0.5), CropCandidate(crop_id="Custard_Apple", confidence=0.3)])
    second = scan(api_client, auth).json()
    assert second["crop"]["candidates"][1]["name"] == {"en": "Custard Apple", "hi": "शरीफा"}
    picked = api_client.post(f"/v1/scans/{second['id']}/crop", json={"crop_id": "custard apple"}, headers=auth)
    assert picked.status_code == 200 and picked.json()["crop"]["crop_id"] == "Custard_Apple"
    fake_container.crop_identifier.result = CropResult(crop_id="Apple", confidence=0.5, needs_confirmation=True)
    other = scan(api_client, auth).json()                                              # Custard Apple was not suggested for this one
    for crop in ("Custard_Apple", "Dragonfruit"):
        assert api_client.post(f"/v1/scans/{other['id']}/crop", json={"crop_id": crop}, headers=auth).status_code == 422


def test_confirming_an_unknown_crop_is_refused(api_client, auth, unsure_scan):
    for bad in ("Unobtainium", "", "../etc", "x" * 60):
        response = api_client.post(f"/v1/scans/{unsure_scan['id']}/crop", json={"crop_id": bad}, headers=auth)
        assert response.status_code == 422 and response.json()["code"] in ("unknown_crop", "validation_error"), bad


def test_expert_task_closes_when_the_scan_later_becomes_ok(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(crop_id=None, unknown=True)
    first = scan(api_client, auth).json()
    assert first["review_task_id"]
    fake_container.crop_identifier.result = CropResult(crop_id="Apple", confidence=0.95)
    second = api_client.post(f"/v1/scans/{first['id']}/photos", files=photo_files(1), headers=auth).json()
    assert second["status"] == "ok" and second["review_task_id"] is None and second["photos"] == 2
    with session_scope() as db:
        task = db.scalars(select(ReviewTaskRow)).one()
        assert task.status == "resolved" and task.resolution == {"auto": "superseded_by_new_result"}


def test_still_unsure_keeps_one_open_task(api_client, auth, fake_container):
    fake_container.crop_identifier.result = CropResult(crop_id=None, unknown=True)
    first = scan(api_client, auth).json()
    second = api_client.post(f"/v1/scans/{first['id']}/photos", files=photo_files(1), headers=auth).json()
    assert second["review_task_id"] == first["review_task_id"]
    with session_scope() as db:
        assert len(db.scalars(select(ReviewTaskRow)).all()) == 1


# ------------------------------------------------------------------------------------------------ add photos
def test_add_photos_reevaluates_with_all_photos(api_client, auth, fake_container):
    first = scan(api_client, auth).json()
    fake_container.disease_classifier.result = DiseaseResult(
        crop_id="Apple", disease_id=SCAB, confidence=0.97, candidates=[DiseaseCandidate(disease_id=SCAB, confidence=0.97)])
    second = api_client.post(f"/v1/scans/{first['id']}/photos", files=photo_files(2), headers=auth)
    assert second.status_code == 200
    body = second.json()
    assert body["id"] == first["id"] and body["photos"] == 3 and body["disease"]["confidence"] == 0.97
    assert fake_container.crop_identifier.calls[-1]["images"] == 3
    assert fake_container.disease_classifier.calls[-1]["images"] == 3
    assert api_client.get(f"/v1/scans/{first['id']}", headers=auth).json() == body
    with session_scope() as db:
        assert len(db.get(ScanRow, first["id"]).photo_paths) == 3


def test_add_photos_keeps_a_confirmed_crop(api_client, auth, fake_container, unsure_scan):
    api_client.post(f"/v1/scans/{unsure_scan['id']}/crop", json={"crop_id": "Apple"}, headers=auth)
    identify_calls = len(fake_container.crop_identifier.calls)
    body = api_client.post(f"/v1/scans/{unsure_scan['id']}/photos", files=photo_files(1), headers=auth).json()
    assert body["crop"]["source"] == "farmer_confirmed" and len(fake_container.crop_identifier.calls) == identify_calls


def test_add_photos_respects_the_photo_limit(api_client, auth):
    first = scan(api_client, auth, count=3).json()
    ok = api_client.post(f"/v1/scans/{first['id']}/photos", files=photo_files(1), headers=auth)
    assert ok.status_code == 200 and ok.json()["photos"] == 4
    full = api_client.post(f"/v1/scans/{first['id']}/photos", files=photo_files(1), headers=auth)
    assert full.status_code == 400 and full.json()["code"] == "too_many_photos"
    assert "add_photo" not in [s["action"] for s in ok.json()["next_steps"]]


def test_add_photos_from_an_unusable_first_attempt(api_client, auth, fake_container):
    from tests.fakes import FakeQuality

    fake_container.quality = FakeQuality([unusable()])
    first = scan(api_client, auth).json()
    fake_container.quality = FakeQuality()
    second = api_client.post(f"/v1/scans/{first['id']}/photos", files=photo_files(1), headers=auth).json()
    assert second["status"] == "ok" and second["photos"] == 2


# ------------------------------------------------------------------------------------------------ ownership
def test_other_farmers_scans_are_invisible(api_client, auth, login):
    mine = scan(api_client, auth).json()
    other = login("+910000000002")
    assert api_client.get(f"/v1/scans/{mine['id']}", headers=other).status_code == 404
    assert api_client.post(f"/v1/scans/{mine['id']}/photos", files=photo_files(1), headers=other).status_code == 404
    assert api_client.post(f"/v1/scans/{mine['id']}/crop", json={"crop_id": "Apple"}, headers=other).status_code == 404
    listing = api_client.get("/v1/scans", headers=other).json()
    assert listing == {"items": [], "next_cursor": None}
    assert [s["id"] for s in api_client.get("/v1/scans", headers=auth).json()["items"]] == [mine["id"]]


@pytest.mark.parametrize("scan_id", ["0" * 32, "nonexistent", "../../etc/passwd", "a" * 200])
def test_unknown_scan_ids_are_404(api_client, auth, scan_id):
    response = api_client.get(f"/v1/scans/{scan_id}", headers=auth)
    assert response.status_code == 404 and response.json()["code"] in ("scan_not_found", "not_found")


def test_scan_list_pages_newest_first(api_client, auth):
    ids = [scan(api_client, auth).json()["id"] for _ in range(3)]
    first = api_client.get("/v1/scans?limit=2", headers=auth).json()
    assert [s["id"] for s in first["items"]] == [ids[2], ids[1]] and first["next_cursor"] == ids[1]
    second = api_client.get(f"/v1/scans?limit=2&cursor={first['next_cursor']}", headers=auth).json()
    assert [s["id"] for s in second["items"]] == [ids[0]] and second["next_cursor"] is None
    bad = api_client.get("/v1/scans?cursor=garbage", headers=auth)
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_cursor"


# ------------------------------------------------------------------------------------------------ degradation and failure
def test_composer_failure_falls_back_to_the_safe_template(api_client, auth, fake_container):
    fake_container.composer.raises = RuntimeError("llm down")
    body = scan(api_client, auth).json()
    assert body["status"] == "ok" and body["advice"]["validated"] is False
    assert body["advice"]["products"][0]["product_id"] == "P012"                  # products still come from the rules
    assert body["advice"]["headline"]["en"] == "Advice for your plant" and body["advice"]["safety"]


def test_composer_failure_on_an_expert_case_never_suggests_spraying(api_client, auth, fake_container):
    fake_container.composer.raises = RuntimeError("llm down")
    fake_container.rules.output = rule_output("expert_review")
    advice = scan(api_client, auth).json()["advice"]
    assert advice["products"] == [] and "Do not spray" in advice["summary"]["en"]


def test_unvalidated_composer_output_is_flagged(api_client, auth, fake_container):
    fake_container.composer.validated = False
    assert scan(api_client, auth).json()["advice"]["validated"] is False


def test_knowledge_base_failure_only_removes_the_sources(api_client, auth, fake_container):
    fake_container.kb.raises = RuntimeError("index missing")
    body = scan(api_client, auth).json()
    assert body["status"] == "ok" and body["advice"]["sources"] == []


def test_tts_failure_only_removes_the_audio(api_client, auth, fake_container):
    fake_container.audio.fail = True
    body = scan(api_client, auth).json()
    assert body["status"] == "ok" and body["spoken"]["text"]["en"] and body["spoken"]["audio"] == {"hi": None, "en": None}


def test_zoho_diagnosis_failure_is_ignored(api_client, auth, fake_container):
    fake_container.zoho.diagnosis_raises = RuntimeError("zoho 500")
    assert scan(api_client, auth).json()["status"] == "ok"


def test_zoho_history_failure_warns_the_farmer(api_client, auth, fake_container):
    fake_container.zoho.history_raises = RuntimeError("zoho down")
    body = scan(api_client, auth).json()
    assert body["status"] == "ok"
    assert "HISTORY_UNAVAILABLE" in [w["code"] for w in body["advice"]["warnings"]]
    assert "spray record" in body["advice"]["spoken"]["text"]["en"]
    assert fake_container.rules.inputs[0].history == []


def test_weather_failure_runs_the_rules_without_weather(api_client, auth, fake_container):
    fake_container.weather.raises = RuntimeError("no weather")
    assert scan(api_client, auth).json()["status"] == "ok"
    assert fake_container.rules.inputs[0].weather is None


def test_rule_warnings_are_passed_through(api_client, auth, fake_container):
    from app.domain.types import Severity, WarningItem

    fake_container.rules.output = rule_output(warnings=[WarningItem(code="PROPOSED_BAN", level=Severity.yellow, text=lt("Proposed ban"))])
    warnings = scan(api_client, auth).json()["advice"]["warnings"]
    assert warnings == [{"code": "PROPOSED_BAN", "level": "yellow", "text": {"en": "Proposed ban", "hi": "hi:Proposed ban"}}]


@pytest.mark.parametrize("provider,attr", [("quality", "check"), ("crop_identifier", "identify"), ("disease_classifier", "classify"),
                                           ("rules", "recommend")])
def test_failure_of_vision_or_rules_is_a_503_and_stores_nothing(api_client, auth, fake_container, api_settings, provider, attr):
    getattr(fake_container, provider).raises = RuntimeError("model crashed: +910000000001")
    response = scan(api_client, auth)
    assert response.status_code == 503 and response.json()["code"] == "analysis_unavailable"
    assert "model crashed" not in response.text and "Traceback" not in response.text
    with session_scope() as db:
        assert db.scalars(select(ScanRow)).all() == []
    photos = api_client.get("/v1/scans", headers=auth).json()
    assert photos["items"] == []
    assert not list((api_settings.storage_dir / "photos").rglob("*.jpg")) if (api_settings.storage_dir / "photos").exists() else True


def test_a_database_failure_while_saving_rolls_back_and_removes_the_photos(api_client, auth, monkeypatch, api_settings):
    from app.services.scan_service import ScanService

    def boom(self, *_args):
        raise RuntimeError("disk full")

    monkeypatch.setattr(ScanService, "_store_advice", boom)
    response = scan(api_client, auth)
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    with session_scope() as db:
        assert db.scalars(select(ScanRow)).all() == [] and db.scalars(select(ReviewTaskRow)).all() == []
    photos = api_settings.storage_dir / "photos"
    assert not photos.exists() or not list(photos.rglob("*.jpg"))


def test_failure_while_adding_photos_leaves_the_scan_unchanged(api_client, auth, fake_container, api_settings):
    first = scan(api_client, auth).json()
    fake_container.rules.raises = RuntimeError("boom")
    assert api_client.post(f"/v1/scans/{first['id']}/photos", files=photo_files(1), headers=auth).status_code == 503
    assert api_client.get(f"/v1/scans/{first['id']}", headers=auth).json() == first
    assert len(list((api_settings.storage_dir / "photos").rglob("*.jpg"))) == 1


# ------------------------------------------------------------------------------------------------ form fields and limits
@pytest.mark.parametrize("data", [{"client_confidence": "1.5"}, {"client_confidence": "-0.1"}, {"lat": "95", "lon": "10"},
                                  {"lat": "10"}, {"lon": "10"}, {"taken_at": "yesterday"}, {"client_crop": "../x"}])
def test_invalid_form_fields_are_400(api_client, auth, data):
    response = scan(api_client, auth, data=data)
    assert response.status_code == 400 and response.json()["code"].startswith("invalid_")


def test_valid_form_fields_are_accepted(api_client, auth, fake_container):
    response = scan(api_client, auth, data={"lat": "31.1", "lon": "77.3", "taken_at": "2026-05-12T07:00:00+05:30", "client_crop": " Apple "})
    assert response.status_code == 200
    assert fake_container.crop_identifier.calls[0]["client_guess"] == "Apple"
    assert fake_container.weather.calls[0][1:3] == (31.1, 77.3)
    with session_scope() as db:
        row = db.scalars(select(ScanRow)).one()
        assert (row.lat, row.lon, row.client_crop) == (31.1, 77.3, "Apple")


def test_scan_rate_limit_per_farmer(api_client, auth, api_app):
    limiters = RateLimiters.default()
    limiters.scan_farmer = SlidingWindowLimiter(2, 600)
    api_app.state.limiters = limiters
    assert [scan(api_client, auth).status_code for _ in range(3)] == [200, 200, 429]


def test_localized_names_use_the_catalogue():
    from app.services.catalogue import load_catalogue
    from tests.fakes import plain_settings

    catalogue = load_catalogue(str(plain_settings().data_dir))
    assert catalogue.crop_name("Apple") == LocalizedText(en="Apple", hi="सेब")
    assert catalogue.disease_name(SCAB).en == "Apple scab" and "स्कैब" in catalogue.disease_name(SCAB).hi
    assert catalogue.disease_name(None) is None
    assert catalogue.disease_name("Weird___Thing").en == "Weird Thing"
    assert catalogue.canonical_crop(" apple ") == "Apple" and catalogue.canonical_crop("nope") is None
