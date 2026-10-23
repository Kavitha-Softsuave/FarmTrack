"""OpenAILLM against httpx.MockTransport: request construction, parameter-drop retry, backoff, errors, nothing secret in logs."""
import base64
import json
import logging

import httpx
import pytest

from app.interfaces import LLMError
from app.llm.openai_client import API_URL, OpenAILLM

KEY = "sk-test-0123456789abcdef"
PROMPT = "SECRET-PROMPT-TEXT about a farmer"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer"], "properties": {"answer": {"type": "string"}}}


def ok_body(text='{"answer": "yes"}', **extra):
    body = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 120, "output_tokens": 30}}
    body.update(extra)
    return body


class Server:
    """Scripted MockTransport: answers with the queued responses in order and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    def bodies(self):
        return [json.loads(r.content) for r in self.requests]


def llm_with(server: Server, sleeps=None, **kw) -> OpenAILLM:
    client = httpx.Client(transport=httpx.MockTransport(server))
    return OpenAILLM(KEY, kw.pop("model", "gpt-4o-mini"), client=client, sleep=(sleeps.append if sleeps is not None else (lambda _s: None)), **kw)


def json_response(status, body, headers=None):
    return httpx.Response(status, json=body, headers=headers)


def error_response(status, code=None, param=None, message="bad"):
    return json_response(status, {"error": {"message": message, "type": "invalid_request_error", "param": param, "code": code}})


# ---------------------------------------------------------------------------------------------- request construction
def test_request_construction():
    server = Server(json_response(200, ok_body()))
    llm = llm_with(server, temperature=0.2, max_output_tokens=777)
    assert llm.generate_json(PROMPT, SCHEMA, "my_schema") == {"answer": "yes"}
    request = server.requests[0]
    assert request.method == "POST" and str(request.url) == API_URL == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = server.bodies()[0]
    assert body["model"] == "gpt-4o-mini" and body["store"] is False
    assert body["temperature"] == 0.2 and body["max_output_tokens"] == 777
    assert body["input"] == [{"role": "user", "content": [{"type": "input_text", "text": PROMPT}]}]
    assert body["text"] == {"format": {"type": "json_schema", "name": "my_schema", "strict": True, "schema": SCHEMA}}


def test_model_name_comes_from_the_constructor():
    server = Server(json_response(200, ok_body()))
    llm_with(server, model="gpt-6-luna").generate_json(PROMPT, SCHEMA)
    assert server.bodies()[0]["model"] == "gpt-6-luna"


def test_no_temperature_when_switched_off():
    server = Server(json_response(200, ok_body()))
    llm_with(server, temperature=None).generate_json(PROMPT, SCHEMA)
    assert "temperature" not in server.bodies()[0]


def test_images_are_sent_as_input_image_with_the_right_mime():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 10
    jpg = b"\xff\xd8\xff" + b"1" * 10
    webp = b"RIFF1234WEBPVP8 "
    server = Server(json_response(200, ok_body()))
    llm_with(server, image_detail="low").generate_json(PROMPT, SCHEMA, images=[png, jpg, webp])
    content = server.bodies()[0]["input"][0]["content"]
    assert [c["type"] for c in content] == ["input_text", "input_image", "input_image", "input_image"]
    assert content[1]["image_url"] == "data:image/png;base64," + base64.b64encode(png).decode() and content[1]["detail"] == "low"
    assert content[2]["image_url"].startswith("data:image/jpeg;base64,")
    assert content[3]["image_url"].startswith("data:image/webp;base64,")


def test_empty_key_is_refused():
    with pytest.raises(LLMError):
        OpenAILLM("", "gpt-4o-mini")


def test_usage_is_recorded():
    server = Server(json_response(200, ok_body()))
    llm = llm_with(server)
    llm.generate_json(PROMPT, SCHEMA)
    llm.generate_json(PROMPT, SCHEMA)
    assert llm.last_usage == {"input_tokens": 120, "output_tokens": 30}
    assert llm.total_usage == {"requests": 2, "input_tokens": 240, "output_tokens": 60}


def test_usage_in_chat_style_names_is_understood():
    server = Server(json_response(200, ok_body(usage={"prompt_tokens": 5, "completion_tokens": 7})))
    llm = llm_with(server)
    llm.generate_json(PROMPT, SCHEMA)
    assert llm.last_usage == {"input_tokens": 5, "output_tokens": 7}


# ---------------------------------------------------------------------------------------------- parameter-drop retry
def test_rejected_parameter_is_dropped_retried_and_remembered():
    reject = error_response(400, "unsupported_parameter", "temperature", "Unsupported parameter: 'temperature'")
    server = Server(reject, json_response(200, ok_body()))
    llm = llm_with(server, temperature=0.0)
    assert llm.generate_json(PROMPT, SCHEMA) == {"answer": "yes"}
    first, second = server.bodies()
    assert "temperature" in first and "temperature" not in second
    server.responses = [json_response(200, ok_body())]
    llm.generate_json(PROMPT, SCHEMA)
    assert "temperature" not in server.bodies()[2] and len(server.requests) == 3        # next call does not even try it


def test_several_parameters_can_be_dropped_one_after_the_other():
    server = Server(error_response(400, "unsupported_parameter", "temperature"), error_response(400, "unknown_parameter", "max_output_tokens"),
                    json_response(200, ok_body()))
    llm_with(server).generate_json(PROMPT, SCHEMA)
    last = server.bodies()[-1]
    assert "temperature" not in last and "max_output_tokens" not in last and len(server.requests) == 3


@pytest.mark.parametrize("param", ["model", "input", "text"])
def test_required_parameters_are_never_dropped(param):
    server = Server(error_response(400, "unsupported_parameter", param))
    with pytest.raises(LLMError):
        llm_with(server).generate_json(PROMPT, SCHEMA)
    assert len(server.requests) == 1


# ---------------------------------------------------------------------------------------------- retries and failures
def test_rate_limit_is_retried_with_backoff():
    server = Server(error_response(429), error_response(503), json_response(200, ok_body()))
    sleeps: list[float] = []
    assert llm_with(server, sleeps).generate_json(PROMPT, SCHEMA) == {"answer": "yes"}
    assert sleeps == [1.0, 2.0] and len(server.requests) == 3


def test_retry_after_header_is_respected():
    server = Server(json_response(429, {"error": {"message": "slow down"}}, headers={"retry-after": "7"}), json_response(200, ok_body()))
    sleeps: list[float] = []
    llm_with(server, sleeps).generate_json(PROMPT, SCHEMA)
    assert sleeps == [7.0]


def test_gives_up_after_the_retries():
    server = Server(error_response(500, message="server error"))
    sleeps: list[float] = []
    with pytest.raises(LLMError, match="500"):
        llm_with(server, sleeps, max_retries=3).generate_json(PROMPT, SCHEMA)
    assert len(server.requests) == 4 and sleeps == [1.0, 2.0, 4.0]


def test_network_errors_are_retried_then_raised():
    server = Server(httpx.ConnectError("no route"))
    sleeps: list[float] = []
    with pytest.raises(LLMError, match="network error: ConnectError"):
        llm_with(server, sleeps, max_retries=2).generate_json(PROMPT, SCHEMA)
    assert len(server.requests) == 3
    server = Server(httpx.ReadTimeout("slow"), json_response(200, ok_body()))
    assert llm_with(server).generate_json(PROMPT, SCHEMA) == {"answer": "yes"}


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_not_retried(status):
    server = Server(error_response(status, "invalid_api_key", message="nope"))
    with pytest.raises(LLMError, match=str(status)):
        llm_with(server).generate_json(PROMPT, SCHEMA)
    assert len(server.requests) == 1


def test_error_message_hides_keys_and_never_includes_the_prompt():
    server = Server(error_response(401, "invalid_api_key", message=f"Incorrect API key provided: {KEY}. You sent {PROMPT}"))
    with pytest.raises(LLMError) as err:
        llm_with(server).generate_json(PROMPT, SCHEMA)
    assert KEY not in str(err.value) and "sk-***" in str(err.value)


@pytest.mark.parametrize("body,fragment", [
    ({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []}, "not completed"),
    ({"status": "completed", "output": []}, "no text"),
    ({"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "I cannot"}]}]}, "refused"),
    (ok_body("not json"), "not valid JSON"),
    (ok_body("[1, 2]"), "not an object"),
])
def test_bad_responses_raise(body, fragment):
    with pytest.raises(LLMError, match=fragment):
        llm_with(Server(json_response(200, body))).generate_json(PROMPT, SCHEMA)


def test_response_that_is_not_json_raises():
    with pytest.raises(LLMError):
        llm_with(Server(httpx.Response(200, text="<html>"))).generate_json(PROMPT, SCHEMA)


def test_text_split_over_several_parts_is_joined():
    body = {"status": "completed", "output": [{"type": "reasoning", "summary": []},
                                              {"type": "message", "content": [{"type": "output_text", "text": '{"answer":'}, {"type": "output_text", "text": ' "joined"}'}]}]}
    assert llm_with(Server(json_response(200, body))).generate_json(PROMPT, SCHEMA) == {"answer": "joined"}


# ---------------------------------------------------------------------------------------------- secrets
def test_prompt_and_key_never_reach_the_logs(caplog):
    caplog.set_level(logging.DEBUG)
    server = Server(error_response(400, "unsupported_parameter", "temperature"), error_response(429), json_response(200, ok_body()))
    llm = llm_with(server)
    llm.generate_json(PROMPT, SCHEMA)
    with pytest.raises(LLMError):
        llm_with(Server(error_response(401, message=f"bad key {KEY}"))).generate_json(PROMPT, SCHEMA)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert KEY not in logged and "SECRET-PROMPT" not in logged
    assert KEY not in repr(llm) and "gpt-4o-mini" in repr(llm)
