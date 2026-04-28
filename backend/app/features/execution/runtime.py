from __future__ import annotations

import inspect
import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, PrivateAttr, StringConstraints
from typing_extensions import Annotated

from app.features.audit.event_model import (
    ExecutedEvidenceAuditPayload,
    SourceAwareAuditEvent,
)
from app.features.evaluation.scenario_metadata import (
    build_release_gate_scenario_metadata,
)
from app.features.execution.connector_selection import (
    ExecutionConnectorSelection,
    ExecutionConnectorSelectionError,
    select_execution_connector,
)
from app.features.guard.deny_taxonomy import (
    DENY_APPLICATION_POSTGRES_REUSE,
    DENY_RUNTIME_CONCURRENCY_LIMIT,
    DENY_RUNTIME_KILL_SWITCH,
    DENY_RUNTIME_RATE_LIMIT,
    DENY_SOURCE_BINDING_MISMATCH,
    DENY_UNSUPPORTED_SOURCE_BINDING,
)
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
QueryRunner = Callable[..., list[dict[str, Any]]]
CancellationProbe = Callable[[], bool]

DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY = {
    "mssql": 30,
    "postgresql": 30,
}
DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY = {
    "mssql": 200,
    "postgresql": 200,
}
DEFAULT_MAX_PAYLOAD_BYTES_BY_SOURCE_FAMILY = {
    "mssql": 64 * 1024,
    "postgresql": 64 * 1024,
}
MSSQL_ODBC_DRIVER_NAME = "ODBC Driver 18 for SQL Server"


@dataclass(frozen=True)
class ExecutionRuntimeControls:
    source_family: str
    timeout_seconds: int
    max_rows: int
    max_payload_bytes: int = 64 * 1024
    cancellation_probe: CancellationProbe | None = None


@dataclass(frozen=True)
class ExecutionRuntimeSafetyState:
    disabled_source_ids: frozenset[str] = field(default_factory=frozenset)
    disabled_source_families: frozenset[str] = field(default_factory=frozenset)
    rate_limited_source_ids: frozenset[str] = field(default_factory=frozenset)
    rate_limited_source_families: frozenset[str] = field(default_factory=frozenset)
    active_executions_by_source_id: Mapping[str, int] = field(default_factory=dict)
    active_executions_by_source_family: Mapping[str, int] = field(default_factory=dict)
    max_concurrent_executions_by_source_id: Mapping[str, int] = field(default_factory=dict)
    max_concurrent_executions_by_source_family: Mapping[str, int] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class _PostgresConnectionIdentity:
    username: str
    host: str
    port: int
    database: str

    @property
    def endpoint_contract(self) -> tuple[str, int, str]:
        return (self.host, self.port, self.database)


class ExecutionResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None
    candidate_id: Optional[NonEmptyTrimmedString] = None
    execution_run_id: Optional[UUID] = None
    row_count: int
    row_limit: int
    payload_bytes: int
    payload_limit_bytes: int
    result_truncated: bool
    truncation_reason: Optional[NonEmptyTrimmedString] = None


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    _audit_event: Optional[SourceAwareAuditEvent] = PrivateAttr(default=None)
    _audit_events: list[SourceAwareAuditEvent] = PrivateAttr(default_factory=list)

    source_id: NonEmptyTrimmedString
    connector_id: NonEmptyTrimmedString
    ownership: str
    rows: list[dict[str, Any]]
    metadata: ExecutionResultMetadata

    @property
    def audit_event(self) -> Optional[SourceAwareAuditEvent]:
        return self._audit_event

    @property
    def audit_events(self) -> list[SourceAwareAuditEvent]:
        return list(self._audit_events)

    @property
    def executed_evidence(self) -> Optional[ExecutedEvidenceAuditPayload]:
        audit_event = self.audit_event
        if (
            audit_event is None
            or audit_event.event_type != "execution_completed"
            or self.ownership != "backend"
            or audit_event.query_candidate_id is None
            or audit_event.dataset_contract_version is None
            or audit_event.schema_snapshot_version is None
            or audit_event.execution_row_count is None
            or audit_event.execution_row_count < 0
            or audit_event.result_truncated is None
            or self.metadata.execution_run_id is None
        ):
            return None

        return ExecutedEvidenceAuditPayload(
            source_id=audit_event.source_id,
            source_family=audit_event.source_family,
            source_flavor=audit_event.source_flavor,
            dataset_contract_version=audit_event.dataset_contract_version,
            schema_snapshot_version=audit_event.schema_snapshot_version,
            execution_policy_version=audit_event.execution_policy_version,
            connector_profile_version=audit_event.connector_profile_version,
            candidate_id=audit_event.query_candidate_id,
            execution_run_id=self.metadata.execution_run_id,
            execution_audit_event_id=audit_event.event_id,
            row_count=audit_event.execution_row_count,
            result_truncated=audit_event.result_truncated,
        )


class ExecutableCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: NonEmptyTrimmedString
    source: SourceBoundCandidateMetadata


class ExecutionAuditContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    causation_event_id: Optional[UUID] = None
    occurred_at: datetime
    request_id: str
    correlation_id: str
    user_subject: str
    session_id: str
    query_candidate_id: Optional[str] = None
    candidate_owner_subject: Optional[str] = None
    guard_audit_event_id: Optional[UUID] = None
    execution_policy_version: Optional[int] = None
    connector_profile_version: Optional[int] = None


class ExecutionConnectorExecutionError(PermissionError):
    def __init__(
        self,
        *,
        deny_code: str,
        message: str,
        audit_event: SourceAwareAuditEvent | None = None,
        audit_events: list[SourceAwareAuditEvent] | None = None,
    ) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code
        self.audit_events = list(audit_events or ([audit_event] if audit_event else []))
        self.audit_event = audit_event or (
            self.audit_events[-1] if self.audit_events else None
        )


class ExecutionRuntimeCancelledError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        audit_events: list[SourceAwareAuditEvent] | None = None,
    ) -> None:
        super().__init__(message)
        self.audit_events = list(audit_events or [])
        self.audit_event = self.audit_events[-1] if self.audit_events else None


class ExecutionRuntimeFailureError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        audit_events: list[SourceAwareAuditEvent] | None = None,
    ) -> None:
        super().__init__(message)
        self.audit_events = list(audit_events or [])
        self.audit_event = self.audit_events[-1] if self.audit_events else None


class MSSQLExecutionRuntimeUnavailable(RuntimeError):
    """Raised when required backend-owned MSSQL runtime dependencies are absent."""


class PostgreSQLExecutionRuntimeUnavailable(RuntimeError):
    """Raised when required backend-owned PostgreSQL runtime dependencies are absent."""


def check_mssql_execution_runtime_readiness() -> dict[str, object]:
    try:
        pyodbc = importlib.import_module("pyodbc")
    except (ModuleNotFoundError, ImportError) as exc:
        raise MSSQLExecutionRuntimeUnavailable(
            "pyodbc must be installed and importable before the MSSQL execution "
            "connector can run."
        ) from exc

    drivers = getattr(pyodbc, "drivers", None)
    if not callable(drivers):
        raise MSSQLExecutionRuntimeUnavailable(
            "pyodbc driver discovery is unavailable; the MSSQL execution connector "
            "cannot verify ODBC Driver 18 for SQL Server."
        )

    try:
        available_drivers = tuple(str(driver).strip() for driver in drivers())
    except Exception as exc:
        raise MSSQLExecutionRuntimeUnavailable(
            "pyodbc could not enumerate ODBC drivers for the MSSQL execution connector."
        ) from exc

    if MSSQL_ODBC_DRIVER_NAME not in available_drivers:
        raise MSSQLExecutionRuntimeUnavailable(
            "ODBC Driver 18 for SQL Server must be installed before the MSSQL "
            "execution connector can run."
        )

    return {
        "pyodbc": "available",
        "odbc_driver": MSSQL_ODBC_DRIVER_NAME,
    }


