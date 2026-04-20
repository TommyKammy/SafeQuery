import logging
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger


def _error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {
        "error": {
            "code": code,
            "message": message,
        }
    }


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
    return mapping.get(status_code, HTTPStatus(status_code).phrase)


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    logger = get_logger()
    status_code = exc.status_code
    code = _http_error_code(status_code)
    message = _http_error_message(status_code)

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

    return JSONResponse(
        status_code=status_code,
        content=_error_body(code, message),
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
