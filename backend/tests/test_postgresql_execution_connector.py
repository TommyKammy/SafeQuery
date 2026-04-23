from __future__ import annotations

import builtins
from typing import Any

import pytest

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.guard.deny_taxonomy import DENY_SOURCE_BINDING_MISMATCH
from app.features.execution.runtime import _default_postgresql_query_runner
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


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
        canonical_sql=(
            "SELECT vendor_name, approved_spend "
            "FROM finance.approved_vendor_spend "
            "ORDER BY approved_spend DESC LIMIT 1"
        ),
        candidate_source=_candidate_source(),
        business_postgres_url=(
            "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
        ),
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
    }
    assert captured == {
        "database_url": (
            "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
        ),
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
            canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
            candidate_source=_candidate_source(),
            selection=_selection(source_id="other-source"),
            business_postgres_url=(
                "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
            ),
        )

    assert exc_info.value.deny_code == DENY_SOURCE_BINDING_MISMATCH


def test_default_postgresql_query_runner_requires_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "psycopg":
            raise ModuleNotFoundError("No module named 'psycopg'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(
        RuntimeError,
        match="psycopg must be installed before the PostgreSQL execution connector can run.",
    ):
        _default_postgresql_query_runner(
            database_url="postgresql://business-postgres-source:5432/business",
            canonical_sql="SELECT 1",
        )
