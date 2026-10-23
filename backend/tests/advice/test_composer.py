import json

import pytest

from app.advice import prompt
from app.advice.composer import LLMAdviceComposer
from app.advice.factory import build_advice_composer
from app.advice.templates import build_template, finalize_draft
from app.config import Settings
from app.domain.types import Note
from app.interfaces import AdviceComposer, LLMError
from app.llm.facts import extract_facts
from app.llm.mock import MockLLM, advice_from_facts
from tests.advice.helpers import DATA_DIR, advice_output, loc, plain_output, ref, rule_input, warning


def NO_DIGIT(text: str) -> bool:  # noqa: N802
    return not any(ch.isdigit() for ch in text)


class FakeLLM:
    """Returns a prepared object (or raises it) and remembers the prompts it saw."""
    name = "fake"

    def __init__(self, result):
        self.result = result
        self.prompts: list[str] = []

    def generate_json(self, prompt_text, schema, schema_name="response", images=None):
        self.prompts.append(prompt_text)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def good_answer(out) -> dict:
    return advice_from_facts(prompt.build_facts(out, [], ref()))


def composer(llm, **kw) -> LLMAdviceComposer:
    return LLMAdviceComposer(llm, ref(), **kw)


def compose(llm, out, notes=None, **kw):
    return composer(llm, **kw).compose(rule_input(out), out, notes or [])


# ---------------------------------------------------------------------------------------------- happy path
def test_mock_llm_pipeline_is_used_and_validated():
    out = advice_output(pids=("P001", "P002"))
    result = compose(MockLLM(), out)
    assert result.used_llm and result.validated and result.problems == []
    assert result.draft.product_ids_mentioned == ["P001", "P002"]


def test_llm_output_is_finalised_spoken_words_and_mandatory_lines():
    out = advice_output(pids=("P001",), warnings=[warning()])
    result = compose(MockLLM(), out)
    spoken = result.draft.spoken
    assert NO_DIGIT(spoken.en) and NO_DIGIT(spoken.hi)
    assert "six hundred grams in two hundred litres of water" in spoken.en
    assert "gloves" in spoken.en and "दस्ताने" in spoken.hi                       # appended: the LLM did not have to write it
    safety = [s.en for s in result.draft.safety]
    assert warning().text.en in safety
    assert any("gloves and goggles" in s for s in safety) and any("Do not mix any other pesticide" in s for s in safety)
    assert any("confirm with your agriculture expert" in s for s in safety)


def test_composer_satisfies_the_interface_and_factory_builds_it():
    settings = Settings(data_dir=DATA_DIR)
    comp = build_advice_composer(settings, MockLLM())
    assert isinstance(comp, AdviceComposer)
    out = advice_output()
    assert comp.compose(rule_input(out), out, []).used_llm


# ---------------------------------------------------------------------------------------------- the LLM is only asked for 'advice'
@pytest.mark.parametrize("status", ["expert_review", "no_approved_data", "not_a_disease", "needs_more_info"])
def test_other_statuses_use_the_template_without_calling_the_llm(status):
    llm = FakeLLM({})
    out = plain_output(status)
    result = compose(llm, out)
    assert llm.prompts == []
    assert result.used_llm is False and result.validated is True and result.problems == []
    assert result.draft == finalize_draft(build_template(out, ref()), out, ref())


def test_llm_can_be_enabled_for_other_statuses_and_is_still_validated():
    out = plain_output("expert_review")
    answer = good_answer(out)                                   # the mock writes a safe 'not sure' text for this status
    ok = compose(FakeLLM(answer), out, llm_statuses={"advice", "expert_review"})
    assert ok.used_llm and ok.validated
    answer["steps"].append({"en": "Spray Captan 600 g in 200 litres of water.", "hi": "कैप्टान छिड़कें।"})
    bad = compose(FakeLLM(answer), out, llm_statuses={"expert_review"})
    assert bad.used_llm is False and bad.validated is False
    assert any("captan" in p for p in bad.problems)


# ---------------------------------------------------------------------------------------------- fallback to the safe template
def faulty(out, mutate):
    answer = good_answer(out)
    mutate(answer)
    return answer


@pytest.mark.parametrize("name,mutate,expected", [
    ("unknown product", lambda a: a["steps"].append({"en": "Also use Mancozeb.", "hi": "मैन्कोज़ेब भी डालें।"}), "product_not_in_rules:mancozeb"),
    ("wrong dose", lambda a: a["steps"].append({"en": "Captan: 900 g in 200 litres of water.", "hi": "कैप्टान: 900 ग्राम।"}), "dose_mismatch:900 g"),
    ("excluded or banned name", lambda a: a["steps"].append({"en": "Streptomycin helps.", "hi": "यह एक वाक्य है।"}), "banned_or_offlabel_product_mentioned:streptomycin"),
    ("missing hindi", lambda a: a.update(summary={"en": "Advice.", "hi": ""}), "empty_text:summary.hi"),
])
def test_validation_failure_returns_the_template_with_problems(name, mutate, expected):
    out = advice_output(pids=("P001",))
    result = compose(FakeLLM(faulty(out, mutate)), out)
    assert result.used_llm is False and result.validated is False, name
    assert any(p.startswith(expected) for p in result.problems), (name, result.problems)
    template = finalize_draft(build_template(out, ref()), out, ref())
    assert result.draft == template                            # exactly the safe template, nothing of the LLM text


