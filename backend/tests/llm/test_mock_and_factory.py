import logging

import pytest

from app.advice import prompt
from app.interfaces import LLMError, LLMProvider
from app.llm import factory
from app.llm.facts import FACTS_END, FACTS_START, extract_facts, wrap_facts
from app.llm.mock import MockLLM, advice_from_facts, fill_schema
from app.llm.openai_client import OpenAILLM
from tests.advice.helpers import advice_output, plain_output, ref
from tests.llm.helpers import make_settings


# ---------------------------------------------------------------------------------------------- MockLLM
def test_mock_satisfies_the_interface():
    assert isinstance(MockLLM(), LLMProvider) and MockLLM().name == "mock"


def test_facts_block_round_trip():
    facts = {"task": "x", "text": "हिंदी ✓", "n": 3}
    block = wrap_facts(facts)
    assert block.startswith(FACTS_START) and block.endswith(FACTS_END)
    assert extract_facts(f"before\n{block}\nafter") == facts
    assert extract_facts("no block here") is None
    assert extract_facts(f"{FACTS_START} [1, 2] {FACTS_END}") is None
    with pytest.raises(LLMError):
        extract_facts(f"{FACTS_START} {{broken {FACTS_END}")


def test_mock_writes_a_schema_valid_draft_from_the_facts_and_is_deterministic():
    out = advice_output(pids=("P001", "P002"))
    facts = prompt.build_facts(out, [], ref())
    text = prompt.build_prompt(facts)
    first = MockLLM().generate_json(text, prompt.ADVICE_SCHEMA, prompt.ADVICE_SCHEMA_NAME)
    assert first == MockLLM().generate_json(text, prompt.ADVICE_SCHEMA, prompt.ADVICE_SCHEMA_NAME)
    assert set(first) == set(prompt.ADVICE_SCHEMA["required"])
    assert first["product_ids_mentioned"] == ["P001", "P002"]
    assert "600 g in 200 litres of water" in first["steps"][1]["en"]
    assert all(set(step) == {"en", "hi"} for step in first["steps"])


def test_mock_text_is_built_only_from_the_facts():
    out = advice_output(pids=("P002",))
    facts = prompt.build_facts(out, [], ref())
    draft = advice_from_facts(facts)
    assert "Dodine" in draft["steps"][1]["en"] and "Captan" not in str(draft)
    facts["products"][0]["dose_text"]["en"] = "1 g per litre of water"
    assert "1 g per litre of water" in advice_from_facts(facts)["steps"][1]["en"]


def test_mock_without_products_writes_a_safe_not_sure_draft():
    facts = prompt.build_facts(plain_output("expert_review"), [], ref())
    draft = advice_from_facts(facts)
    assert draft["product_ids_mentioned"] == [] and "expert" in draft["summary"]["en"]


def test_mock_fills_any_other_schema():
    schema = {"type": "object", "additionalProperties": False, "required": ["answer", "refused", "score", "tags", "kind", "inner"],
              "properties": {"answer": {"type": "string"}, "refused": {"type": "boolean"}, "score": {"type": "number"},
                             "tags": {"type": "array", "items": {"type": "string"}}, "kind": {"enum": ["a", "b"]},
                             "inner": {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}}}, "extra": {"type": "string"}}}
    assert MockLLM().generate_json("anything", schema) == {"answer": "", "refused": False, "score": 0, "tags": [], "kind": "a", "inner": {"n": 0}}


def test_fill_schema_handles_unions_and_unknowns():
    assert fill_schema({"anyOf": [{"type": "string"}, {"type": "null"}]}) == ""
    assert fill_schema({"type": ["null", "integer"]}) == 0
    assert fill_schema({"type": "null"}) is None
    assert fill_schema({"type": "number", "minimum": 5}) == 5


def test_mock_rejects_a_non_object_root_schema():
    with pytest.raises(LLMError):
        MockLLM().generate_json("x", {"type": "array", "items": {"type": "string"}})


# ---------------------------------------------------------------------------------------------- build_llm
@pytest.fixture(autouse=True)
def _reset_log_once():
    factory._logged.clear()
    yield
    factory._logged.clear()


def test_default_is_the_mock():
    assert isinstance(factory.build_llm(make_settings()), MockLLM)
    assert isinstance(factory.build_llm(make_settings(llm_provider="mock", openai_api_key="sk-real-key-123456")), MockLLM)


def test_openai_without_a_key_falls_back_to_the_mock_and_logs_once(caplog):
    caplog.set_level(logging.WARNING)
    for key in (None, "", "your-key-here"):
        assert isinstance(factory.build_llm(make_settings(llm_provider="openai", openai_api_key=key)), MockLLM)
    assert [r.getMessage() for r in caplog.records].count("LLM_PROVIDER=openai but OPENAI_API_KEY is not set: using the offline MockLLM") == 1


def test_openai_with_a_key_builds_the_client_from_settings():
    llm = factory.build_llm(make_settings(llm_provider="openai", openai_api_key="sk-real-key-123456", openai_model="gpt-6-luna",
                                          openai_temperature="0.3", openai_max_output_tokens=900, openai_image_detail="low"))
    assert isinstance(llm, OpenAILLM) and llm.model == "gpt-6-luna" and llm.name == "openai"
    payload = llm.build_payload("p", {"type": "object"}, "s", [b"\xff\xd8\xff1"])
    assert payload["temperature"] == 0.3 and payload["max_output_tokens"] == 900
    assert payload["input"][0]["content"][1]["detail"] == "low"


@pytest.mark.parametrize("raw,expected", [("0", 0.0), ("0.7", 0.7), ("", None), ("none", None), ("NONE", None), ("abc", None)])
def test_temperature_setting_is_parsed(raw, expected):
    llm = factory.build_llm(make_settings(llm_provider="openai", openai_api_key="sk-real-key-123456", openai_temperature=raw))
    payload = llm.build_payload("p", {"type": "object"}, "s", None)
    assert payload.get("temperature") == expected


def test_unknown_provider_uses_the_mock(caplog):
    caplog.set_level(logging.WARNING)
    assert isinstance(factory.build_llm(make_settings(llm_provider="claude")), MockLLM)
    assert any("Unknown LLM_PROVIDER" in r.getMessage() for r in caplog.records)