def check_postgresql_execution_runtime_readiness() -> dict[str, object]:
    try:
        psycopg = importlib.import_module("psycopg")
        psycopg_rows = importlib.import_module("psycopg.rows")
    except (ModuleNotFoundError, ImportError) as exc:
        raise PostgreSQLExecutionRuntimeUnavailable(
            "psycopg must be installed and importable before the PostgreSQL "
            "execution connector can run."
        ) from exc
    except Exception as exc:
        raise PostgreSQLExecutionRuntimeUnavailable(
            "psycopg failed to initialize for the PostgreSQL execution connector."
        ) from exc

    if not callable(getattr(psycopg, "connect", None)):
        raise PostgreSQLExecutionRuntimeUnavailable(
            "psycopg connection support is unavailable; the PostgreSQL execution "
            "connector cannot open backend-owned source connections."
        )

    if not callable(getattr(psycopg_rows, "dict_row", None)):
        raise PostgreSQLExecutionRuntimeUnavailable(
            "psycopg row factory support is unavailable; the PostgreSQL execution "
            "connector cannot materialize result rows."
        )

    return {"psycopg": "available", "dict_row": "available"}


def _source_flavor_matches(
    *,
    candidate_source: SourceBoundCandidateMetadata,
    selection: ExecutionConnectorSelection,
) -> bool:
    candidate_flavor = candidate_source.source_flavor.strip() if candidate_source.source_flavor else None
    selection_flavor = selection.source_flavor.strip() if selection.source_flavor else None
    return candidate_flavor == selection_flavor


def _execution_denial_cause_for_code(deny_code: str) -> str:
    return {
        DENY_APPLICATION_POSTGRES_REUSE: "application_postgresql_reuse",
        DENY_RUNTIME_KILL_SWITCH: "runtime_kill_switch",
        DENY_RUNTIME_RATE_LIMIT: "runtime_rate_limit",
        DENY_RUNTIME_CONCURRENCY_LIMIT: "runtime_concurrency_limit",
        DENY_SOURCE_BINDING_MISMATCH: "source_binding_mismatch",
        DENY_UNSUPPORTED_SOURCE_BINDING: "unsupported_source_binding",
    }.get(deny_code, "execution_denied")


def _build_execution_audit_event(
    *,
    event_type: str,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
    canonical_sql: str | None = None,
    primary_deny_code: str | None = None,
    candidate_state: str | None = None,
    execution_row_count: int | None = None,
    result_truncated: bool | None = None,
) -> SourceAwareAuditEvent | None:
    if audit_context is None:
        return None

    event = SourceAwareAuditEvent(
        event_id=(
            audit_context.event_id
            if event_type in {"execution_completed", "execution_denied"}
            else uuid4()
        ),
        event_type=event_type,
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
        execution_policy_version=(
            audit_context.execution_policy_version
            or candidate_source.execution_policy_version
        ),
        connector_profile_version=(
            audit_context.connector_profile_version
            or candidate_source.connector_profile_version
        ),
        primary_deny_code=primary_deny_code,
        denial_cause=(
            _execution_denial_cause_for_code(primary_deny_code)
            if primary_deny_code is not None
            else None
        ),
        candidate_state=(
            candidate_state
            if candidate_state is not None
            else "denied" if primary_deny_code is not None else None
        ),
        execution_row_count=execution_row_count,
        result_truncated=result_truncated,
    )
    if canonical_sql is not None and event_type in {
        "execution_completed",
        "execution_denied",
    }:
        guard_decision = "allow" if primary_deny_code is None else "reject"
        metadata = build_release_gate_scenario_metadata(
            source_id=candidate_source.source_id,
            source_family=candidate_source.source_family,
            source_flavor=candidate_source.source_flavor,
            dataset_contract_version=candidate_source.dataset_contract_version,
            schema_snapshot_version=candidate_source.schema_snapshot_version,
            execution_policy_version=(
                audit_context.execution_policy_version
                or candidate_source.execution_policy_version
            ),
            connector_profile_version=(
                audit_context.connector_profile_version
                or candidate_source.connector_profile_version
            ),
            canonical_sql=canonical_sql,
            candidate_id=audit_context.query_candidate_id,
            guard_decision=guard_decision,
            guard_audit_event_id=audit_context.guard_audit_event_id,
            execution_run_id=event.event_id,
            execution_audit_event_id=event.event_id,
        )
        if metadata is not None:
            event.release_gate_scenario = metadata
    return event


