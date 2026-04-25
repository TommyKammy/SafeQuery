from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    api_error,
    handle_http_exception,
    handle_unexpected_exception,
    handle_validation_exception,
    log_startup_configuration_error,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import require_preview_submission_session
from app.features.auth.dev import attach_dev_authenticated_subject
from app.features.auth.context import (
    AuthenticatedSubject,
    require_authenticated_subject,
)
from app.features.auth.session import (
    ApplicationSessionContext,
    require_application_session,
)
from app.services.health import check_database_health
from app.services.first_run_doctor import FirstRunDoctorResult, run_first_run_doctor
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionEntitlementError,
    PreviewSubmissionRequest,
    PreviewSubmissionResponse,
    submit_preview_request,
)
from app.services.operator_workflow import (
    OperatorWorkflowSnapshot,
    get_operator_workflow_snapshot,
)

configure_logging()


def create_app() -> FastAPI:
    logger = get_logger()
    try:
        settings = get_settings()
        source_posture = settings.source_posture_telemetry()
    except (RuntimeError, ValidationError) as exc:
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
                    **source_posture.model_dump(),
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
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    if settings.dev_auth_enabled:
        app.middleware("http")(attach_dev_authenticated_subject)

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

        response = None
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            status_code = response.status_code if response is not None else 500

            logger.info(
                "request.completed",
                extra={
                    "event_data": {
                        "event": "request.completed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    }
                },
            )

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
        database = check_database_health(str(settings.app_postgres_url))
        healthy = database["status"] == "ok"

        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ok" if healthy else "degraded",
                "service": "safequery-api",
                "database": database,
            },
        )

    @app.get("/doctor/first-run", response_model=FirstRunDoctorResult)
    def read_first_run_doctor(
        session: Session = Depends(require_preview_submission_session),
    ) -> FirstRunDoctorResult:
        return run_first_run_doctor(session, backend_probe_mode="served_route")

    @app.post("/requests/preview", response_model=PreviewSubmissionResponse)
    def create_request_preview(
        request: Request,
        payload: PreviewSubmissionRequest,
        authenticated_subject: AuthenticatedSubject = Depends(
            require_authenticated_subject
        ),
        application_session: ApplicationSessionContext = Depends(
            require_application_session
        ),
        session: Session = Depends(require_preview_submission_session),
    ) -> PreviewSubmissionResponse:
        try:
            request_id = getattr(request.state, "request_id", None)
            if not isinstance(request_id, str) or not request_id.strip():
                raise HTTPException(
                    status_code=500,
                    detail="Request audit context is unavailable.",
                )

            user_subject = authenticated_subject.normalized_subject_id()
            audit_context = PreviewAuditContext(
                occurred_at=datetime.now(timezone.utc),
                request_id=request_id,
                correlation_id=str(uuid4()),
                user_subject=user_subject,
                session_id=application_session.audit_session_id,
                query_candidate_id=str(uuid4()),
                candidate_owner_subject=user_subject,
                application_version=f"safequery-api/{app.version}",
            )
            return submit_preview_request(
                payload,
                authenticated_subject,
                session,
                audit_context=audit_context,
            )
        except PreviewSubmissionEntitlementError as exc:
            raise api_error(
                403,
                "entitlement_denied",
                "The signed-in operator is not entitled to use that source.",
            ) from exc
        except PreviewSubmissionContractError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/operator/workflow", response_model=OperatorWorkflowSnapshot)
    def read_operator_workflow(
        session: Session = Depends(require_preview_submission_session),
    ) -> OperatorWorkflowSnapshot:
        return get_operator_workflow_snapshot(session)

    return app


app = create_app()
