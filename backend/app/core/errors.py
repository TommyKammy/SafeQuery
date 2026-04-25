from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger


_SAFE_API_ERROR_CODES = frozenset(
    {
        "unauthenticated",
        "session_invalid",
        "csrf_failed",
        "entitlement_denied",
    }
)

_SAFE_ENTITLEMENT_DENIAL_AUDIT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "occurred_at",
        "request_id",
        "correlation_id",
        "user_subject",
        "session_id",
        "auth_source",
        "governance_bindings",
        "entitlement_decision",
        "entitlement_source_bindings",
        "application_version",
        "source_id",
        "source_family",
        "source_flavor",
        "dataset_contract_version",
        "schema_snapshot_version",
        "primary_deny_code",
        "denial_cause",
    }
)


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    audit_events: list[dict[str, Any]] | None = None,
) -> HTTPException:
    if code not in _SAFE_API_ERROR_CODES:
        raise ValueError("Unsupported API error code.")

    detail: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if audit_events is not None:
        detail["audit"] = {"events": audit_events}

    return HTTPException(
        status_code=status_code,
        detail=detail,
    )


def _error_body(code: str, message: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    return body


def _request_log_context(request: Request) -> dict[str, str]:
    return {
        "event": "request.error",
        "method": request.method,
        "path": request.url.path,
        "request_id": getattr(request.state, "request_id", "unknown"),
    }


def _http_error_code(status_code: int) -> str:
    mapping = {
        404: "not_found",
        405: "method_not_allowed",
        422: "invalid_request",
    }
    return mapping.get(status_code, "http_error")


def _http_error_message(status_code: int) -> str:
    mapping = {
        404: "Resource not found.",
        405: "Method not allowed.",
        422: "Request validation failed.",
    }
    if status_code in mapping:
        return mapping[status_code]

    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP error."


def _safe_http_exception_error(
    exc: StarletteHTTPException,
) -> tuple[str, str]:
    detail: Any = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
        if (
            isinstance(code, str)
            and code.strip()
            and code in _SAFE_API_ERROR_CODES
            and isinstance(message, str)
            and message.strip()
        ):
            return code, message

    return _http_error_code(exc.status_code), _http_error_message(exc.status_code)


def _safe_http_exception_audit(
    exc: StarletteHTTPException,
    *,
    code: str,
) -> dict[str, list[dict[str, Any]]] | None:
    if exc.status_code != 403 or code != "entitlement_denied":
        return None

    detail: Any = exc.detail
    if not isinstance(detail, dict):
        return None

    audit = detail.get("audit")
    if not isinstance(audit, dict):
        return None

    events = audit.get("events")
    if not isinstance(events, list):
        return None
    if not all(isinstance(event, dict) for event in events):
        return None

    return {
        "events": [
            {
                key: value
                for key, value in event.items()
                if isinstance(key, str)
                and key in _SAFE_ENTITLEMENT_DENIAL_AUDIT_FIELDS
            }
            for event in events
        ]
    }


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger = get_logger()
    status_code = exc.status_code
    code, message = _safe_http_exception_error(exc)

    logger.warning(
        "request.http_error",
        extra={
            "event_data": {
                **_request_log_context(request),
                "event": "request.http_error",
                "status_code": status_code,
                "error_code": code,
            }
        },
    )

    content = _error_body(code, message)
    audit = _safe_http_exception_audit(exc, code=code)
    if audit is not None:
        content["audit"] = audit

    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={"X-Request-ID": getattr(request.state, "request_id", "unknown")},
    )


async def handle_validation_exception(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger = get_logger()
    logger.warning(
        "request.validation_error",
        extra={
            "event_data": {
                **_request_log_context(request),
                "event": "request.validation_error",
                "status_code": 422,
                "error_code": "invalid_request",
                "error_count": len(exc.errors()),
            }
        },
    )

    return JSONResponse(
        status_code=422,
        content=_error_body("invalid_request", "Request validation failed."),
        headers={"X-Request-ID": getattr(request.state, "request_id", "unknown")},
    )


async def handle_unexpected_exception(
    request: Request, exc: Exception
) -> JSONResponse:
    logger = get_logger()
    logger.error(
        "request.unhandled_exception",
        extra={
            "event_data": {
                **_request_log_context(request),
                "event": "request.unhandled_exception",
                "status_code": 500,
                "error_code": "internal_server_error",
                "exception_class": exc.__class__.__name__,
            }
        },
    )

    return JSONResponse(
        status_code=500,
        content=_error_body(
            "internal_server_error",
            "Internal server error.",
        ),
        headers={"X-Request-ID": getattr(request.state, "request_id", "unknown")},
    )


def log_startup_configuration_error(exc: Exception) -> None:
    logger = get_logger()
    details: dict[str, object] = {
        "event": "app.startup.configuration_error",
        "exception_class": exc.__class__.__name__,
    }

    if isinstance(exc, ValidationError):
        details["error_count"] = len(exc.errors())

    logger.error("app.startup.configuration_error", extra={"event_data": details})
