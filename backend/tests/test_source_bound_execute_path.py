from __future__ import annotations

import inspect

import pytest

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.guard.deny_taxonomy import DENY_SOURCE_BINDING_MISMATCH
from app.features.execution.runtime import ExecutableCandidateRecord
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


def _candidate_source() -> SourceBoundCandidateMetadata:
    return SourceBoundCandidateMetadata(
        source_id="approved-spend",
        source_family="postgresql",
        source_flavor="warehouse",
        dataset_contract_version=3,
        schema_snapshot_version=7,
    )


def _selection(
    *,
    connector_id: str = "postgresql_readonly",
) -> ExecutionConnectorSelection:
    return ExecutionConnectorSelection(
        source_id="approved-spend",
        source_family="postgresql",
        source_flavor="warehouse",
        connector_id=connector_id,
        ownership="backend",
    )


def _candidate() -> ExecutableCandidateRecord:
    return ExecutableCandidateRecord(
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
        source=_candidate_source(),
    )


def test_execute_candidate_sql_requires_candidate_bound_record() -> None:
    from app.features.execution import execute_candidate_sql

    signature = inspect.signature(execute_candidate_sql)

    selection_parameter = signature.parameters["selection"]
    candidate_parameter = signature.parameters["candidate"]

    assert "canonical_sql" not in signature.parameters
    assert "candidate_source" not in signature.parameters
    assert candidate_parameter.default is inspect._empty
    assert candidate_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert selection_parameter.default is inspect._empty
    assert selection_parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_execute_candidate_sql_rejects_connector_swaps_on_bound_source() -> None:
    from app.features.execution import (
        ExecutionConnectorExecutionError,
        execute_candidate_sql,
    )

    with pytest.raises(
        ExecutionConnectorExecutionError,
        match="candidate-bound source metadata does not match the selected connector binding",
    ) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(),
            selection=_selection(connector_id="postgresql_readonly_shadow"),
            business_postgres_url=(
                "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
            ),
        )

    assert exc_info.value.deny_code == DENY_SOURCE_BINDING_MISMATCH
