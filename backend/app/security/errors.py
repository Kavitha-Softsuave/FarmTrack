"""One error shape for the whole API: ErrorOut {code, message, details}. No stack traces ever reach the client."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas import ErrorOut

logger = logging.getLogger(__name__)

_DEFAULT_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
    409: "conflict", 413: "payload_too_large", 415: "unsupported_media_type", 422: "validation_error",
    429: "rate_limited", 500: "internal_error", 503: "service_unavailable",
}


class ApiError(StarletteHTTPException):
    """Raise anywhere in a handler or service; the handler below renders it as ErrorOut."""

    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.details = details


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorOut(code=code, message=message, details=details).model_dump(mode="json")


def _http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    if isinstance(exc, ApiError):
        code, message, details = exc.code, exc.message, exc.details
    else:
        code = _DEFAULT_CODES.get(exc.status_code, f"http_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ")
        details = None
    return JSONResponse(error_body(code, message, details), status_code=exc.status_code, headers=exc.headers)


def _validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    """422 with ErrorOut fields plus FastAPI's usual `detail` list, so both documented shapes parse.

    The offending input value is dropped from every entry: it may be a phone number or a question.
    """
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    problems = [{"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
                for e in exc.errors()]
    body = error_body("validation_error", "The request is not valid.", {"errors": problems})
    body["detail"] = jsonable_encoder(problems)
    return JSONResponse(body, status_code=422)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
