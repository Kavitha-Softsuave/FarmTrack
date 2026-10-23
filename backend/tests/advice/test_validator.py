"""The validator must catch every violation class. Faulty drafts are made by editing a valid draft (written by MockLLM from the facts)."""
import pytest

from app.advice.prompt import build_facts
from app.advice.validator import recommends_spraying, validate_draft
from app.domain.types import AdviceDraft, ExcludedProduct, LocalizedText, Note, SpokenText
from app.llm.mock import advice_from_facts
from tests.advice.helpers import advice_output, loc, plain_output, ref, warning


def valid_draft(out) -> AdviceDraft:
    return AdviceDraft.model_validate(advice_from_facts(build_facts(out, [], ref())))


def problems(draft, out, notes=()):
    return validate_draft(draft, out, ref(), notes)


def with_step(draft: AdviceDraft, en: str, hi: str) -> AdviceDraft:
    return draft.model_copy(update={"steps": [*draft.steps, loc(en, hi)]})


def has(found, prefix):
    return any(p.startswith(prefix) for p in found)


# ---------------------------------------------------------------------------------------------- a good draft passes
@pytest.mark.parametrize("action", ["spray_now", "wait", "not_needed", "repeat_within_days", "unknown"])
def test_mock_draft_is_valid_for_every_timing(action):
    out = advice_output(pids=("P001", "P002", "P004"), action=action)
    assert problems(valid_draft(out), out) == []


def test_mock_draft_is_valid_for_a_vegetable_with_hectare_doses():
    out = advice_output(pids=("P072", "P083", "P086"), crop_id="Potato", disease_id="Potato___Late_blight")
    assert problems(valid_draft(out), out) == []


# ---------------------------------------------------------------------------------------------- products
def test_product_not_in_rule_output_is_caught():
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), "Dodine is also good.", "डोडीन भी अच्छा है।")
    assert has(problems(draft, out), "product_not_in_rules:dodine")


def test_brand_of_another_product_is_caught():
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), "Ask for Bavistin at the shop.", "दुकान से बाविस्टिन माँगें।")
    assert "product_not_in_rules:bavistin" in problems(draft, out)


def test_brand_of_the_listed_product_is_allowed():
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), "Ask for Captaf or Captax at the shop.", "दुकान से कैप्टान माँगें।")
    assert problems(draft, out) == []


def test_hindi_name_of_an_unlisted_product_is_caught_with_or_without_nukta():
    out = advice_output(pids=("P001",))
    for hindi in ("ज़ीरम भी डालें।", "जीरम भी डालें।"):
        draft = with_step(valid_draft(out), "Also a second medicine.", hindi)
        assert "product_not_in_rules:ziram" not in problems(draft, out)           # Latin scan does not see Devanagari ...
        assert any(p.startswith("product_not_in_rules:") and "रम" in p for p in problems(draft, out))   # ... the Hindi scan does


def test_banned_and_off_label_names_are_caught():
    out = advice_output(pids=("P001",))
    for en in ("Miravis Duo works well.", "Use Streptomycin on the leaves.", "Dicofol kills mites.", "Meothrin is cheap."):
        draft = with_step(valid_draft(out), en, "यह एक वाक्य है।")
        assert has(problems(draft, out), "banned_or_offlabel_product_mentioned:"), en


def test_excluded_product_is_caught_even_if_the_rules_mention_it():
    out = advice_output(pids=("P001",), excluded=[ExcludedProduct(product_id="P003", active_ingredient="Ziram", reasons=["same_frac_as_last_spray"])],
                        warnings=[warning()])
    out.warnings[0].text = loc("Ziram was used last week.", "पिछले हफ़्ते ज़ीरम इस्तेमाल हुआ था।")
    draft = with_step(valid_draft(out), "Ziram would also work.", "ज़ीरम भी चलेगा।")
    assert "excluded_product_mentioned:ziram" in problems(draft, out)


