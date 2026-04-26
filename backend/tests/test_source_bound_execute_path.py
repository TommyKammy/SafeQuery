from __future__ import annotations

from datetime import datetime, timezone
import inspect
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.guard.deny_taxonomy import (
    DENY_RUNTIME_RATE_LIMIT,
    DENY_SOURCE_BINDING_MISMATCH,
    DENY_UNSUPPORTED_SOURCE_BINDING,
)
from app.features.execution.runtime import (
    ExecutableCandidateRecord,
    ExecutionAuditContext,
    ExecutionResult,
    ExecutionRuntimeSafetyState,
)
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


def _unsupported_flavor_candidate() -> ExecutableCandidateRecord:
    return ExecutableCandidateRecord(
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
        source=SourceBoundCandidateMetadata(
            source_id="approved-spend",
            source_family="postgresql",
            source_flavor="analytics",
            dataset_contract_version=3,
            schema_snapshot_version=7,
        ),
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


def _anchored_audit_context(previous_event_id) -> ExecutionAuditContext:
    context = _audit_context()
    return context.model_copy(update={"causation_event_id": previous_event_id})


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


def test_execute_candidate_sql_attaches_audit_events_to_selection_denials() -> None:
    from app.features.execution import (
        ExecutionConnectorSelectionError,
        execute_candidate_sql,
    )

    with pytest.raises(
        ExecutionConnectorSelectionError,
        match="No backend-owned execution connector is registered",
    ) as exc_info:
        execute_candidate_sql(
            candidate=_unsupported_flavor_candidate(),
            selection=ExecutionConnectorSelection(
                source_id="approved-spend",
                source_family="postgresql",
                source_flavor="analytics",
                connector_id="postgresql_readonly",
                ownership="backend",
            ),
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            audit_context=_audit_context(),
        )

    assert exc_info.value.deny_code == DENY_UNSUPPORTED_SOURCE_BINDING
    assert exc_info.value.audit_event is not None
    assert [event.event_type for event in exc_info.value.audit_events] == [
        "execution_requested",
        "execution_denied",
    ]
    assert {
        "event_type": "execution_denied",
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "analytics",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "primary_deny_code": DENY_UNSUPPORTED_SOURCE_BINDING,
        "denial_cause": "unsupported_source_binding",
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
    assert result.metadata.model_dump(exclude_none=True) == {
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "candidate_id": "candidate-123",
        "execution_run_id": result.audit_event.event_id,
        "row_count": 1,
        "row_limit": 200,
        "payload_bytes": 24,
        "payload_limit_bytes": 65536,
        "result_truncated": False,
    }
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


@pytest.mark.parametrize(
    (
        "source_id",
        "source_family",
        "source_flavor",
        "connector_id",
        "execution_kwargs",
    ),
    [
        (
            "approved-spend",
            "postgresql",
            "warehouse",
            "postgresql_readonly",
            {
                "business_postgres_url": BUSINESS_POSTGRES_URL,
                "application_postgres_url": APPLICATION_POSTGRES_URL,
            },
        ),
        (
            "orders-ledger",
            "mssql",
            "sqlserver",
            "mssql_readonly",
            {
                "business_mssql_connection_string": (
                    "Driver={ODBC Driver 18 for SQL Server};"
                    "Server=business-mssql-source;"
                    "Database=orders;"
                    "Authentication=ActiveDirectoryMsi;"
                ),
            },
        ),
    ],
)
def test_execute_candidate_sql_derives_source_labeled_executed_evidence(
    source_id: str,
    source_family: str,
    source_flavor: str,
    connector_id: str,
    execution_kwargs: dict[str, str],
) -> None:
    from app.features.execution import execute_candidate_sql

    candidate = ExecutableCandidateRecord(
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
        source=SourceBoundCandidateMetadata(
            source_id=source_id,
            source_family=source_family,
            source_flavor=source_flavor,
            dataset_contract_version=3,
            schema_snapshot_version=7,
        ),
    )
    selection = ExecutionConnectorSelection(
        source_id=source_id,
        source_family=source_family,
        source_flavor=source_flavor,
        connector_id=connector_id,
        ownership="backend",
    )
    result = execute_candidate_sql(
        candidate=candidate,
        selection=selection,
        query_runner=lambda **_: [{"vendor_name": "Acme"}],
        audit_context=_audit_context(),
        **execution_kwargs,
    )

    assert result.executed_evidence is not None
    assert result.executed_evidence.model_dump(exclude_none=True) == {
        "type": "executed_evidence",
        "source_id": source_id,
        "source_family": source_family,
        "source_flavor": source_flavor,
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "connector_profile_version": 11,
        "candidate_id": "candidate-123",
        "execution_audit_event_id": result.audit_event.event_id,
        "execution_audit_event_type": "execution_completed",
        "row_count": 1,
        "result_truncated": False,
        "authority": "backend_execution_result",
        "can_authorize_execution": False,
    }
    assert "retrieved_citations" not in result.executed_evidence.model_dump(
        exclude_none=True
    )
    assert "rows" not in result.executed_evidence.model_dump(exclude_none=True)


def test_execution_result_omits_executed_evidence_for_negative_audit_row_count() -> None:
    from app.features.execution import execute_candidate_sql

    result = execute_candidate_sql(
        candidate=_candidate(),
        selection=_selection(),
        query_runner=lambda **_: [{"vendor_name": "Acme"}],
        audit_context=_audit_context(),
        business_postgres_url=BUSINESS_POSTGRES_URL,
        application_postgres_url=APPLICATION_POSTGRES_URL,
    )

    assert result.audit_event is not None
    result._audit_event = result.audit_event.model_copy(
        update={"execution_row_count": -1}
    )

    assert result.executed_evidence is None


def test_execution_result_rejects_client_supplied_executed_evidence() -> None:
    with pytest.raises(ValidationError):
        ExecutionResult(
            source_id="approved-spend",
            connector_id="postgresql_readonly",
            ownership="backend",
            rows=[],
            executed_evidence={
                "type": "executed_evidence",
                "source_id": "approved-spend",
                "source_family": "postgresql",
                "dataset_contract_version": 3,
                "schema_snapshot_version": 7,
                "candidate_id": "candidate-123",
                "execution_audit_event_id": uuid4(),
                "row_count": 0,
                "result_truncated": False,
                "authority": "backend_execution_result",
                "can_authorize_execution": False,
            },
        )


def test_execute_candidate_sql_returns_source_aware_runtime_denial_audit_event() -> None:
    from app.features.execution import (
        ExecutionConnectorExecutionError,
        execute_candidate_sql,
    )

    with pytest.raises(ExecutionConnectorExecutionError) as exc_info:
        execute_candidate_sql(
            candidate=_candidate(),
            selection=_selection(),
            business_postgres_url=BUSINESS_POSTGRES_URL,
            application_postgres_url=APPLICATION_POSTGRES_URL,
            query_runner=lambda **_: [{"vendor_name": "Acme"}],
            runtime_safety_state=ExecutionRuntimeSafetyState(
                rate_limited_source_ids=frozenset({"approved-spend"})
            ),
            audit_context=_audit_context(),
        )

    assert exc_info.value.deny_code == DENY_RUNTIME_RATE_LIMIT
    assert [event.event_type for event in exc_info.value.audit_events] == [
        "execution_requested",
        "execution_denied",
    ]
    assert {
        "event_type": "execution_denied",
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "primary_deny_code": DENY_RUNTIME_RATE_LIMIT,
        "denial_cause": "runtime_rate_limit",
        "candidate_state": "denied",
    }.items() <= exc_info.value.audit_event.model_dump(exclude_none=True).items()
    assert exc_info.value.audit_event.model_dump(exclude_none=True).get("rows") is None


def test_execute_candidate_sql_anchors_first_audit_event_to_previous_event() -> None:
    from app.features.execution import execute_candidate_sql

    previous_event_id = uuid4()

    result = execute_candidate_sql(
        candidate=_candidate(),
        selection=_selection(),
        business_postgres_url=BUSINESS_POSTGRES_URL,
        application_postgres_url=APPLICATION_POSTGRES_URL,
        query_runner=lambda **_: [{"vendor_name": "Acme"}],
        audit_context=_anchored_audit_context(previous_event_id),
    )

    assert [event.event_type for event in result.audit_events] == [
        "execution_requested",
        "execution_started",
        "execution_completed",
    ]
    assert result.audit_events[0].causation_event_id == previous_event_id
    assert result.audit_events[1].causation_event_id == result.audit_events[0].event_id
    assert result.audit_events[2].causation_event_id == result.audit_events[1].event_id
