"""OpenAI Responses API client over httpx (no SDK). Mirrors the working call in data/model_test/run_llm_vision.py.

- strict json_schema output, store=false, temperature and max_output_tokens from settings
- a parameter the model rejects (temperature on some models) is dropped and remembered, then the call is repeated
- 429 and 5xx (and network errors) are retried with backoff; everything else raises LLMError
- prompts, images and the API key are never logged or put into error messages
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.interfaces import LLMError

logger = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/responses"
_RETRY_STATUS = {429, 500, 502, 503, 504}
_UNSUPPORTED = {"unsupported_parameter", "unknown_parameter", "unsupported_value"}
_PROTECTED = {"model", "input", "text"}
_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-*]{4,}")


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"


def _redact(text: str) -> str:
    return _KEY_PATTERN.sub("sk-***", text)


class OpenAILLM:
    name = "openai"

    def __init__(self, api_key: str, model: str, *, temperature: float | None = 0.0, max_output_tokens: int = 1200,
                 image_detail: str = "high", url: str = API_URL, client: httpx.Client | None = None, max_retries: int = 4,
                 timeout: float = 60.0, sleep: Callable[[float], None] = time.sleep) -> None:
        if not api_key:
            raise LLMError("OpenAI API key is not set")
        self._api_key = api_key
        self.model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._image_detail = image_detail
        self._url = url
        self._client = client or httpx.Client(timeout=timeout)
        self._max_retries = max_retries
        self._sleep = sleep
        self._unsupported: set[str] = set()
        self.last_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
        self.total_usage: dict[str, int] = {"requests": 0, "input_tokens": 0, "output_tokens": 0}

    def __repr__(self) -> str:
        return f"OpenAILLM(model={self.model!r})"

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------------------------------ request
    def build_payload(self, prompt: str, schema: dict[str, Any], schema_name: str, images: list[bytes] | None) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for image in images or []:
            encoded = base64.b64encode(image).decode()
            content.append({"type": "input_image", "image_url": f"data:{_image_mime(image)};base64,{encoded}", "detail": self._image_detail})
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [{"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
            "max_output_tokens": self._max_output_tokens,
            "store": False,
        }
        if self._temperature is not None:
            payload["temperature"] = self._temperature
        for param in self._unsupported:
            payload.pop(param, None)
        return payload

    def generate_json(self, prompt: str, schema: dict[str, Any], schema_name: str = "response",
                      images: list[bytes] | None = None) -> dict[str, Any]:
        payload = self.build_payload(prompt, schema, schema_name, images)
        response = self._post_with_retries(payload)
        return self._parse(response)

    # ------------------------------------------------------------------------------------------ transport
    def _post_with_retries(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                response = self._client.post(self._url, json=payload, headers={"Authorization": f"Bearer {self._api_key}"})
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise LLMError(f"OpenAI network error: {type(exc).__name__}") from None
                self._sleep(self._delay(attempt, None))
                attempt += 1
                continue
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    raise LLMError("OpenAI returned a body that is not JSON") from None
                if not isinstance(body, dict):
                    raise LLMError("OpenAI returned an unexpected body")
                return body
            code, param, message = self._error_fields(response)
            if response.status_code == 400 and code in _UNSUPPORTED and param in payload and param not in _PROTECTED:
                logger.info("openai: model %s does not accept %r; dropping it", self.model, param)
                self._unsupported.add(param)
                payload.pop(param)
                continue
            if response.status_code in _RETRY_STATUS and attempt < self._max_retries:
                self._sleep(self._delay(attempt, response.headers.get("retry-after")))
                attempt += 1
                continue
            raise LLMError(f"OpenAI error {response.status_code} {code or ''}: {message}".strip())

    @staticmethod
    def _delay(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(60.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
        return float(min(30, 2 ** attempt))

    @staticmethod
    def _error_fields(response: httpx.Response) -> tuple[str | None, str | None, str]:
        try:
            err = response.json().get("error", {})
        except (ValueError, AttributeError):
            err = {}
        if not isinstance(err, dict):
            err = {}
        return err.get("code"), err.get("param"), _redact(str(err.get("message", ""))[:200])

    # ------------------------------------------------------------------------------------------ response
    def _parse(self, body: dict[str, Any]) -> dict[str, Any]:
        status = body.get("status")
        if status not in (None, "completed"):
            reason = (body.get("incomplete_details") or {}).get("reason", "")
            raise LLMError(f"OpenAI response not completed: {status} {reason}".strip())
        text = ""
        refused = False
        for item in body.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content", []) or []:
                if part.get("type") == "output_text":
                    text += part.get("text", "")
                elif part.get("type") == "refusal":
                    refused = True
        self._record_usage(body.get("usage"))
        if not text:
            raise LLMError("OpenAI refused to answer" if refused else "OpenAI response has no text")
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            raise LLMError("OpenAI text is not valid JSON") from None
        if not isinstance(result, dict):
            raise LLMError("OpenAI JSON is not an object")
        return result

    def _record_usage(self, usage: Any) -> None:
        usage = usage if isinstance(usage, dict) else {}
        tokens_in = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
        tokens_out = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        self.last_usage = {"input_tokens": tokens_in, "output_tokens": tokens_out}
        self.total_usage["requests"] += 1
        self.total_usage["input_tokens"] += tokens_in
        self.total_usage["output_tokens"] += tokens_out
        logger.info("openai usage: model=%s input_tokens=%d output_tokens=%d", self.model, tokens_in, tokens_out)
