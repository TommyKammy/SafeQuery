from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
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
from app.db.models.preview import PreviewCandidate
from app.db.models.source_registry import RegisteredSource
from app.db.session import require_preview_submission_session
from app.features.audit import SourceAwareAuditEvent
from app.features.auth.dev import attach_dev_authenticated_subject
from app.features.auth.context import (
    AuthenticatedSubject,
    require_authenticated_subject,
)
from app.features.auth.session import (
    ApplicationSessionContext,
    require_application_session,
)
from app.features.guard.deny_taxonomy import DENY_SOURCE_BINDING_MISMATCH
from app.features.execution import (
    ExecutableCandidateRecord,
    ExecutionAuditContext,
    ExecutionConnectorExecutionError,
    ExecutionConnectorSelection,
    ExecutionConnectorSelectionError,
    ExecutionRuntimeCancelledError,
    ExecutionRuntimeFailureError,
    ExecutionRuntimeSafetyState,
    execute_candidate_sql,
    preflight_execution_runtime_controls,
    select_execution_connector,
)
from app.services.candidate_lifecycle import (
    CandidateLifecycleAuditContext,
    CandidateLifecycleRevalidationError,
    CandidateLifecycleRevalidationResult,
    SourceBoundCandidateMetadata,
    revalidate_authoritative_candidate_approval,
)
from app.services.first_run_doctor import FirstRunDoctorResult, run_first_run_doctor
from app.services.health import (
    build_operator_health,
    check_database_health,
    check_sql_generation_runtime_health,
)
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionEntitlementError,
    PreviewSubmissionRequest,
    PreviewSubmissionResponse,
    persist_execution_audit_events,
    submit_preview_request,
)
from app.services.sql_generation_adapter import resolve_sql_generation_adapter
from app.services.operator_workflow import (
    OperatorWorkflowSnapshot,
    get_operator_workflow_snapshot,
)
from app.services.support_bundle import SupportBundle, build_support_bundle

configure_logging()


_ENTITLEMENT_DENIAL_AUDIT_FIELDS = frozenset(
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

_EXECUTION_DENIAL_AUDIT_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "occurred_at",
        "request_id",
        "correlation_id",
        "causation_event_id",
        "user_subject",
        "session_id",
        "query_candidate_id",
        "candidate_owner_subject",
        "source_id",
        "source_family",
        "source_flavor",
        "dataset_contract_version",
        "schema_snapshot_version",
        "execution_policy_version",
        "connector_profile_version",
        "primary_deny_code",
        "denial_cause",
        "candidate_state",
        "execution_row_count",
        "result_truncated",
    }
)


class CandidateExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_source_id: Optional[str] = None


class CandidateExecuteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_id: str
    connector_id: str
    ownership: str
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]
    audit: dict[str, list[dict[str, Any]]]


def _operator_runtime_safety_state(request: Request) -> ExecutionRuntimeSafetyState | None:
    state = getattr(request.app.state, "execution_runtime_safety_state", None)
    if state is None:
        return None
    if not isinstance(state, ExecutionRuntimeSafetyState):
        raise api_error(
            503,
            "execution_unavailable",
            "Candidate execution is unavailable.",
        )
    return state


def _operator_control_values(values: object) -> frozenset[str]:
    if isinstance(values, (set, frozenset, list, tuple)):
        normalized_values: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                break
            normalized = value.strip()
            if not normalized:
                break
            normalized_values.add(normalized)
        else:
            return frozenset(normalized_values)
    raise api_error(
        503,
        "execution_unavailable",
        "Candidate execution is unavailable.",
    )


def _operator_cancellation_probe(
    request: Request,
    *,
    candidate_id: str,
    source_id: str,
) -> Callable[[], bool]:
    def probe() -> bool:
        cancelled_candidate_ids = _operator_control_values(
            getattr(
                request.app.state,
                "execution_cancelled_candidate_ids",
                frozenset(),
            )
        )
        cancelled_source_ids = _operator_control_values(
            getattr(
                request.app.state,
                "execution_cancelled_source_ids",
                frozenset(),
            )
        )
        return candidate_id in cancelled_candidate_ids or source_id in cancelled_source_ids

    return probe


def _serialize_entitlement_denial_audit_events(
    exc: PreviewSubmissionEntitlementError,
) -> list[dict[str, object]]:
    return [
        event.model_dump(
            mode="json",
            include=_ENTITLEMENT_DENIAL_AUDIT_FIELDS,
            exclude_none=True,
        )
        for event in exc.audit_events
    ]


def _serialize_execution_audit_events(
    events: list[object],
) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for event in events:
        if not hasattr(event, "model_dump"):
            continue
        serialized.append(
            event.model_dump(
                mode="json",
                include=_EXECUTION_DENIAL_AUDIT_FIELDS,
                exclude_none=True,
            )
        )
    return serialized