def _build_execution_audit_events(
    *,
    event_types: list[str],
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
    canonical_sql: str | None = None,
    primary_deny_code: str | None = None,
    candidate_state: str | None = None,
    execution_row_count: int | None = None,
    result_truncated: bool | None = None,
) -> list[SourceAwareAuditEvent]:
    if audit_context is None:
        return []

    events: list[SourceAwareAuditEvent] = []
    causation_event_id = audit_context.causation_event_id
    for event_type in event_types:
        event = _build_execution_audit_event(
            event_type=event_type,
            candidate_source=candidate_source,
            audit_context=audit_context,
            canonical_sql=canonical_sql,
            primary_deny_code=(
                primary_deny_code
                if event_type
                in {"execution_denied", "request_rate_limited", "concurrency_rejected"}
                else None
            ),
            candidate_state=(
                candidate_state if event_type == "execution_failed" else None
            ),
            execution_row_count=(
                execution_row_count if event_type == "execution_completed" else None
            ),
            result_truncated=(
                result_truncated if event_type == "execution_completed" else None
            ),
        )
        if event is None:
            continue
        if causation_event_id is not None:
            event.causation_event_id = causation_event_id
        causation_event_id = event.event_id
        events.append(event)
    return events


def _attach_execution_denial_audit_event(
    *,
    error: ExecutionConnectorExecutionError | ExecutionConnectorSelectionError,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
) -> ExecutionConnectorExecutionError | ExecutionConnectorSelectionError:
    if error.audit_event is not None or audit_context is None:
        return error
    message = str(error).split(": ", 1)[1] if ": " in str(error) else str(error)
    return type(error)(
        deny_code=error.deny_code,
        message=message,
        audit_events=_build_execution_audit_events(
            event_types=["execution_requested", "execution_denied"],
            candidate_source=candidate_source,
            audit_context=audit_context,
            canonical_sql=None,
            primary_deny_code=error.deny_code,
        ),
    )


def _attach_cancellation_audit_event(
    *,
    error: ExecutionRuntimeCancelledError,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
) -> ExecutionRuntimeCancelledError:
    if error.audit_event is not None or audit_context is None:
        return error
    return ExecutionRuntimeCancelledError(
        str(error),
        audit_events=_build_execution_audit_events(
            event_types=["execution_requested", "execution_failed"],
            candidate_source=candidate_source,
            audit_context=audit_context,
            canonical_sql=None,
            candidate_state="canceled",
        ),
    )


def _attach_runtime_failure_audit_event(
    *,
    error: RuntimeError,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
) -> ExecutionRuntimeFailureError:
    if isinstance(error, ExecutionRuntimeFailureError) and error.audit_event is not None:
        return error
    return ExecutionRuntimeFailureError(
        str(error),
        audit_events=_build_execution_audit_events(
            event_types=[
                "execution_requested",
                "execution_started",
                "execution_failed",
            ],
            candidate_source=candidate_source,
            audit_context=audit_context,
            canonical_sql=None,
            candidate_state="failed",
        ),
    )


def _require_matching_selection(
    *,
    candidate_source: SourceBoundCandidateMetadata,
    selection: ExecutionConnectorSelection,
    audit_context: ExecutionAuditContext | None = None,
) -> None:
    expected_selection = select_execution_connector(candidate_source=candidate_source)
    if (
        candidate_source.source_id.strip() != selection.source_id
        or candidate_source.source_family.strip() != selection.source_family
        or not _source_flavor_matches(
            candidate_source=candidate_source,
            selection=selection,
        )
        or selection.connector_id != expected_selection.connector_id
        or selection.ownership != expected_selection.ownership
    ):
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_SOURCE_BINDING_MISMATCH,
            message=(
                "The candidate-bound source metadata does not match the selected "
                "connector binding."
            ),
        )


