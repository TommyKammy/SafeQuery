from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    handle_http_exception,
    handle_unexpected_exception,
    handle_validation_exception,
    log_startup_configuration_error,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.health import check_database_health

configure_logging()


def create_app() -> FastAPI:
    logger = get_logger()
    try:
        settings = get_settings()
    except ValidationError as exc:
        log_startup_configuration_error(exc)
        raise

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info(
            "app.startup",
            extra={
                "event_data": {
                    "event": "app.startup",
                    "service": "safequery-api",
                    "environment": settings.environment,
                    "cors_origin_count": len(settings.cors_origins_list),
                    "database_configured": True,
                }
            },
        )
        yield
        logger.info(
            "app.shutdown",
            extra={
                "event_data": {
                    "event": "app.shutdown",
                    "service": "safequery-api",
                    "environment": settings.environment,
                }
            },
        )

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="Minimum SafeQuery control-plane baseline.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = perf_counter()

        logger.info(
            "request.started",
            extra={
                "event_data": {
                    "event": "request.started",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                }
            },
        )

        response = await call_next(request)
        duration_ms = round((perf_counter() - started_at) * 1000, 3)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request.completed",
            extra={
                "event_data": {
                    "event": "request.completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )

        return response

    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_exception)
    app.add_exception_handler(Exception, handle_unexpected_exception)

    @app.get("/")
    def read_root() -> dict[str, object]:
        return {
            "service": "safequery-api",
            "status": "baseline",
            "health": "/health",
            "seams": {
                "auth": "reserved",
                "guard": "reserved",
                "execution": "reserved",
                "audit": "reserved",
            },
        }

    @app.get("/health")
    def read_health() -> JSONResponse:
        database = check_database_health(str(settings.database_url))
        healthy = database["status"] == "ok"

        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ok" if healthy else "degraded",
                "service": "safequery-api",
                "database": database,
            },
        )

    return app


app = create_app()
