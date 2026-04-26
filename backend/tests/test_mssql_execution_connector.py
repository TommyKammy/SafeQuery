from __future__ import annotations

import sys
from typing import Any

import pytest

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.guard.deny_taxonomy import DENY_SOURCE_BINDING_MISMATCH
from app.features.execution.runtime import ExecutableCandidateRecord
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


def _candidate_source(
    *,
    source_id: str = "business-mssql-source",
    source_family: str = "mssql",
    source_flavor: str | None = "sqlserver",
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
    source_id: str = "business-mssql-source",
    source_family: str = "mssql",
    source_flavor: str | None = "sqlserver",
    connector_id: str = "mssql_readonly",
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
    source_id: str = "business-mssql-source",
    source_family: str = "mssql",
    source_flavor: str | None = "sqlserver",
) -> ExecutableCandidateRecord:
    return ExecutableCandidateRecord(
        canonical_sql=canonical_sql,
        source=_candidate_source(
            source_id=source_id,
            source_family=source_family,
            source_flavor=source_flavor,
        ),
    )


def test_execute_mssql_connector_uses_backend_owned_connection_path() -> None:
    from app.features.execution import execute_candidate_sql

    captured: dict[str, Any] = {}

    def fake_query_runner(*, connection_string: str, canonical_sql: str) -> list[dict[str, Any]]:
        captured["connection_string"] = connection_string
        captured["canonical_sql"] = canonical_sql
        return [
            {
                "vendor_name": "Northwind",
                "approved_spend": 4200,
            }
        ]

    result = execute_candidate_sql(
        candidate=_candidate(
            canonical_sql="SELECT TOP 1 vendor_name, approved_spend FROM dbo.approved_vendor_spend"
        ),
        selection=_selection(),
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

    assert result.model_dump() == {
        "source_id": "business-mssql-source",
        "connector_id": "mssql_readonly",
        "ownership": "backend",
        "rows": [
            {
                "vendor_name": "Northwind",
                "approved_spend": 4200,
            }
        ],
    }
    assert captured == {
        "connection_string": (
            "Driver={ODBC Driver 18 for SQL Server};"
            "Server=tcp:business-mssql-source,1433;"
            "Database=business;"
            "Uid=svc_safequery_exec;"
            "Pwd=super-secret;"
            "Encrypt=yes;"
            "TrustServerCertificate=no"
        ),
        "canonical_sql": "SELECT TOP 1 vendor_name, approved_spend FROM dbo.approved_vendor_spend",
    }


def test_execute_mssql_connector_rejects_selection_binding_mismatch_fail_closed() -> None:
    from app.features.execution import (
        ExecutionConnectorExecutionError,
        execute_candidate_sql,
    )

    with pytest.raises(
        ExecutionConnectorExecutionError,
        match="candidate-bound source metadata does not match the selected connector binding",
    ) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(
                canonical_sql="SELECT TOP 1 vendor_name FROM dbo.approved_vendor_spend"
            ),
            selection=_selection(source_id="other-source"),
            business_mssql_connection_string=(
                "Driver={ODBC Driver 18 for SQL Server};"
                "Server=tcp:business-mssql-source,1433;"
                "Database=business;"
                "Uid=svc_safequery_exec;"
                "Pwd=super-secret;"
                "Encrypt=yes;"
                "TrustServerCertificate=no"
            ),
        )

    assert exc_info.value.deny_code == DENY_SOURCE_BINDING_MISMATCH


def test_mssql_runtime_readiness_fails_closed_when_pyodbc_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.execution.runtime import (
        MSSQLExecutionRuntimeUnavailable,
        check_mssql_execution_runtime_readiness,
    )

    monkeypatch.setitem(sys.modules, "pyodbc", None)

    with pytest.raises(
        MSSQLExecutionRuntimeUnavailable,
        match=(
            "pyodbc must be installed and importable before the MSSQL execution "
            "connector can run"
        ),
    ):
        check_mssql_execution_runtime_readiness()


def test_mssql_runtime_readiness_fails_closed_when_pyodbc_import_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.features.execution.runtime as runtime_module

    def broken_pyodbc_import(module_name: str) -> object:
        assert module_name == "pyodbc"
        raise ImportError("libodbc.so.2: cannot open shared object file")

    monkeypatch.setattr(runtime_module.importlib, "import_module", broken_pyodbc_import)

    with pytest.raises(
        runtime_module.MSSQLExecutionRuntimeUnavailable,
        match=(
            "pyodbc must be installed and importable before the MSSQL execution "
            "connector can run"
        ),
    ) as exc_info:
        runtime_module.check_mssql_execution_runtime_readiness()

    assert isinstance(exc_info.value.__cause__, ImportError)


def test_mssql_runtime_readiness_requires_odbc_driver_18(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.execution.runtime import (
        MSSQLExecutionRuntimeUnavailable,
        check_mssql_execution_runtime_readiness,
    )

    class FakePyodbcModule:
        @staticmethod
        def drivers() -> list[str]:
            return ["PostgreSQL Unicode"]

    monkeypatch.setitem(sys.modules, "pyodbc", FakePyodbcModule())

    with pytest.raises(
        MSSQLExecutionRuntimeUnavailable,
        match="ODBC Driver 18 for SQL Server must be installed",
    ):
        check_mssql_execution_runtime_readiness()