def _default_mssql_query_runner(
    *,
    connection_string: str,
    canonical_sql: str,
    runtime_controls: ExecutionRuntimeControls,
) -> list[dict[str, Any]]:
    check_mssql_execution_runtime_readiness()
    import pyodbc  # type: ignore[import-not-found]

    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        if not hasattr(cursor, "timeout"):
            raise RuntimeError(
                "The MSSQL execution connector requires cursor timeout support to "
                "enforce backend-owned runtime controls."
            )
        cursor.timeout = runtime_controls.timeout_seconds
        _raise_if_cancelled(
            runtime_controls=runtime_controls,
            connection=connection,
            message="Execution canceled before the MSSQL query started.",
        )
        cursor.execute(canonical_sql)
        _raise_if_cancelled(
            runtime_controls=runtime_controls,
            connection=connection,
            message="Execution canceled before the MSSQL result set was read.",
        )
        column_names = [column[0] for column in cursor.description or ()]
        rows = cursor.fetchmany(runtime_controls.max_rows + 1)
        return [dict(zip(column_names, row)) for row in rows]


def _default_postgresql_query_runner(
    *,
    database_url: str,
    canonical_sql: str,
    runtime_controls: ExecutionRuntimeControls,
) -> list[dict[str, Any]]:
    check_postgresql_execution_runtime_readiness()
    import psycopg  # type: ignore[import-not-found]
    from psycopg.rows import dict_row  # type: ignore[import-not-found]

    timeout_milliseconds = runtime_controls.timeout_seconds * 1000
    with psycopg.connect(
        database_url,
        connect_timeout=runtime_controls.timeout_seconds,
        options=(
            f"-c statement_timeout={timeout_milliseconds} "
            f"-c lock_timeout={timeout_milliseconds}"
        ),
    ) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            _raise_if_cancelled(
                runtime_controls=runtime_controls,
                connection=connection,
                message="Execution canceled before the PostgreSQL query started.",
            )
            cursor.execute(canonical_sql)
            _raise_if_cancelled(
                runtime_controls=runtime_controls,
                connection=connection,
                message="Execution canceled before the PostgreSQL result set was read.",
            )
            return [dict(row) for row in cursor.fetchmany(runtime_controls.max_rows + 1)]


def _resolve_runtime_controls(
    *,
    selection: ExecutionConnectorSelection,
    cancellation_probe: CancellationProbe | None,
) -> ExecutionRuntimeControls:
    try:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY[selection.source_family]
        max_rows = DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY[selection.source_family]
        max_payload_bytes = DEFAULT_MAX_PAYLOAD_BYTES_BY_SOURCE_FAMILY[
            selection.source_family
        ]
    except KeyError as exc:
        raise ExecutionConnectorSelectionError(
            deny_code=DENY_UNSUPPORTED_SOURCE_BINDING,
            message=(
                "No source-aware execution runtime controls are registered for source "
                f"family '{selection.source_family}'."
            ),
        ) from exc

    return ExecutionRuntimeControls(
        source_family=selection.source_family,
        timeout_seconds=timeout_seconds,
        max_rows=max_rows,
        max_payload_bytes=max_payload_bytes,
        cancellation_probe=cancellation_probe,
    )


def _scope_contains(
    *,
    values: frozenset[str],
    candidate_value: str,
) -> bool:
    return candidate_value.strip() in values


def _concurrency_limit_exceeded(
    *,
    active_by_scope: Mapping[str, int],
    max_by_scope: Mapping[str, int],
    scope: str,
) -> bool:
    max_allowed = max_by_scope.get(scope)
    if max_allowed is None:
        return False
    return active_by_scope.get(scope, 0) >= max_allowed


