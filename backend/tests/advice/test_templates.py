import re

import pytest

from app.advice.names import has_devanagari
from app.advice.quantities import MASS, PERCENT, VOLUME, extract_quantities
from app.advice.templates import build_template, finalize_draft
from app.advice.validator import validate_draft
from app.domain.types import AdviceDraft, Severity
from tests.advice.helpers import advice_output, loc, master_rows, plain_output, product, ref, risk, warning

STATUSES = ["advice", "expert_review", "no_approved_data", "not_a_disease", "needs_more_info"]


def final(out) -> AdviceDraft:
    return finalize_draft(build_template(out, ref()), out, ref())


def all_texts(draft: AdviceDraft, lang: str) -> list[str]:
    fields = [draft.headline, draft.summary, *draft.steps, *draft.safety]
    return [getattr(f, lang) for f in fields] + [getattr(draft.spoken, lang)]


def outputs_for_every_status():
    yield advice_output(pids=("P001", "P002", "P004"), warnings=[warning()], risks=[risk()])
    for status in STATUSES[1:]:
        yield plain_output(status, warnings=[warning("OFF_LABEL_HISTORY", Severity.red)], risks=[risk()])
        yield plain_output(status, non_chemical=advice_output().non_chemical)
        yield plain_output(status)


@pytest.mark.parametrize("out", list(outputs_for_every_status()), ids=lambda o: o.status)
def test_template_is_valid_and_complete_in_both_languages(out):
    draft = build_template(out, ref())
    assert validate_draft(draft, out, ref()) == []
    done = finalize_draft(draft, out, ref())
    for lang in ("en", "hi"):
        texts = all_texts(done, lang)
        assert all(t.strip() for t in texts), (out.status, lang)
        assert all(has_devanagari(t) for t in all_texts(done, "hi")), out.status
        assert not any(has_devanagari(t) for t in texts if lang == "en"), out.status


@pytest.mark.parametrize("pid", sorted(master_rows()))
def test_advice_template_is_valid_for_every_master_product(pid):
    p = product(pid)
    for action in ("spray_now", "wait", "repeat_within_days", "not_needed"):
        out = advice_output(pids=(pid,), action=action, crop_id=p.crop, disease_id=None)
        assert validate_draft(build_template(out, ref()), out, ref()) == [], (pid, action)


def test_advice_template_content():
    out = advice_output(pids=("P001", "P002"), warnings=[warning()], risks=[risk()])
    draft = final(out)
    en = " ".join(all_texts(draft, "en"))
    hi = " ".join(all_texts(draft, "hi"))
    assert draft.headline.en == "Apple scab: what to do" and "सेब का स्कैब" in draft.headline.hi
    assert "Captan (for example Captaf): 600 g in 200 litres of water." in en
    assert "Dodine (for example Noor): 200 g in 200 litres of water. Do not harvest for at least 21 days after you spray." in en
    assert "कैप्टान (जैसे Captaf): 200 लीटर पानी में 600 ग्राम।" in hi
    assert "छिड़काव के बाद कम से कम 21 दिन तक तुड़ाई न करें।" in hi
    assert "You can spray now." in en and "No rain is expected in the next 12 hours." in en
    assert "Choose one of the medicines below" in en
    assert "Compost fallen leaves or spray 5% urea on the orchard floor." in draft.steps[-1].en
    assert draft.product_ids_mentioned == ["P001", "P002"]
    assert draft.doses_mentioned == ["600 g in 200 litres of water", "200 g in 200 litres of water"]


def test_advice_template_shows_at_most_three_products_and_one_brand_each():
    out = advice_output(pids=("P001", "P002", "P003", "P004", "P005"))
    draft = final(out)
    assert draft.product_ids_mentioned == ["P001", "P002", "P003"]
    assert not re.search("Sercadis", " ".join(all_texts(draft, "en")))


def test_brand_is_shown_without_company():
    out = advice_output(pids=("P001",))
    out.products[0] = product("P001", brand_examples=["Captaf (Rallis India Ltd)", "Captax (India Pesticides Limited)"])
    text = " ".join(all_texts(final(out), "en"))
    assert "for example Captaf)" in text and "Rallis" not in text


def test_waiting_period_sentence_for_each_case():
    with_days = " ".join(all_texts(final(advice_output(pids=("P002",))), "en"))
    without = " ".join(all_texts(final(advice_output(pids=("P001",))), "en"))
    assert "at least 21 days" in with_days
    assert "No waiting period is listed for this medicine, so ask your expert if harvest is near." in without


@pytest.mark.parametrize("action,en,hi", [
    ("spray_now", "You can spray now.", "आप अभी छिड़काव कर सकते हैं।"),
    ("wait", "Do not spray now. Wait until it is safe to spray.", "अभी छिड़काव न करें।"),
    ("not_needed", "Spraying is not needed now.", "अभी छिड़काव की ज़रूरत नहीं है।"),
    ("repeat_within_days", "Spray again within 7 days.", "7 दिन के अंदर दोबारा छिड़काव करें।"),
    ("unknown", "Ask your expert for the best time to spray.", "छिड़काव का सही समय खेती के जानकार से पूछें।"),
])
def test_timing_sentence_matches_the_rule_action(action, en, hi):
    draft = final(advice_output(pids=("P001",), action=action))
    assert en in draft.steps[0].en and hi in draft.steps[0].hi
    assert en in draft.spoken.en.replace("seven", "7") or action == "wait" or "7" in en


def test_severity_changes_the_tone():
    summaries = {s: final(advice_output(severity=s)).summary.en for s in ("green", "yellow", "red")}
    assert "not urgent" in summaries["green"] and "attention soon" in summaries["yellow"] and "serious" in summaries["red"]