def _require_execution_connector_configuration(
    *,
    connector_id: str,
    business_postgres_source_url: object | None,
    business_mssql_source_connection_string: str | None,
) -> None:
    if connector_id == "postgresql_readonly":
        if business_postgres_source_url is None:
            raise api_error(
                503,
                "execution_unavailable",
                "Candidate execution is unavailable.",
            )
        return

    if connector_id == "mssql_readonly":
        connection_string = business_mssql_source_connection_string
        if connection_string is None or not connection_string.strip():
            raise api_error(
                503,
                "execution_unavailable",
                "Candidate execution is unavailable.",
            )
        return


def _build_execution_source_binding_denial_audit_event(
    *,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: CandidateLifecycleAuditContext,
) -> SourceAwareAuditEvent:
    return SourceAwareAuditEvent(
        event_id=audit_context.event_id,
        event_type="execution_denied",
        occurred_at=audit_context.occurred_at,
        request_id=audit_context.request_id,
        correlation_id=audit_context.correlation_id,
        user_subject=audit_context.user_subject,
        session_id=audit_context.session_id,
        query_candidate_id=audit_context.query_candidate_id,
        candidate_owner_subject=audit_context.candidate_owner_subject,
        source_id=candidate_source.source_id,
        source_family=candidate_source.source_family,
        source_flavor=candidate_source.source_flavor,
        dataset_contract_version=candidate_source.dataset_contract_version,
        schema_snapshot_version=candidate_source.schema_snapshot_version,
        execution_policy_version=candidate_source.execution_policy_version,
        connector_profile_version=candidate_source.connector_profile_version,
        primary_deny_code=DENY_SOURCE_BINDING_MISMATCH,
        denial_cause="source_binding_mismatch",
        candidate_state="denied",
    )