def test_spraying_when_the_rules_say_wait_falls_back():
    out = advice_output(pids=("P001",), action="wait")
    answer = faulty(out, lambda a: a["steps"].append({"en": "Spray Captan now.", "hi": "अभी कैप्टान छिड़कें।"}))
    result = compose(FakeLLM(answer), out)
    assert not result.validated and "spray_recommended_when_timing_wait" in result.problems
    assert "Do not spray now" in result.draft.steps[0].en                    # the template carries the rule's decision


@pytest.mark.parametrize("failure", [LLMError("boom"), RuntimeError("unexpected"), TimeoutError()])
def test_llm_failure_returns_the_template(failure):
    out = advice_output()
    result = compose(FakeLLM(failure), out)
    assert result.used_llm is False and result.validated is False
    assert result.problems == [f"llm_error:{type(failure).__name__}"]
    assert result.draft.steps and result.draft.product_ids_mentioned


def test_output_that_does_not_fit_the_schema_returns_the_template():
    out = advice_output()
    result = compose(FakeLLM({"headline": "not an object"}), out)
    assert result.validated is False and result.problems == ["llm_output_not_valid_schema"]


# ---------------------------------------------------------------------------------------------- what the LLM is shown
def test_prompt_has_the_rule_facts_and_no_farmer_data():
    out = advice_output(pids=("P001",), warnings=[warning()])
    llm = FakeLLM(good_answer(out))
    compose(llm, out)
    text = llm.prompts[0]
    for private in ("Test Farmer", "+910000000001", "F001", "Kotgarh"):
        assert private not in text
    facts = extract_facts(text)
    assert facts["task"] == "advice" and facts["status"] == "advice" and facts["crop"]["en"] == "apple"
    assert facts["products"][0]["dose_text"]["en"] == "600 g in 200 litres of water"
    assert facts["products"][0]["brand_example"] == "Captaf"
    assert facts["timing"]["action"] == "spray_now" and facts["disease"]["en"] == "Apple scab"
    assert "excluded" not in json.dumps(facts) and "trace" not in facts


def test_prompt_never_carries_the_us_poison_number():
    out = advice_output(pids=("P001",))
    notes = [Note(note_id="N129", topic="rule", text_en="First aid: call 1-800-222-1222.", text_hi="प्राथमिक उपचार: 1-800-222-1222 पर फ़ोन करें।"),
             Note(note_id="N1", topic="product_use", text_en="Captan is a contact fungicide.", text_hi="कैप्टान एक संपर्क फफूंदनाशक है।")]
    llm = FakeLLM(good_answer(out))
    compose(llm, out, notes)
    assert "1-800" not in llm.prompts[0] and "222-1222" not in llm.prompts[0]
    assert "N1" in llm.prompts[0] and "N129" not in llm.prompts[0]


def test_prompt_limits_notes_and_their_length():
    out = advice_output()
    notes = [Note(note_id=f"N{i}", topic="product_use", text_en="x" * 2000, text_hi="y") for i in range(20)]
    facts = prompt.build_facts(out, notes, ref())
    assert len(facts["notes"]) == prompt.MAX_NOTES and all(len(n["text_en"]) == prompt.MAX_NOTE_CHARS for n in facts["notes"])


def test_schema_is_strict_compatible():
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for child in node.values():
                check(child)
        elif isinstance(node, list):
            for child in node:
                check(child)
    check(prompt.ADVICE_SCHEMA)
    assert set(prompt.ADVICE_SCHEMA["properties"]) == {"headline", "summary", "steps", "safety", "spoken", "product_ids_mentioned", "doses_mentioned"}


def test_instructions_state_the_hard_rules():
    text = prompt.INSTRUCTIONS
    for phrase in ("Name only the products listed", "Copy every dose", "facts.timing.action", "BOTH English", "Never write a phone number"):
        assert phrase in text


def test_notes_with_other_products_do_not_break_a_good_draft():
    out = advice_output(pids=("P001",))
    note = Note(note_id="N1", topic="product_use", text_en="Do not tank-mix dodine; keep 15 days away from oil.", text_hi="डोडीन न मिलाएँ।")
    assert compose(MockLLM(), out, [note]).validated


def test_rule_text_in_hindi_missing_still_produces_a_card():
    out = advice_output(non_chemical=[loc("Remove infected leaves.", "")])
    assert compose(MockLLM(), out).draft.steps