def test_unknown_chemical_looking_word_is_caught():
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), "Zetaconazole is the best choice.", "यह एक वाक्य है।")
    assert "unlisted_chemical_name:zetaconazole" in problems(draft, out)


def test_declared_product_ids_must_belong_to_the_rules():
    out = advice_output(pids=("P001",))
    draft = valid_draft(out).model_copy(update={"product_ids_mentioned": ["P001", "P002"]})
    assert "declared_product_not_in_rules:P002" in problems(draft, out)
    draft = valid_draft(out).model_copy(update={"product_ids_mentioned": []})
    assert "no_product_declared" in problems(draft, out)


def test_draft_that_names_no_product_is_rejected():
    out = advice_output(pids=("P001",))
    draft = AdviceDraft(headline=loc("Advice", "सलाह"), summary=loc("Spray soon.", "जल्दी छिड़कें।"), steps=[loc("Spray when dry.", "सूखे में छिड़कें।")],
                        spoken=SpokenText(en="Spray soon. Ask your expert.", hi="जल्दी छिड़कें। विशेषज्ञ से पूछें।"), product_ids_mentioned=["P001"])
    found = problems(draft, out)
    assert "no_product_named:en" in found and "no_product_named:hi" in found


def test_name_mentioned_in_a_rule_warning_is_allowed_in_a_caution_but_not_as_advice():
    warn = warning()
    warn.text = loc("Keep 15 days away from horticultural mineral oil.", "बागवानी खनिज तेल से 15 दिन दूर रखें।")
    out = advice_output(pids=("P001",), warnings=[warn])
    caution = with_step(valid_draft(out), "Do not spray horticultural mineral oil within 15 days.", "तेल से 15 दिन पहले न छिड़कें।")
    assert problems(caution, out) == []
    advice = with_step(valid_draft(out), "Spray horticultural mineral oil as well.", "तेल भी छिड़कें।")
    assert "recommends_product_not_in_rules" in problems(advice, out)


# ---------------------------------------------------------------------------------------------- doses and numbers
@pytest.mark.parametrize("en", [
    "Captan: 700 g in 200 litres of water.",        # wrong amount
    "Captan: 600 ml in 200 litres of water.",       # right number, wrong unit (ml instead of g)
    "Captan: 600 g in 100 litres of water.",        # wrong water volume
    "Captan: 0.7 kg in 200 litres of water.",       # wrong amount in another unit
    "Captan: seven hundred grams in 200 litres.",   # wrong amount written as words
])
def test_wrong_dose_is_caught(en):
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), en, "कैप्टान: 200 लीटर पानी में 600 ग्राम।")
    assert has(problems(draft, out), "dose_mismatch:"), en


def test_equivalent_units_are_not_flagged():
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), "Captan: 0.6 kg in 200 L of water.", "कैप्टान: 200 लीटर पानी में 600 ग्राम।")
    assert problems(draft, out) == []


def test_wrong_dose_in_hindi_is_caught():
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), "Captan: 600 g in 200 litres of water.", "कैप्टान: 200 लीटर पानी में 800 ग्राम।")
    assert has(problems(draft, out), "dose_mismatch:")


def test_one_products_dose_on_another_product_is_caught():
    out = advice_output(pids=("P001", "P002"))          # captan 600 g, dodine 200 g
    draft = with_step(valid_draft(out), "Dodine: 600 g in 200 litres of water.", "डोडीन: 200 लीटर पानी में 200 ग्राम।")
    assert has(problems(draft, out), "dose_mismatch:600")


def test_dose_declared_in_doses_mentioned_is_checked():
    out = advice_output(pids=("P001",))
    draft = valid_draft(out).model_copy(update={"doses_mentioned": ["900 g in 200 litres of water"]})
    assert has(problems(draft, out), "dose_mismatch:900")