def _require_source_bound_execution_connection_reference(
    *,
    session: Session,
    candidate_source: SourceBoundCandidateMetadata,
    connector_id: str,
    audit_context: CandidateLifecycleAuditContext,
) -> None:
    def raise_source_binding_mismatch(message: str) -> None:
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_SOURCE_BINDING_MISMATCH,
            message=message,
            audit_event=_build_execution_source_binding_denial_audit_event(
                candidate_source=candidate_source,
                audit_context=audit_context,
            ),
        )

    expected_connection_reference_by_connector = {
        "postgresql_readonly": "env:SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        "mssql_readonly": "env:SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING",
    }
    expected_connection_reference = expected_connection_reference_by_connector.get(
        connector_id
    )
    if expected_connection_reference is None:
        raise_source_binding_mismatch(
            "The candidate-bound source is not bound to a supported "
            f"backend-owned execution connection reference for connector '{connector_id}'."
        )

    source = session.scalar(
        select(RegisteredSource).where(
            RegisteredSource.source_id == candidate_source.source_id
        )
    )
    raw_connection_reference = (
        source.connection_reference if source is not None else None
    )
    actual_connection_reference = (
        raw_connection_reference.strip()
        if isinstance(raw_connection_reference, str)
        else None
    )
    if actual_connection_reference != expected_connection_reference:
        raise_source_binding_mismatch(
            "The candidate-bound source is not bound to the backend-owned "
            "execution connection reference."
        )


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
    sql_generation_adapter = (
        None
        if settings.sql_generation.provider == "disabled"
        else resolve_sql_generation_adapter(settings.sql_generation)
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
    def read_health(
        session: Session = Depends(require_preview_submission_session),
    ) -> JSONResponse:
        database = check_database_health(str(settings.app_postgres_url))
        sql_generation = check_sql_generation_runtime_health(settings.sql_generation)
        operator_health = build_operator_health(
            session,
            database=database,
            sql_generation=sql_generation,
        )
        get_logger().info(
            "operator.workflow_lifecycle_metrics",
            extra={
                "event_data": {
                    "event": "operator.workflow_lifecycle_metrics",
                    "workflow_lifecycle_metrics": operator_health[
                        "workflow_lifecycle_metrics"
                    ],
                }
            },
        )
        sql_generation_status = sql_generation["status"]
        healthy = database["status"] == "ok" and sql_generation_status in {
            "ok",
            "disabled",
            "unchecked",
        }
        backend_healthy = healthy
        aggregate_healthy = healthy and operator_health["status"] == "ok"

        return JSONResponse(
            status_code=200 if backend_healthy else 503,
            content={
                "status": "ok" if aggregate_healthy else "degraded",
                "service": "safequery-api",
                "database": database,
                "sql_generation": sql_generation,
                "operator_health": operator_health,
            },
        )

    @app.get("/doctor/first-run", response_model=FirstRunDoctorResult)
    def read_first_run_doctor(
        session: Session = Depends(require_preview_submission_session),
    ) -> FirstRunDoctorResult:
        return run_first_run_doctor(session, backend_probe_mode="served_route")

    @app.get("/support/bundle", response_model=SupportBundle)
    def read_support_bundle(
        authenticated_subject: AuthenticatedSubject = Depends(
            require_authenticated_subject
        ),
        session: Session = Depends(require_preview_submission_session),
    ) -> SupportBundle:
        authenticated_subject.normalized_subject_id()
        database = check_database_health(str(settings.app_postgres_url))
        sql_generation = check_sql_generation_runtime_health(settings.sql_generation)
        return build_support_bundle(
            session,
            settings=settings,
            database=database,
            sql_generation=sql_generation,
        )

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
                auth_source=application_session.auth_source,
                application_version=f"safequery-api/{app.version}",
            )
            return submit_preview_request(
                payload,
                authenticated_subject,
                session,
                audit_context=audit_context,
                sql_generation_adapter=sql_generation_adapter,
            )
        except PreviewSubmissionEntitlementError as exc:
            raise api_error(
                403,
                "entitlement_denied",
                "The signed-in operator is not entitled to use that source.",
                audit_events=_serialize_entitlement_denial_audit_events(exc),
            ) from exc
        except PreviewSubmissionContractError as exc:
            if exc.public_code is not None and exc.public_message is not None:
                raise api_error(
                    422,
                    exc.public_code,
                    exc.public_message,
                ) from exc
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post(
        "/candidates/{candidate_id}/execute",
        response_model=CandidateExecuteResponse,
    )
    def execute_candidate_preview(
        http_request: Request,
        candidate_id: str,
        payload: CandidateExecuteRequest,
        authenticated_subject: AuthenticatedSubject = Depends(
            require_authenticated_subject
        ),
        application_session: ApplicationSessionContext = Depends(
            require_application_session
        ),
        session: Session = Depends(require_preview_submission_session),
    ) -> CandidateExecuteResponse:
        request_id = getattr(http_request.state, "request_id", None)
        if not isinstance(request_id, str) or not request_id.strip():
            raise HTTPException(
                status_code=500,
                detail="Request audit context is unavailable.",
            )

        occurred_at = datetime.now(timezone.utc)
        user_subject = authenticated_subject.normalized_subject_id()
        preview_candidate = session.scalar(
            select(PreviewCandidate).where(PreviewCandidate.candidate_id == candidate_id)
        )
        audit_request_id = (
            preview_candidate.request_id
            if preview_candidate is not None
            else request_id
        )
        lifecycle_audit_context = CandidateLifecycleAuditContext(
            event_id=uuid4(),
            occurred_at=occurred_at,
            request_id=audit_request_id,
            correlation_id=str(uuid4()),
            user_subject=user_subject,
            session_id=application_session.audit_session_id,
            query_candidate_id=candidate_id,
            candidate_owner_subject=user_subject,
        )
        try:
            candidate: ExecutableCandidateRecord | None = None
            selection: ExecutionConnectorSelection | None = None
            cancellation_probe = None
            runtime_safety_state = _operator_runtime_safety_state(http_request)

            def prepare_execution(
                revalidation_result: CandidateLifecycleRevalidationResult,
            ) -> None:
                nonlocal candidate, selection, cancellation_probe
                approved_sql = revalidation_result.approved_sql
                if approved_sql is None:
                    raise api_error(
                        403,
                        "execution_denied",
                        "Candidate execution was denied.",
                    )
                prepared_candidate = ExecutableCandidateRecord(
                    canonical_sql=approved_sql,
                    source=revalidation_result.source,
                )
                prepared_selection = select_execution_connector(
                    candidate_source=prepared_candidate.source
                )
                _require_source_bound_execution_connection_reference(
                    session=session,
                    candidate_source=prepared_candidate.source,
                    connector_id=prepared_selection.connector_id,
                    audit_context=lifecycle_audit_context,
                )
                prepared_cancellation_probe = _operator_cancellation_probe(
                    http_request,
                    candidate_id=candidate_id,
                    source_id=prepared_candidate.source.source_id,
                )
                preflight_audit_context = ExecutionAuditContext(
                    event_id=uuid4(),
                    occurred_at=occurred_at,
                    request_id=audit_request_id,
                    correlation_id=lifecycle_audit_context.correlation_id,
                    user_subject=user_subject,
                    session_id=application_session.audit_session_id,
                    query_candidate_id=candidate_id,
                    candidate_owner_subject=user_subject,
                    execution_policy_version=(
                        prepared_candidate.source.execution_policy_version
                    ),
                    connector_profile_version=(
                        prepared_candidate.source.connector_profile_version
                    ),
                )
                preflight_execution_runtime_controls(
                    candidate_source=prepared_candidate.source,
                    selection=prepared_selection,
                    cancellation_probe=prepared_cancellation_probe,
                    runtime_safety_state=runtime_safety_state,
                    audit_context=preflight_audit_context,
                )
                _require_execution_connector_configuration(
                    connector_id=prepared_selection.connector_id,
                    business_postgres_source_url=settings.business_postgres_source_url,
                    business_mssql_source_connection_string=(
                        settings.business_mssql_source_connection_string
                    ),
                )
                candidate = prepared_candidate
                selection = prepared_selection
                cancellation_probe = prepared_cancellation_probe

            revalidate_authoritative_candidate_approval(
                session=session,
                candidate_id=candidate_id,
                authenticated_subject=authenticated_subject,
                as_of=occurred_at,
                selected_source_id=payload.selected_source_id,
                audit_context=lifecycle_audit_context,
                before_mark_executed=prepare_execution,
            )
            if candidate is None or selection is None:
                raise api_error(
                    403,
                    "execution_denied",
                    "Candidate execution was denied.",
                )
            execution_audit_context = ExecutionAuditContext(
                event_id=uuid4(),
                occurred_at=occurred_at,
                request_id=audit_request_id,
                correlation_id=lifecycle_audit_context.correlation_id,
                user_subject=user_subject,
                session_id=application_session.audit_session_id,
                query_candidate_id=candidate_id,
                candidate_owner_subject=user_subject,
                execution_policy_version=candidate.source.execution_policy_version,
                connector_profile_version=candidate.source.connector_profile_version,
            )
            query_runner = getattr(
                http_request.app.state,
                "execution_query_runner",
                None,
            )
            result = execute_candidate_sql(
                candidate=candidate,
                selection=selection,
                business_mssql_connection_string=(
                    settings.business_mssql_source_connection_string
                ),
                business_postgres_url=(
                    str(settings.business_postgres_source_url)
                    if settings.business_postgres_source_url is not None
                    else None
                ),
                application_postgres_url=str(settings.app_postgres_url),
                query_runner=query_runner,
                cancellation_probe=cancellation_probe,
                runtime_safety_state=runtime_safety_state,
                audit_context=execution_audit_context,
            )
        except CandidateLifecycleRevalidationError as exc:
            if exc.audit_event is not None:
                persist_execution_audit_events(
                    session,
                    candidate_id=candidate_id,
                    audit_events=[exc.audit_event],
                )
            audit_events = (
                _serialize_execution_audit_events([exc.audit_event])
                if exc.audit_event is not None
                else None
            )
            raise api_error(
                403,
                "execution_denied",
                "Candidate execution was denied.",
                audit_events=audit_events,
            ) from exc
        except (
            ExecutionConnectorExecutionError,
            ExecutionConnectorSelectionError,
        ) as exc:
            persist_execution_audit_events(
                session,
                candidate_id=candidate_id,
                audit_events=exc.audit_events,
            )
            audit_events = _serialize_execution_audit_events(exc.audit_events)
            raise api_error(
                403,
                "execution_denied",
                "Candidate execution was denied.",
                audit_events=audit_events or None,
            ) from exc
        except ExecutionRuntimeCancelledError as exc:
            persist_execution_audit_events(
                session,
                candidate_id=candidate_id,
                audit_events=exc.audit_events,
            )
            audit_events = _serialize_execution_audit_events(exc.audit_events)
            raise api_error(
                503,
                "execution_unavailable",
                "Candidate execution is unavailable.",
                audit_events=audit_events or None,
            ) from exc
        except ExecutionRuntimeFailureError as exc:
            persist_execution_audit_events(
                session,
                candidate_id=candidate_id,
                audit_events=exc.audit_events,
            )
            audit_events = _serialize_execution_audit_events(exc.audit_events)
            raise api_error(
                503,
                "execution_unavailable",
                "Candidate execution is unavailable.",
                audit_events=audit_events or None,
            ) from exc
        except RuntimeError as exc:
            raise api_error(
                503,
                "execution_unavailable",
                "Candidate execution is unavailable.",
            ) from exc

        persist_execution_audit_events(
            session,
            candidate_id=candidate_id,
            audit_events=result.audit_events,
        )
        return CandidateExecuteResponse(
            candidate_id=candidate_id,
            source_id=result.source_id,
            connector_id=result.connector_id,
            ownership=result.ownership,
            rows=result.rows,
            metadata=result.metadata.model_dump(mode="json", exclude_none=True),
            audit={"events": _serialize_execution_audit_events(result.audit_events)},
        )

    @app.get("/operator/workflow", response_model=OperatorWorkflowSnapshot)
    def read_operator_workflow(
        authenticated_subject: AuthenticatedSubject = Depends(
            require_authenticated_subject
        ),
        session: Session = Depends(require_preview_submission_session),
    ) -> OperatorWorkflowSnapshot:
        authenticated_subject.normalized_subject_id()
        return get_operator_workflow_snapshot(session)

    return app


app = create_app()