def _require_runtime_safety_controls_allow_execution(
    *,
    candidate_source: SourceBoundCandidateMetadata,
    runtime_safety_state: ExecutionRuntimeSafetyState | None,
) -> None:
    if runtime_safety_state is None:
        return

    source_id = candidate_source.source_id.strip()
    source_family = candidate_source.source_family.strip()

    if _scope_contains(
        values=runtime_safety_state.disabled_source_ids,
        candidate_value=source_id,
    ) or _scope_contains(
        values=runtime_safety_state.disabled_source_families,
        candidate_value=source_family,
    ):
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_RUNTIME_KILL_SWITCH,
            message=(
                "The backend-owned runtime kill switch is enabled for this "
                "candidate-bound source."
            ),
        )

    if _scope_contains(
        values=runtime_safety_state.rate_limited_source_ids,
        candidate_value=source_id,
    ) or _scope_contains(
        values=runtime_safety_state.rate_limited_source_families,
        candidate_value=source_family,
    ):
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_RUNTIME_RATE_LIMIT,
            message=(
                "The backend-owned runtime rate limit rejected this "
                "candidate-bound source."
            ),
        )

    if _concurrency_limit_exceeded(
        active_by_scope=runtime_safety_state.active_executions_by_source_id,
        max_by_scope=runtime_safety_state.max_concurrent_executions_by_source_id,
        scope=source_id,
    ) or _concurrency_limit_exceeded(
        active_by_scope=runtime_safety_state.active_executions_by_source_family,
        max_by_scope=runtime_safety_state.max_concurrent_executions_by_source_family,
        scope=source_family,
    ):
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_RUNTIME_CONCURRENCY_LIMIT,
            message=(
                "The backend-owned runtime concurrency limit rejected this "
                "candidate-bound source."
            ),
        )


def preflight_execution_runtime_controls(
    *,
    candidate_source: SourceBoundCandidateMetadata,
    selection: ExecutionConnectorSelection,
    cancellation_probe: CancellationProbe | None = None,
    runtime_safety_state: ExecutionRuntimeSafetyState | None = None,
    audit_context: ExecutionAuditContext | None = None,
) -> None:
    try:
        runtime_controls = _resolve_runtime_controls(
            selection=selection,
            cancellation_probe=cancellation_probe,
        )
        _raise_if_cancelled(
            runtime_controls=runtime_controls,
            message="Execution canceled before the backend-owned query runner started.",
        )
        _require_runtime_safety_controls_allow_execution(
            candidate_source=candidate_source,
            runtime_safety_state=runtime_safety_state,
        )
    except ExecutionRuntimeCancelledError as exc:
        raise _attach_cancellation_audit_event(
            error=exc,
            candidate_source=candidate_source,
            audit_context=audit_context,
        ) from exc
    except (ExecutionConnectorExecutionError, ExecutionConnectorSelectionError) as exc:
        raise _attach_execution_denial_audit_event(
            error=exc,
            candidate_source=candidate_source,
            audit_context=audit_context,
        ) from exc


def _raise_if_cancelled(
    *,
    runtime_controls: ExecutionRuntimeControls,
    message: str,
    connection: Any | None = None,
) -> None:
    cancellation_probe = runtime_controls.cancellation_probe
    if cancellation_probe is None or not cancellation_probe():
        return

    if connection is not None and hasattr(connection, "cancel"):
        try:
            connection.cancel()
        except Exception:
            pass
    raise ExecutionRuntimeCancelledError(message)


def _execute_query_runner(
    *,
    query_runner: QueryRunner,
    runtime_controls: ExecutionRuntimeControls,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    signature = inspect.signature(query_runner)
    parameters = signature.parameters.values()
    accepts_runtime_controls = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD or parameter.name == "runtime_controls"
        for parameter in parameters
    )
    if accepts_runtime_controls:
        return query_runner(runtime_controls=runtime_controls, **kwargs)
    return query_runner(**kwargs)


