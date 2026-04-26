from __future__ import annotations

import builtins
from typing import Any

import pytest

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.guard.deny_taxonomy import (
    DENY_APPLICATION_POSTGRES_REUSE,
    DENY_SOURCE_BINDING_MISMATCH,
)
from app.features.execution.runtime import (
    ExecutableCandidateRecord,
    ExecutionRuntimeControls,
    _default_postgresql_query_runner,
)
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


APPLICATION_POSTGRES_URL = "postgresql://safequery:safequery@app-postgres:5432/safequery"
BUSINESS_POSTGRES_URL = (
    "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
)


def _candidate_source(
    *,
    source_id: str = "approved-spend",
    source_family: str = "postgresql",
    source_flavor: str | None = "warehouse",
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
    source_id: str = "approved-spend",
    source_family: str = "postgresql",
    source_flavor: str | None = "warehouse",
    connector_id: str = "postgresql_readonly",
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
    source_id: str = "approved-spend",
    source_family: str = "postgresql",
    source_flavor: str | None = "warehouse",
) -> ExecutableCandidateRecord:
    return ExecutableCandidateRecord(
        canonical_sql=canonical_sql,
        source=_candidate_source(
            source_id=source_id,
            source_family=source_family,
            source_flavor=source_flavor,
        ),
    )


def test_execute_postgresql_connector_uses_backend_owned_connection_path() -> None:
    from app.features.execution import execute_candidate_sql

    captured: dict[str, Any] = {}

    def fake_query_runner(*, database_url: str, canonical_sql: str) -> list[dict[str, Any]]:
        captured["database_url"] = database_url
        captured["canonical_sql"] = canonical_sql
        return [
            {
                "vendor_name": "Northwind",
                "approved_spend": 4200,
            }
        ]

    result = execute_candidate_sql(
        candidate=_candidate(
            canonical_sql=(
                "SELECT vendor_name, approved_spend "
                "FROM finance.approved_vendor_spend "
                "ORDER BY approved_spend DESC LIMIT 1"
            )
        ),
        selection=_selection(),
        business_postgres_url=BUSINESS_POSTGRES_URL,
        application_postgres_url=APPLICATION_POSTGRES_URL,
        query_runner=fake_query_runner,
    )

    assert result.model_dump() == {
        "source_id": "approved-spend",
        "connector_id": "postgresql_readonly",
        "ownership": "backend",
        "rows": [
            {
                "vendor_name": "Northwind",
                "approved_spend": 4200,
            }
        ],
        "metadata": {
            "source_id": "approved-spend",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
            "candidate_id": None,
            "execution_run_id": None,
            "row_count": 1,
            "row_limit": 200,
            "payload_bytes": 51,
            "payload_limit_bytes": 65536,
            "result_truncated": False,
            "truncation_reason": None,
        },
    }
    assert captured == {
        "database_url": BUSINESS_POSTGRES_URL,
        "canonical_sql": (
            "SELECT vendor_name, approved_spend "
            "FROM finance.approved_vendor_spend "
            "ORDER BY approved_spend DESC LIMIT 1"
        ),
    }


def test_execute_postgresql_connector_rejects_selection_binding_mismatch_fail_closed() -> None:
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
                canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"
            ),
            selection=_selection(source_id="other-source"),
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
        )

    assert exc_info.value.deny_code == DENY_SOURCE_BINDING_MISMATCH


def test_execute_postgresql_connector_rejects_application_postgres_reuse_before_query() -> None:
    from app.features.execution import (
        ExecutionConnectorExecutionError,
        execute_candidate_sql,
    )

    def fake_query_runner(*, database_url: str, canonical_sql: str) -> list[dict[str, Any]]:
        raise AssertionError("query runner must not run for application PostgreSQL reuse")

    with pytest.raises(
        ExecutionConnectorExecutionError,
        match="must not reuse the application PostgreSQL connection identity",
    ) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(
                canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"
            ),
            selection=_selection(),
            business_postgres_url=APPLICATION_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            query_runner=fake_query_runner,
        )

    assert exc_info.value.deny_code == DENY_APPLICATION_POSTGRES_REUSE


def test_execute_postgresql_connector_rejects_equivalent_application_endpoint_contract() -> None:
    from app.features.execution import (
        ExecutionConnectorExecutionError,
        execute_candidate_sql,
    )

    def fake_query_runner(*, database_url: str, canonical_sql: str) -> list[dict[str, Any]]:
        raise AssertionError("query runner must not run for application PostgreSQL reuse")

    with pytest.raises(
        ExecutionConnectorExecutionError,
        match="must not target the application PostgreSQL endpoint contract",
    ) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(
                canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"
            ),
            selection=_selection(),
            business_postgres_url=(
                "postgresql://safequery_exec:super-secret@app-postgres/safequery"
            ),
            application_postgres_url=APPLICATION_POSTGRES_URL,
            query_runner=fake_query_runner,
        )

    assert exc_info.value.deny_code == DENY_APPLICATION_POSTGRES_REUSE


def test_default_postgresql_query_runner_requires_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globalns: dict[str, Any] | None = None,
        localns: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "psycopg":
            raise ModuleNotFoundError("No module named 'psycopg'")
        return real_import(name, globalns, localns, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(
        RuntimeError,
        match=r"psycopg must be installed before the PostgreSQL execution connector can run\.",
    ):
        _default_postgresql_query_runner(
            database_url="postgresql://business-postgres-source:5432/business",
            canonical_sql="SELECT 1",
            runtime_controls=ExecutionRuntimeControls(
                source_family="postgresql",
                timeout_seconds=30,
                max_rows=200,
            ),
        )
