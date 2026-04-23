from __future__ import annotations

from typing import Any

import pytest

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.execution.runtime import (
    DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY,
    DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY,
)
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


def _candidate_source(
    *,
    source_id: str,
    source_family: str,
    source_flavor: str | None,
) -> SourceBoundCandidateMetadata:
    return SourceBoundCandidateMetadata(
        source_id=source_id,
        source_family=source_family,
        source_flavor=source_flavor,
        dataset_contract_version=3,
        schema_snapshot_version=7,
    )


def _selection(
    *,
    source_id: str,
    source_family: str,
    source_flavor: str | None,
    connector_id: str,
) -> ExecutionConnectorSelection:
    return ExecutionConnectorSelection(
        source_id=source_id,
        source_family=source_family,
        source_flavor=source_flavor,
        connector_id=connector_id,
        ownership="backend",
    )


def test_execute_candidate_sql_passes_source_aware_controls_to_mssql_runner() -> None:
    from app.features.execution import execute_candidate_sql

    captured: dict[str, Any] = {}

    def fake_query_runner(
        *,
        connection_string: str,
        canonical_sql: str,
        runtime_controls: Any,
    ) -> list[dict[str, Any]]:
        captured["connection_string"] = connection_string
        captured["canonical_sql"] = canonical_sql
        captured["runtime_controls"] = runtime_controls
        return [{"vendor_name": "Northwind"}]

    execute_candidate_sql(
        canonical_sql="SELECT TOP 1 vendor_name FROM dbo.approved_vendor_spend",
        candidate_source=_candidate_source(
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
        ),
        selection=_selection(
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
            connector_id="mssql_readonly",
        ),
        business_mssql_connection_string=(
            "Driver={ODBC Driver 18 for SQL Server};"
            "Server=tcp:business-mssql-source,1433;"
            "Database=business;"
            "Uid=svc_safequery_exec;"
            "Pwd=super-secret;"
            "Encrypt=yes;"
            "TrustServerCertificate=no"
        ),
        query_runner=fake_query_runner,
    )

    runtime_controls = captured["runtime_controls"]
    assert runtime_controls.source_family == "mssql"
    assert runtime_controls.timeout_seconds == DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY["mssql"]
    assert runtime_controls.max_rows == DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY["mssql"]


def test_execute_candidate_sql_passes_source_aware_controls_to_postgresql_runner() -> None:
    from app.features.execution import execute_candidate_sql

    captured: dict[str, Any] = {}

    def fake_query_runner(
        *,
        database_url: str,
        canonical_sql: str,
        runtime_controls: Any,
    ) -> list[dict[str, Any]]:
        captured["database_url"] = database_url
        captured["canonical_sql"] = canonical_sql
        captured["runtime_controls"] = runtime_controls
        return [{"vendor_name": "Northwind"}]

    execute_candidate_sql(
        canonical_sql=(
            "SELECT vendor_name FROM finance.approved_vendor_spend "
            "ORDER BY approved_spend DESC LIMIT 1"
        ),
        candidate_source=_candidate_source(
            source_id="approved-spend",
            source_family="postgresql",
            source_flavor="warehouse",
        ),
        selection=_selection(
            source_id="approved-spend",
            source_family="postgresql",
            source_flavor="warehouse",
            connector_id="postgresql_readonly",
        ),
        business_postgres_url=(
            "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
        ),
        query_runner=fake_query_runner,
    )

    runtime_controls = captured["runtime_controls"]
    assert runtime_controls.source_family == "postgresql"
    assert runtime_controls.timeout_seconds == DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY["postgresql"]
    assert runtime_controls.max_rows == DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY["postgresql"]


def test_execute_candidate_sql_blocks_pre_cancelled_execution_fail_closed() -> None:
    from app.features.execution import (
        ExecutionRuntimeCancelledError,
        execute_candidate_sql,
    )

    def fake_query_runner(*, database_url: str, canonical_sql: str) -> list[dict[str, Any]]:
        raise AssertionError("query runner should not run after cancellation")

    with pytest.raises(
        ExecutionRuntimeCancelledError,
        match="Execution canceled before the backend-owned query runner started.",
    ):
        execute_candidate_sql(
            canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
            candidate_source=_candidate_source(
                source_id="approved-spend",
                source_family="postgresql",
                source_flavor="warehouse",
            ),
            selection=_selection(
                source_id="approved-spend",
                source_family="postgresql",
                source_flavor="warehouse",
                connector_id="postgresql_readonly",
            ),
            business_postgres_url=(
                "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
            ),
            query_runner=fake_query_runner,
            cancellation_probe=lambda: True,
        )


def test_execute_candidate_sql_caps_rows_to_source_bound_maximum() -> None:
    from app.features.execution import execute_candidate_sql

    result = execute_candidate_sql(
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend",
        candidate_source=_candidate_source(
            source_id="approved-spend",
            source_family="postgresql",
            source_flavor="warehouse",
        ),
        selection=_selection(
            source_id="approved-spend",
            source_family="postgresql",
            source_flavor="warehouse",
            connector_id="postgresql_readonly",
        ),
        business_postgres_url=(
            "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
        ),
        query_runner=lambda *, database_url, canonical_sql: [
            {"row_number": row_number}
            for row_number in range(
                DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY["postgresql"] + 25
            )
        ],
    )

    assert len(result.rows) == DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY["postgresql"]
    assert result.rows[0] == {"row_number": 0}
    assert result.rows[-1] == {
        "row_number": DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY["postgresql"] - 1
    }