def test_warnings_come_first_and_most_severe_first():
    red = warning("OFF_LABEL_HISTORY", Severity.red)
    red.text = loc("Red warning.", "लाल चेतावनी।")
    yellow = warning("PROPOSED_BAN", Severity.yellow)
    yellow.text = loc("Yellow warning.", "पीली चेतावनी।")
    out = advice_output(warnings=[yellow, red])
    safety = [s.en for s in final(out).safety]
    assert safety.index("Red warning.") < safety.index("Yellow warning.")
    assert safety[0] == "Red warning."


def test_product_warnings_are_included_once():
    p = product("P001", warnings=[warning()])
    out = advice_output(pids=("P002",), warnings=[warning()])
    out.products.append(p)
    safety = [s.en for s in final(out).safety]
    assert safety.count(warning().text.en) == 1


def test_safety_lines_come_from_the_notes_and_never_carry_the_us_poison_number():
    out = advice_output()
    for status in STATUSES:
        o = out if status == "advice" else plain_output(status)
        text = " ".join(all_texts(final(o), "en") + all_texts(final(o), "hi"))
        assert "1-800" not in text and "222-1222" not in text and "1800" not in text
    safety = " ".join(s.en for s in final(out).safety)
    assert "gloves and goggles" in safety                      # N128 (HP 2026 safe use)
    assert "Do not mix any other pesticide" in safety and "confirm with your agriculture expert" in safety


def test_expert_review_says_not_sure_gives_no_medicine_and_promises_no_expert_reply():
    out = plain_output("expert_review", crop="Apple", disease_id="Apple___Marssonina_blotch", severity=Severity.red)
    draft = final(out)
    en = " ".join(all_texts(draft, "en"))
    hi = " ".join(all_texts(draft, "hi"))
    assert "is not sure what is wrong" in en and "Please do not spray any medicine yet" in en
    assert "ऐप को पक्का नहीं पता" in hi and "अभी कोई दवा न छिड़कें" in hi
    assert "Do not spray any medicine until you know what is wrong." in draft.steps[0].en
    # the owner wants an immediate answer and no callback: nothing may promise that an expert will answer later
    for promise in ("will look at your photo", "will advise you", "until the expert answers", "when it comes", "call you back"):
        assert promise not in en
    assert "Marssonina" not in en and "मार्सोनिना" not in hi             # the app is not sure: it names no disease
    assert draft.product_ids_mentioned == [] and draft.doses_mentioned == []
    assert not ref().latin_matcher.find(en) and not ref().deva_matcher.find(hi)       # no product, brand or chemical name at all
    for text in (en, hi):
        assert not [q for q in extract_quantities(text) if q.family in (MASS, VOLUME, PERCENT)]


def test_expert_review_uses_the_rules_general_measures_but_never_one_that_says_to_spray():
    clean = loc("Clean the orchard floor.", "बाग की ज़मीन साफ़ करें।")
    spray = loc("Spray the basin too.", "थाले में भी छिड़काव करें।")
    out = plain_output("expert_review", non_chemical=[clean, spray])
    draft = final(out)
    assert clean in draft.steps and spray not in draft.steps
    assert validate_draft(build_template(out, ref()), out, ref()) == []
    generic = final(plain_output("expert_review"))
    assert any("Remove fallen leaves" in s.en for s in generic.steps)
    only_spray = final(plain_output("expert_review", non_chemical=[spray]))
    assert any("Remove fallen leaves" in s.en for s in only_spray.steps)           # nothing usable from the rules: the generic ones


def test_no_approved_data_says_so_and_gives_no_medicine():
    draft = final(plain_output("no_approved_data", crop="Pear"))
    assert "does not have approved medicine advice for your pear crop yet" in draft.summary.en
    assert "pear" in draft.spoken.en and "ask a local agriculture expert" in draft.spoken.en
    assert draft.product_ids_mentioned == []


def test_not_a_disease_and_needs_more_info_texts():
    healthy = final(plain_output("not_a_disease", crop="Tomato"))
    assert "does not see a disease on this tomato leaf" in healthy.summary.en and "No medicine is needed now" in healthy.summary.en
    more = final(plain_output("needs_more_info"))
    assert "one more clear photo" in more.summary.en and "daylight" in more.steps[0].en
    assert "daylight" in more.spoken.en


def test_crop_names_in_hindi_for_glossary_fallback_and_unknown_crops():
    assert "सेब" in final(plain_output("expert_review", crop="Apple")).summary.hi
    assert "टमाटर" in final(plain_output("expert_review", crop="Tomato")).summary.hi
    assert "नाशपाती" in final(plain_output("no_approved_data", crop="Pear")).summary.hi          # not in the glossary: built-in draft name
    assert "dragon fruit" in final(plain_output("no_approved_data", crop="Dragon_fruit")).summary.hi    # unknown: the English name, not a blank


def test_spoken_hindi_for_a_fallback_crop_has_no_latin_letters():
    spoken = final(plain_output("no_approved_data", crop="Pear")).spoken.hi
    assert "नाशपाती" in spoken and not re.search("[A-Za-z]", spoken)


def test_advice_without_any_product_is_treated_like_expert_review():
    out = advice_output(pids=())
    draft = final(out)
    assert draft.headline.en.startswith("Not sure yet") and draft.product_ids_mentioned == []
    assert validate_draft(build_template(out, ref()), out, ref()) == []


def test_missing_hindi_in_a_rule_text_falls_back_to_english_instead_of_blank():
    out = advice_output(non_chemical=[loc("Remove infected leaves.", "")])
    assert loc("Remove infected leaves.", "Remove infected leaves.") in final(out).steps
