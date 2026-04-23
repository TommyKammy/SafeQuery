from __future__ import annotations

from datetime import datetime, timezone
import inspect
from uuid import uuid4

import pytest

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.guard.deny_taxonomy import DENY_SOURCE_BINDING_MISMATCH
from app.features.execution.runtime import ExecutableCandidateRecord, ExecutionAuditContext
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


APPLICATION_POSTGRES_URL = "postgresql://safequery:safequery@app-postgres:5432/safequery"
BUSINESS_POSTGRES_URL = (
    "postgresql://safequery_exec:super-secret@business-postgres-source:5432/business"
)


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


def _audit_context() -> ExecutionAuditContext:
    return ExecutionAuditContext(
        event_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        request_id="request-123",
        correlation_id="correlation-123",
        user_subject="user:alice",
        session_id="session-123",
        query_candidate_id="candidate-123",
        candidate_owner_subject="user:alice",
        connector_profile_version=11,
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
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            audit_context=_audit_context(),
        )

    assert exc_info.value.deny_code == DENY_SOURCE_BINDING_MISMATCH
    assert exc_info.value.audit_event is not None
    assert [event.event_type for event in exc_info.value.audit_events] == [
        "execution_requested",
        "execution_denied",
    ]
    assert {
        "event_type": "execution_denied",
        "request_id": "request-123",
        "correlation_id": "correlation-123",
        "user_subject": "user:alice",
        "session_id": "session-123",
        "query_candidate_id": "candidate-123",
        "candidate_owner_subject": "user:alice",
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "connector_profile_version": 11,
        "primary_deny_code": DENY_SOURCE_BINDING_MISMATCH,
        "denial_cause": "source_binding_mismatch",
    }.items() <= exc_info.value.audit_event.model_dump(exclude_none=True).items()


def test_execute_candidate_sql_returns_source_aware_completion_audit_event() -> None:
    from app.features.execution import execute_candidate_sql

    result = execute_candidate_sql(
        candidate=_candidate(),
        selection=_selection(),
        business_postgres_url=BUSINESS_POSTGRES_URL,
        application_postgres_url=APPLICATION_POSTGRES_URL,
        query_runner=lambda **_: [{"vendor_name": "Acme"}],
        audit_context=_audit_context(),
    )

    assert result.audit_event is not None
    assert [event.event_type for event in result.audit_events] == [
        "execution_requested",
        "execution_started",
        "execution_completed",
    ]
    assert {
        "event_type": "execution_completed",
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "connector_profile_version": 11,
        "execution_row_count": 1,
        "result_truncated": False,
    }.items() <= result.audit_event.model_dump(exclude_none=True).items()
    assert result.audit_event.model_dump(exclude_none=True).get("rows") is None