def test_declared_product_whose_dose_is_missing_is_caught():
    out = advice_output(pids=("P001",))
    draft = AdviceDraft(headline=loc("Captan", "कैप्टान"), summary=loc("Use Captan.", "कैप्टान लें।"), steps=[loc("Captan is good.", "कैप्टान अच्छा है।")],
                        spoken=SpokenText(en="Use Captan. Ask your expert.", hi="कैप्टान लें। विशेषज्ञ से पूछें।"), product_ids_mentioned=["P001"])
    found = problems(draft, out)
    assert "dose_missing:P001:en" in found and "dose_missing:P001:hi" in found


def test_wrong_waiting_period_is_caught():
    out = advice_output(pids=("P002",))                 # dodine: 21 days
    draft = with_step(valid_draft(out), "Dodine: do not harvest for 10 days after spraying.", "डोडीन: छिड़काव के बाद तुड़ाई न करें।")
    found = problems(draft, out)
    assert has(found, "waiting_period_mismatch:10") or has(found, "number_not_in_rules:10")


def test_waiting_period_of_another_product_is_caught():
    out = advice_output(pids=("P002", "P004"))          # dodine 21 days, fluxapyroxad 33 days
    draft = with_step(valid_draft(out), "Dodine: do not harvest for 33 days after spraying.", "डोडीन: छिड़काव के बाद तुड़ाई न करें।")
    assert has(problems(draft, out), "waiting_period_mismatch:33")


def test_waiting_period_invented_when_the_rules_have_none_is_caught():
    out = advice_output(pids=("P001",))                 # captan: no waiting period in the master
    draft = with_step(valid_draft(out), "Captan: do not harvest for 14 days after spraying.", "कैप्टान: छिड़काव के बाद तुड़ाई न करें।")
    assert has(problems(draft, out), "waiting_period_mismatch:14")


def test_numbers_from_the_rule_texts_are_allowed():
    out = advice_output(pids=("P001",))                 # timing text says 12 hours; non-chemical says 5% urea
    draft = with_step(valid_draft(out), "No rain is expected for 12 hours. Use 5% urea on the floor.", "अगले 12 घंटे बारिश नहीं। 5% यूरिया डालें।")
    assert problems(draft, out) == []
    bad = with_step(valid_draft(out), "No rain is expected for 36 hours.", "अगले 36 घंटे बारिश नहीं।")
    assert has(problems(bad, out), "number_not_in_rules:36")


def test_numbers_from_retrieved_notes_are_allowed_for_non_dose_units():
    out = advice_output(pids=("P001",))
    note = Note(note_id="N1", topic="rule", text_en="Keep a 12-14 day interval between sprays.", text_hi="छिड़काव के बीच 12-14 दिन का अंतर रखें।")
    draft = with_step(valid_draft(out), "Keep 14 days between sprays.", "छिड़काव के बीच 14 दिन का अंतर रखें।")
    assert problems(draft, out, [note]) == []
    assert has(problems(draft, out), "number_not_in_rules:14")


def test_phone_numbers_are_caught():
    out = advice_output(pids=("P001",))
    draft = with_step(valid_draft(out), "Call 1-800-222-1222 if you feel sick.", "बीमार लगे तो 1-800-222-1222 पर फ़ोन करें।")
    assert "phone_number_in_text" in problems(draft, out)


# ---------------------------------------------------------------------------------------------- timing and spraying
def test_spraying_advice_when_the_timing_is_wait_is_caught():
    out = advice_output(pids=("P001",), action="wait")
    draft = with_step(valid_draft(out), "Spray Captan now.", "अभी कैप्टान छिड़कें।")
    found = problems(draft, out)
    assert "spray_recommended_when_timing_wait" in found


def test_conditional_spraying_when_the_timing_is_wait_is_allowed():
    out = advice_output(pids=("P001",), action="wait")
    draft = with_step(valid_draft(out), "When the rain stops, spray Captan.", "बारिश रुकने के बाद कैप्टान छिड़कें।")
    assert problems(draft, out) == []


