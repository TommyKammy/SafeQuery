from __future__ import annotations

import sys
from typing import Any

import pytest

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.execution.runtime import (
    DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY,
    DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY,
    ExecutableCandidateRecord,
    ExecutionConnectorExecutionError,
    ExecutionRuntimeCancelledError,
    ExecutionRuntimeSafetyState,
    ExecutionRuntimeControls,
    _default_mssql_query_runner,
)
from app.features.guard.deny_taxonomy import (
    DENY_RUNTIME_CONCURRENCY_LIMIT,
    DENY_RUNTIME_KILL_SWITCH,
    DENY_RUNTIME_RATE_LIMIT,
)
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


APPLICATION_POSTGRES_URL = "postgresql://safequery:safequery@app-postgres:5432/safequery"
BUSINESS_POSTGRES_URL = (
    "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
)


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


def _candidate(
    *,
    canonical_sql: str,
    source_id: str,
    source_family: str,
    source_flavor: str | None,
) -> ExecutableCandidateRecord:
    return ExecutableCandidateRecord(
        canonical_sql=canonical_sql,
        source=_candidate_source(
            source_id=source_id,
            source_family=source_family,
            source_flavor=source_flavor,
        ),
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
        candidate=_candidate(
            canonical_sql="SELECT TOP 1 vendor_name FROM dbo.approved_vendor_spend",
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
        candidate=_candidate(
            canonical_sql=(
                "SELECT vendor_name FROM finance.approved_vendor_spend "
                "ORDER BY approved_spend DESC LIMIT 1"
            ),
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
        business_postgres_url=BUSINESS_POSTGRES_URL,
        application_postgres_url=APPLICATION_POSTGRES_URL,
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
        match=r"Execution canceled before the backend-owned query runner started\.",
    ):
        execute_candidate_sql(
            candidate=_candidate(
                canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
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
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            query_runner=fake_query_runner,
            cancellation_probe=lambda: True,
        )


def test_execute_candidate_sql_caps_rows_to_source_bound_maximum() -> None:
    from app.features.execution import execute_candidate_sql

    result = execute_candidate_sql(
        candidate=_candidate(
            canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend",
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
        business_postgres_url=BUSINESS_POSTGRES_URL,
        application_postgres_url=APPLICATION_POSTGRES_URL,
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


def test_execute_candidate_sql_denies_source_kill_switch_before_runner() -> None:
    from app.features.execution import execute_candidate_sql

    def fake_query_runner(*, database_url: str, canonical_sql: str) -> list[dict[str, Any]]:
        raise AssertionError("query runner should not run when source is disabled")

    with pytest.raises(ExecutionConnectorExecutionError) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(
                canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
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
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            query_runner=fake_query_runner,
            runtime_safety_state=ExecutionRuntimeSafetyState(
                disabled_source_ids=frozenset({"approved-spend"})
            ),
        )

    assert exc_info.value.deny_code == DENY_RUNTIME_KILL_SWITCH


def test_execute_candidate_sql_denies_source_rate_limit_before_runner() -> None:
    from app.features.execution import execute_candidate_sql

    with pytest.raises(ExecutionConnectorExecutionError) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(
                canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
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
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            query_runner=lambda **_: [{"vendor_name": "Acme"}],
            runtime_safety_state=ExecutionRuntimeSafetyState(
                rate_limited_source_ids=frozenset({"approved-spend"})
            ),
        )

    assert exc_info.value.deny_code == DENY_RUNTIME_RATE_LIMIT


def test_execute_candidate_sql_keeps_rate_limits_source_specific() -> None:
    from app.features.execution import execute_candidate_sql

    result = execute_candidate_sql(
        candidate=_candidate(
            canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
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
        business_postgres_url=BUSINESS_POSTGRES_URL,
        application_postgres_url=APPLICATION_POSTGRES_URL,
        query_runner=lambda **_: [{"vendor_name": "Acme"}],
        runtime_safety_state=ExecutionRuntimeSafetyState(
            rate_limited_source_ids=frozenset({"marketing-spend"})
        ),
    )

    assert result.rows == [{"vendor_name": "Acme"}]


def test_execute_candidate_sql_denies_source_concurrency_limit_before_runner() -> None:
    from app.features.execution import execute_candidate_sql

    with pytest.raises(ExecutionConnectorExecutionError) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(
                canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
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
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            query_runner=lambda **_: [{"vendor_name": "Acme"}],
            runtime_safety_state=ExecutionRuntimeSafetyState(
                active_executions_by_source_id={"approved-spend": 1},
                max_concurrent_executions_by_source_id={"approved-spend": 1},
            ),
        )

    assert exc_info.value.deny_code == DENY_RUNTIME_CONCURRENCY_LIMIT


def test_default_mssql_query_runner_requires_timeout_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCursor:
        pass

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

        def cursor(self) -> FakeCursor:
            return FakeCursor()

    class FakePyodbcModule:
        @staticmethod
        def drivers() -> list[str]:
            return ["ODBC Driver 18 for SQL Server"]

        @staticmethod
        def connect(connection_string: str) -> FakeConnection:
            assert connection_string == "Driver={ODBC Driver 18 for SQL Server};Server=tcp:test"
            return FakeConnection()

    monkeypatch.setitem(sys.modules, "pyodbc", FakePyodbcModule())

    with pytest.raises(
        RuntimeError,
        match=(
            r"The MSSQL execution connector requires cursor timeout support to "
            r"enforce backend-owned runtime controls\."
        ),
    ):
        _default_mssql_query_runner(
            connection_string="Driver={ODBC Driver 18 for SQL Server};Server=tcp:test",
            canonical_sql="SELECT 1",
            runtime_controls=ExecutionRuntimeControls(
                source_family="mssql",
                timeout_seconds=30,
                max_rows=200,
            ),
        )


def test_default_mssql_query_runner_preserves_cancelled_error_when_cancel_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCursor:
        def __init__(self) -> None:
            self.timeout: int | None = None

    class FakeConnection:
        def __init__(self) -> None:
            self.cancel_calls = 0
            self._cursor = FakeCursor()

        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

        def cursor(self) -> FakeCursor:
            return self._cursor

        def cancel(self) -> None:
            self.cancel_calls += 1
            raise RuntimeError("driver cancellation failure")

    connection = FakeConnection()

    class FakePyodbcModule:
        @staticmethod
        def drivers() -> list[str]:
            return ["ODBC Driver 18 for SQL Server"]

        @staticmethod
        def connect(connection_string: str) -> FakeConnection:
            assert connection_string == "Driver={ODBC Driver 18 for SQL Server};Server=tcp:test"
            return connection

    monkeypatch.setitem(sys.modules, "pyodbc", FakePyodbcModule())

    with pytest.raises(
        ExecutionRuntimeCancelledError,
        match=r"Execution canceled before the MSSQL query started\.",
    ):
        _default_mssql_query_runner(
            connection_string="Driver={ODBC Driver 18 for SQL Server};Server=tcp:test",
            canonical_sql="SELECT 1",
            runtime_controls=ExecutionRuntimeControls(
                source_family="mssql",
                timeout_seconds=17,
                max_rows=200,
                cancellation_probe=lambda: True,
            ),
        )

    assert connection.cancel_calls == 1
    assert connection._cursor.timeout == 17