def _cap_rows(
    rows: list[dict[str, Any]],
    *,
    runtime_controls: ExecutionRuntimeControls,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
) -> tuple[list[dict[str, Any]], ExecutionResultMetadata]:
    row_limited_rows = rows[: runtime_controls.max_rows]
    capped_rows: list[dict[str, Any]] = []
    payload_bytes = _result_payload_size(capped_rows)
    payload_truncated = False

    for row in row_limited_rows:
        candidate_rows = [*capped_rows, row]
        candidate_payload_bytes = _result_payload_size(candidate_rows)
        if candidate_payload_bytes > runtime_controls.max_payload_bytes:
            payload_truncated = True
            break
        capped_rows = candidate_rows
        payload_bytes = candidate_payload_bytes

    row_truncated = len(rows) > len(row_limited_rows)
    truncation_reason: str | None = None
    if payload_truncated:
        truncation_reason = "payload_limit"
    elif row_truncated:
        truncation_reason = "row_limit"

    return capped_rows, ExecutionResultMetadata(
        source_id=candidate_source.source_id,
        source_family=candidate_source.source_family,
        source_flavor=candidate_source.source_flavor,
        candidate_id=audit_context.query_candidate_id if audit_context is not None else None,
        execution_run_id=audit_context.event_id if audit_context is not None else None,
        row_count=len(capped_rows),
        row_limit=runtime_controls.max_rows,
        payload_bytes=payload_bytes,
        payload_limit_bytes=runtime_controls.max_payload_bytes,
        result_truncated=truncation_reason is not None,
        truncation_reason=truncation_reason,
    )


def _result_payload_size(rows: list[dict[str, Any]]) -> int:
    return len(
        json.dumps(
            rows,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    )


def _postgres_identity_from_url(
    *,
    database_url: str,
    role_name: str,
) -> _PostgresConnectionIdentity:
    parsed = urlsplit(database_url)
    if not parsed.scheme.startswith("postgresql"):
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_APPLICATION_POSTGRES_REUSE,
            message=f"{role_name} must use a PostgreSQL URL.",
        )

    username = unquote(parsed.username or "").strip()
    host = (parsed.hostname or "").strip().casefold()
    database = unquote(parsed.path.lstrip("/")).strip()
    if not username or not host or not database:
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_APPLICATION_POSTGRES_REUSE,
            message=(
                f"{role_name} is missing a trusted PostgreSQL user, host, or "
                "database identity."
            ),
        )

    try:
        port = parsed.port or 5432
    except ValueError as exc:
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_APPLICATION_POSTGRES_REUSE,
            message=f"{role_name} has an invalid PostgreSQL port.",
        ) from exc

    return _PostgresConnectionIdentity(
        username=username,
        host=host,
        port=port,
        database=database,
    )


def _require_separate_postgresql_execution_target(
    *,
    business_postgres_url: str,
    application_postgres_url: str,
) -> None:
    business_identity = _postgres_identity_from_url(
        database_url=business_postgres_url,
        role_name="business PostgreSQL execution URL",
    )
    application_identity = _postgres_identity_from_url(
        database_url=application_postgres_url,
        role_name="application PostgreSQL URL",
    )

    if business_identity == application_identity:
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_APPLICATION_POSTGRES_REUSE,
            message=(
                "The PostgreSQL execution connector must not reuse the application "
                "PostgreSQL connection identity."
            ),
        )

    if business_identity.endpoint_contract == application_identity.endpoint_contract:
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_APPLICATION_POSTGRES_REUSE,
            message=(
                "The PostgreSQL execution connector must not target the application "
                "PostgreSQL endpoint contract."
            ),
        )