def test_spraying_advice_when_not_needed_is_caught():
    out = advice_output(pids=("P001",), action="not_needed")
    draft = with_step(valid_draft(out), "Spray Captan.", "कैप्टान छिड़कें।")
    assert "spray_recommended_when_timing_not_needed" in problems(draft, out)


def test_wait_must_be_conveyed_in_both_languages():
    out = advice_output(pids=("P001",), action="wait")
    draft = AdviceDraft(headline=loc("Captan", "कैप्टान"), summary=loc("Captan helps.", "कैप्टान मदद करता है।"),
                        steps=[loc("Captan: 600 g in 200 litres of water.", "कैप्टान: 200 लीटर पानी में 600 ग्राम।")],
                        spoken=SpokenText(en="Captan helps. It is cheap. Ask your expert.", hi="कैप्टान मदद करता है। यह सस्ता है। विशेषज्ञ से पूछें।"),
                        product_ids_mentioned=["P001"])
    found = problems(draft, out)
    assert "timing_not_conveyed:en" in found and "timing_not_conveyed:hi" in found


def test_repeat_days_must_be_stated():
    out = advice_output(pids=("P001",), action="repeat_within_days")      # repeat within 7 days
    draft = valid_draft(out)
    draft = draft.model_copy(update={"steps": [loc("Spray again later.", "बाद में दोबारा छिड़कें।"), *draft.steps[1:]],
                                     "spoken": SpokenText(en="Use Captan, 600 g in 200 L. Spray again later. Ask your expert.",
                                                          hi="कैप्टान लें, 200 लीटर पानी में 600 ग्राम। बाद में दोबारा छिड़कें। विशेषज्ञ से पूछें।")})
    assert "repeat_days_missing" in problems(draft, out)


@pytest.mark.parametrize("status", ["expert_review", "no_approved_data", "not_a_disease", "needs_more_info"])
def test_no_medicine_status_never_recommends_spraying_or_names_a_product(status):
    out = plain_output(status)
    safe = AdviceDraft(headline=loc("Wait for the expert", "विशेषज्ञ का इंतज़ार करें"), summary=loc("Ask an expert. Do not spray anything.", "विशेषज्ञ से पूछें। कुछ न छिड़कें।"),
                       steps=[loc("Remove fallen leaves.", "गिरी पत्तियाँ हटाएँ।")],
                       spoken=SpokenText(en="I am not sure. An expert will look. Do not spray.", hi="मुझे पक्का नहीं पता। विशेषज्ञ देखेंगे। कुछ न छिड़कें।"))
    assert problems(safe, out) == []
    for en, hi in (("Spray Captan 600 g in 200 litres of water.", "कैप्टान छिड़कें।"), ("Spray something strong today.", "आज कुछ छिड़कें।"),
                   ("Use a fungicide.", "फफूंदनाशक का इस्तेमाल करें।")):
        found = problems(with_step(safe, en, hi), out)
        assert found, en
    assert has(problems(with_step(safe, "Spray Captan.", "कैप्टान छिड़कें।"), out), "product_not_in_rules:captan")


def test_expert_review_must_mention_the_expert():
    out = plain_output("expert_review")
    draft = AdviceDraft(headline=loc("Not sure", "पक्का नहीं"), summary=loc("Watch the plants.", "पौधों पर नज़र रखें।"), steps=[loc("Keep checking.", "देखते रहें।")],
                        spoken=SpokenText(en="Not sure. Keep watching. Do not spray.", hi="पक्का नहीं। देखते रहें। न छिड़कें।"))
    found = problems(draft, out)
    assert "expert_not_mentioned:en" in found and "expert_not_mentioned:hi" in found


def test_other_disease_is_caught_but_the_diagnosed_one_is_fine():
    out = advice_output(pids=("P001",))
    assert problems(with_step(valid_draft(out), "This is Apple scab.", "यह सेब का स्कैब है।"), out) == []
    found = problems(with_step(valid_draft(out), "It may also be powdery mildew.", "शायद सेब का चूर्णिल आसिता भी हो।"), out)
    assert "disease_not_in_rules:powdery mildew" in found
    assert any(p.startswith("disease_not_in_rules:") and "चूर्णिल" in p for p in found)


