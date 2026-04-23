from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated

from app.features.execution.connector_selection import (
    ExecutionConnectorSelection,
    ExecutionConnectorSelectionError,
    select_execution_connector,
)
from app.features.guard.deny_taxonomy import (
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


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    connector_id: NonEmptyTrimmedString
    ownership: str
    rows: list[dict[str, Any]]


class ExecutableCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: NonEmptyTrimmedString
    source: SourceBoundCandidateMetadata


class ExecutionConnectorExecutionError(PermissionError):
    def __init__(self, *, deny_code: str, message: str) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code


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


def _require_matching_selection(
    *,
    candidate_source: SourceBoundCandidateMetadata,
    selection: ExecutionConnectorSelection,
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


def execute_candidate_sql(
    *,
    candidate: ExecutableCandidateRecord,
    selection: ExecutionConnectorSelection,
    business_mssql_connection_string: NonEmptyTrimmedString | None = None,
    business_postgres_url: NonEmptyTrimmedString | None = None,
    query_runner: QueryRunner | None = None,
    cancellation_probe: CancellationProbe | None = None,
) -> ExecutionResult:
    _require_matching_selection(
        candidate_source=candidate.source,
        selection=selection,
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

    return ExecutionResult(
        source_id=selection.source_id,
        connector_id=selection.connector_id,
        ownership=selection.ownership,
        rows=_cap_rows(rows, runtime_controls=runtime_controls),
    )