def execute_candidate_sql(
    *,
    candidate: ExecutableCandidateRecord,
    selection: ExecutionConnectorSelection,
    business_mssql_connection_string: NonEmptyTrimmedString | None = None,
    business_postgres_url: NonEmptyTrimmedString | None = None,
    application_postgres_url: NonEmptyTrimmedString | None = None,
    query_runner: QueryRunner | None = None,
    cancellation_probe: CancellationProbe | None = None,
    runtime_safety_state: ExecutionRuntimeSafetyState | None = None,
    audit_context: ExecutionAuditContext | None = None,
) -> ExecutionResult:
    try:
        _require_matching_selection(
            candidate_source=candidate.source,
            selection=selection,
            audit_context=audit_context,
        )

        if selection.ownership != "backend":
            raise ExecutionConnectorExecutionError(
                deny_code=DENY_UNSUPPORTED_SOURCE_BINDING,
                message="Execution connectors must remain backend-owned.",
            )

        runtime_controls = _resolve_runtime_controls(
            selection=selection,
            cancellation_probe=cancellation_probe,
        )
        _raise_if_cancelled(
            runtime_controls=runtime_controls,
            message="Execution canceled before the backend-owned query runner started.",
        )
        _require_runtime_safety_controls_allow_execution(
            candidate_source=candidate.source,
            runtime_safety_state=runtime_safety_state,
        )

        if selection.connector_id == "mssql_readonly":
            if business_mssql_connection_string is None:
                raise RuntimeError(
                    "A backend-owned business MSSQL connection string is required before "
                    "the MSSQL execution connector can run."
                )

            effective_query_runner = query_runner or _default_mssql_query_runner
            rows = _execute_query_runner(
                query_runner=effective_query_runner,
                runtime_controls=runtime_controls,
                connection_string=business_mssql_connection_string,
                canonical_sql=candidate.canonical_sql,
            )
        elif selection.connector_id == "postgresql_readonly":
            if business_postgres_url is None:
                raise RuntimeError(
                    "A backend-owned business PostgreSQL URL is required before the "
                    "PostgreSQL execution connector can run."
                )

            if application_postgres_url is None:
                from app.core.config import get_settings

                application_postgres_url = str(get_settings().app_postgres_url)

            _require_separate_postgresql_execution_target(
                business_postgres_url=business_postgres_url,
                application_postgres_url=application_postgres_url,
            )

            effective_query_runner = query_runner or _default_postgresql_query_runner
            rows = _execute_query_runner(
                query_runner=effective_query_runner,
                runtime_controls=runtime_controls,
                database_url=business_postgres_url,
                canonical_sql=candidate.canonical_sql,
            )
        else:
            raise ExecutionConnectorSelectionError(
                deny_code=DENY_UNSUPPORTED_SOURCE_BINDING,
                message=(
                    "No backend-owned execution runtime is registered for connector "
                    f"'{selection.connector_id}'."
                ),
            )
    except ExecutionRuntimeCancelledError as exc:
        raise _attach_cancellation_audit_event(
            error=exc,
            candidate_source=candidate.source,
            audit_context=audit_context,
        ) from exc
    except (ExecutionConnectorExecutionError, ExecutionConnectorSelectionError) as exc:
        raise _attach_execution_denial_audit_event(
            error=exc,
            candidate_source=candidate.source,
            audit_context=audit_context,
        ) from exc
    except RuntimeError as exc:
        raise _attach_runtime_failure_audit_event(
            error=exc,
            candidate_source=candidate.source,
            audit_context=audit_context,
        ) from exc

    capped_rows, metadata = _cap_rows(
        rows,
        runtime_controls=runtime_controls,
        candidate_source=candidate.source,
        audit_context=audit_context,
    )

    result = ExecutionResult(
        source_id=selection.source_id,
        connector_id=selection.connector_id,
        ownership=selection.ownership,
        rows=capped_rows,
        metadata=metadata,
    )
    result._audit_events = _build_execution_audit_events(
        event_types=["execution_requested", "execution_started", "execution_completed"],
        candidate_source=candidate.source,
        audit_context=audit_context,
        canonical_sql=candidate.canonical_sql,
        execution_row_count=metadata.row_count,
        result_truncated=metadata.result_truncated,
    )
    result._audit_event = result._audit_events[-1] if result._audit_events else None
    return result