# ---------------------------------------------------------------------------------------------- language and shape
def test_missing_hindi_is_caught():
    out = advice_output(pids=("P001",))
    draft = valid_draft(out)
    for field in ("headline", "summary"):
        broken = draft.model_copy(update={field: LocalizedText(en="Advice", hi="")})
        assert f"empty_text:{field}.hi" in problems(broken, out)
    broken = draft.model_copy(update={"spoken": SpokenText(en=draft.spoken.en, hi="")})
    assert "empty_text:spoken.hi" in problems(broken, out)
    broken = with_step(draft, "Another step.", "")
    assert f"empty_text:steps[{len(draft.steps)}].hi" in problems(broken, out)


def test_missing_english_and_no_steps_are_caught():
    out = advice_output(pids=("P001",))
    broken = valid_draft(out).model_copy(update={"headline": LocalizedText(en="", hi="सलाह"), "steps": []})
    found = problems(broken, out)
    assert "empty_text:headline.en" in found and "no_steps" in found


def test_hindi_field_written_in_latin_letters_is_caught():
    out = advice_output(pids=("P001",))
    broken = valid_draft(out).model_copy(update={"summary": loc("Use Captan.", "Use Captan.")})
    assert "hindi_not_devanagari:summary" in problems(broken, out)
    broken = valid_draft(out).model_copy(update={"summary": loc("कैप्टान लें।", "कैप्टान लें।")})
    assert "english_contains_devanagari:summary" in problems(broken, out)


def test_spoken_length_is_bounded():
    out = advice_output(pids=("P001",))
    draft = valid_draft(out)
    short = draft.model_copy(update={"spoken": SpokenText(en="Use Captan, 600 g in 200 L.", hi=draft.spoken.hi)})
    assert any(p.startswith("spoken_length:en:1") for p in problems(short, out))
    long = draft.model_copy(update={"spoken": SpokenText(en=draft.spoken.en, hi=" ".join(["कैप्टान लें।"] * 9))})
    assert any(p.startswith("spoken_length:hi:9") for p in problems(long, out))


def test_product_declared_when_there_is_no_medicine():
    out = plain_output("expert_review")
    draft = AdviceDraft(headline=loc("Not sure", "पक्का नहीं"), summary=loc("Ask the expert.", "विशेषज्ञ से पूछें।"), steps=[loc("Wait.", "रुकें।")],
                        spoken=SpokenText(en="Not sure. Ask the expert. Do not spray.", hi="पक्का नहीं। विशेषज्ञ से पूछें। न छिड़कें।"), product_ids_mentioned=["P001"])
    assert "product_declared_without_medicine" in problems(draft, out)


# ---------------------------------------------------------------------------------------------- the spray-sentence helper
@pytest.mark.parametrize("sentence,lang,expected", [
    ("Spray Captan now.", "en", True),
    ("Apply 600 g in 200 litres.", "en", True),
    ("Do not spray now.", "en", False),
    ("Wait for the rain to stop, then spray.", "en", False),
    ("Ask your expert before you spray.", "en", False),
    ("Spraying is not needed.", "en", False),
    ("अभी कैप्टान छिड़कें।", "hi", True),
    ("अभी छिड़काव न करें।", "hi", False),
    ("बारिश रुकने के बाद छिड़कें।", "hi", False),
    ("विशेषज्ञ से पूछकर छिड़कें।", "hi", False),
])
def test_recommends_spraying(sentence, lang, expected):
    assert recommends_spraying(sentence, lang) is expected


def test_use_verbs_only_count_when_asked():
    assert recommends_spraying("Use Captan.", "en") is False
    assert recommends_spraying("Use Captan.", "en", include_use=True) is True
    assert recommends_spraying("कैप्टान का इस्तेमाल करें।", "hi", include_use=True) is True
