from __future__ import annotations

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


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    connector_id: NonEmptyTrimmedString
    ownership: str
    rows: list[dict[str, Any]]


class ExecutionConnectorExecutionError(PermissionError):
    def __init__(self, *, deny_code: str, message: str) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code


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
    if (
        candidate_source.source_id.strip() != selection.source_id
        or candidate_source.source_family.strip() != selection.source_family
        or not _source_flavor_matches(
            candidate_source=candidate_source,
            selection=selection,
        )
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
) -> list[dict[str, Any]]:
    try:
        import pyodbc  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pyodbc must be installed before the MSSQL execution connector can run."
        ) from exc

    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        cursor.execute(canonical_sql)
        column_names = [column[0] for column in cursor.description or ()]
        return [dict(zip(column_names, row)) for row in cursor.fetchall()]


def _default_postgresql_query_runner(
    *,
    database_url: str,
    canonical_sql: str,
) -> list[dict[str, Any]]:
    try:
        import psycopg  # type: ignore[import-not-found]
        from psycopg.rows import dict_row  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "psycopg must be installed before the PostgreSQL execution connector can run."
        ) from exc

    with psycopg.connect(database_url) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(canonical_sql)
            return [dict(row) for row in cursor.fetchall()]


def execute_candidate_sql(
    *,
    canonical_sql: NonEmptyTrimmedString,
    candidate_source: SourceBoundCandidateMetadata,
    business_mssql_connection_string: NonEmptyTrimmedString | None = None,
    business_postgres_url: NonEmptyTrimmedString | None = None,
    selection: ExecutionConnectorSelection | None = None,
    query_runner: QueryRunner | None = None,
) -> ExecutionResult:
    resolved_selection = (
        selection
        if selection is not None
        else select_execution_connector(candidate_source=candidate_source)
    )
    _require_matching_selection(
        candidate_source=candidate_source,
        selection=resolved_selection,
    )

    if resolved_selection.ownership != "backend":
        raise ExecutionConnectorExecutionError(
            deny_code=DENY_UNSUPPORTED_SOURCE_BINDING,
            message="Execution connectors must remain backend-owned.",
        )

    if resolved_selection.connector_id == "mssql_readonly":
        if business_mssql_connection_string is None:
            raise RuntimeError(
                "A backend-owned business MSSQL connection string is required before "
                "the MSSQL execution connector can run."
            )

        effective_query_runner = query_runner or _default_mssql_query_runner
        rows = effective_query_runner(
            connection_string=business_mssql_connection_string,
            canonical_sql=canonical_sql,
        )
    elif resolved_selection.connector_id == "postgresql_readonly":
        if business_postgres_url is None:
            raise RuntimeError(
                "A backend-owned business PostgreSQL URL is required before the "
                "PostgreSQL execution connector can run."
            )

        effective_query_runner = query_runner or _default_postgresql_query_runner
        rows = effective_query_runner(
            database_url=business_postgres_url,
            canonical_sql=canonical_sql,
        )
    else:
        raise ExecutionConnectorSelectionError(
            deny_code=DENY_UNSUPPORTED_SOURCE_BINDING,
            message=(
                "No backend-owned execution runtime is registered for connector "
                f"'{resolved_selection.connector_id}'."
            ),
        )
    return ExecutionResult(
        source_id=resolved_selection.source_id,
        connector_id=resolved_selection.connector_id,
        ownership=resolved_selection.ownership,
        rows=rows,
    )
