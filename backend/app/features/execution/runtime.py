from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PrivateAttr, StringConstraints
from typing_extensions import Annotated

from app.features.audit.event_model import SourceAwareAuditEvent
from app.features.execution.connector_selection import (
    ExecutionConnectorSelection,
    ExecutionConnectorSelectionError,
    select_execution_connector,
)
from app.features.guard.deny_taxonomy import (
    DENY_APPLICATION_POSTGRES_REUSE,
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


@dataclass(frozen=True)
class ExecutionRuntimeControls:
    source_family: str
    timeout_seconds: int
    max_rows: int
    cancellation_probe: CancellationProbe | None = None


@dataclass(frozen=True)
class _PostgresConnectionIdentity:
    username: str
    host: str
    port: int
    database: str

    @property
    def endpoint_contract(self) -> tuple[str, int, str]:
        return (self.host, self.port, self.database)


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    _audit_event: Optional[SourceAwareAuditEvent] = PrivateAttr(default=None)

    source_id: NonEmptyTrimmedString
    connector_id: NonEmptyTrimmedString
    ownership: str
    rows: list[dict[str, Any]]

    @property
    def audit_event(self) -> Optional[SourceAwareAuditEvent]:
        return self._audit_event


class ExecutableCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: NonEmptyTrimmedString
    source: SourceBoundCandidateMetadata


class ExecutionAuditContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    occurred_at: datetime
    request_id: str
    correlation_id: str
    user_subject: str
    session_id: str
    query_candidate_id: Optional[str] = None
    candidate_owner_subject: Optional[str] = None
    connector_profile_version: Optional[int] = None


class ExecutionConnectorExecutionError(PermissionError):
    def __init__(
        self,
        *,
        deny_code: str,
        message: str,
        audit_event: SourceAwareAuditEvent | None = None,
    ) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code
        self.audit_event = audit_event


class ExecutionRuntimeCancelledError(RuntimeError):
    pass


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
        DENY_SOURCE_BINDING_MISMATCH: "source_binding_mismatch",
        DENY_UNSUPPORTED_SOURCE_BINDING: "unsupported_source_binding",
    }.get(deny_code, "execution_denied")


def _build_execution_audit_event(
    *,
    event_type: str,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
    primary_deny_code: str | None = None,
    execution_row_count: int | None = None,
    result_truncated: bool | None = None,
) -> SourceAwareAuditEvent | None:
    if audit_context is None:
        return None

    return SourceAwareAuditEvent(
        event_id=audit_context.event_id,
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
        connector_profile_version=audit_context.connector_profile_version,
        primary_deny_code=primary_deny_code,
        denial_cause=(
            _execution_denial_cause_for_code(primary_deny_code)
            if primary_deny_code is not None
            else None
        ),
        candidate_state="denied" if primary_deny_code is not None else None,
        execution_row_count=execution_row_count,
        result_truncated=result_truncated,
    )


def _attach_execution_denial_audit_event(
    *,
    error: ExecutionConnectorExecutionError,
    candidate_source: SourceBoundCandidateMetadata,
    audit_context: ExecutionAuditContext | None,
) -> ExecutionConnectorExecutionError:
    if error.audit_event is not None or audit_context is None:
        return error
    message = str(error).split(": ", 1)[1] if ": " in str(error) else str(error)
    return ExecutionConnectorExecutionError(
        deny_code=error.deny_code,
        message=message,
        audit_event=_build_execution_audit_event(
            event_type="execution_denied",
            candidate_source=candidate_source,
            audit_context=audit_context,
            primary_deny_code=error.deny_code,
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
            audit_event=_build_execution_audit_event(
                event_type="execution_denied",
                candidate_source=candidate_source,
                audit_context=audit_context,
                primary_deny_code=DENY_SOURCE_BINDING_MISMATCH,
            ),
        )


def _default_mssql_query_runner(
    *,
    connection_string: str,
    canonical_sql: str,
    runtime_controls: ExecutionRuntimeControls,
) -> list[dict[str, Any]]:
    try:
        import pyodbc  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pyodbc must be installed before the MSSQL execution connector can run."
        ) from exc

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
    try:
        import psycopg  # type: ignore[import-not-found]
        from psycopg.rows import dict_row  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "psycopg must be installed before the PostgreSQL execution connector can run."
        ) from exc

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
        cancellation_probe=cancellation_probe,
    )


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
) -> list[dict[str, Any]]:
    if len(rows) <= runtime_controls.max_rows:
        return rows
    return rows[: runtime_controls.max_rows]


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
    except ExecutionConnectorExecutionError as exc:
        raise _attach_execution_denial_audit_event(
            error=exc,
            candidate_source=candidate.source,
            audit_context=audit_context,
        ) from exc

    capped_rows = _cap_rows(rows, runtime_controls=runtime_controls)

    result = ExecutionResult(
        source_id=selection.source_id,
        connector_id=selection.connector_id,
        ownership=selection.ownership,
        rows=capped_rows,
    )
    result._audit_event = _build_execution_audit_event(
        event_type="execution_completed",
        candidate_source=candidate.source,
        audit_context=audit_context,
        execution_row_count=len(capped_rows),
        result_truncated=len(rows) > len(capped_rows),
    )
    return result
