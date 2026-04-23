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
MssqlQueryRunner = Callable[..., list[dict[str, Any]]]


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


def execute_candidate_sql(
    *,
    canonical_sql: NonEmptyTrimmedString,
    candidate_source: SourceBoundCandidateMetadata,
    business_mssql_connection_string: NonEmptyTrimmedString,
    selection: ExecutionConnectorSelection | None = None,
    query_runner: MssqlQueryRunner | None = None,
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

    if resolved_selection.connector_id != "mssql_readonly":
        raise ExecutionConnectorSelectionError(
            deny_code=DENY_UNSUPPORTED_SOURCE_BINDING,
            message=(
                "No backend-owned execution runtime is registered for connector "
                f"'{resolved_selection.connector_id}'."
            ),
        )

    effective_query_runner = query_runner or _default_mssql_query_runner
    rows = effective_query_runner(
        connection_string=business_mssql_connection_string,
        canonical_sql=canonical_sql,
    )
    return ExecutionResult(
        source_id=resolved_selection.source_id,
        connector_id=resolved_selection.connector_id,
        ownership=resolved_selection.ownership,
        rows=rows,
    )
