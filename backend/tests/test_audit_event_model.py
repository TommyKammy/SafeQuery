from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.audit.event_model import SourceAwareAuditEvent


def _source_aware_payload() -> dict[str, object]:
    return {
        "event_id": uuid4(),
        "event_type": "guard_evaluated",
        "occurred_at": datetime.now(timezone.utc),
        "request_id": "request-123",
        "correlation_id": "correlation-123",
        "user_subject": "user:alice",
        "session_id": "session-123",
        "source_id": "sap-approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dialect_profile_version": 2,
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": 5,
        "connector_profile_version": 11,
    }


@pytest.mark.parametrize(
    "event_type",
    [
        "query_submitted",
        "generation_requested",
        "generation_completed",
        "guard_evaluated",
        "execution_requested",
        "execution_started",
        "execution_completed",
        "execution_denied",
        "request_rate_limited",
        "concurrency_rejected",
        "candidate_invalidated",
    ],
)
def test_source_aware_audit_event_accepts_relevant_lifecycle_events(
    event_type: str,
) -> None:
    payload = _source_aware_payload()
    payload["event_type"] = event_type

    event = SourceAwareAuditEvent(**payload)

    dumped = event.model_dump(exclude_none=True)
    assert dumped == payload
    assert set(SourceAwareAuditEvent.model_fields) >= {
        "source_id",
        "source_family",
        "source_flavor",
        "dialect_profile_version",
        "dataset_contract_version",
        "schema_snapshot_version",
        "execution_policy_version",
        "connector_profile_version",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", " sap-approved-spend "),
        ("source_id", "sap/approved/spend"),
        ("source_family", "mysql"),
        ("dataset_contract_version", 0),
        ("connector_profile_version", -1),
    ],
)
def test_source_aware_audit_event_rejects_invalid_source_metadata(
    field: str,
    value: object,
) -> None:
    payload = _source_aware_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        SourceAwareAuditEvent(**payload)


@pytest.mark.parametrize("field", ["source_id", "source_family"])
def test_source_aware_audit_event_rejects_missing_required_source_metadata(
    field: str,
) -> None:
    payload = _source_aware_payload()
    del payload[field]

    with pytest.raises(ValidationError):
        SourceAwareAuditEvent(**payload)


def test_retrieval_completed_audit_event_preserves_source_labeled_citations() -> None:
    payload = _source_aware_payload()
    payload.update(
        {
            "event_type": "retrieval_completed",
            "retrieval_corpus_version": "source-aware-v1",
            "retrieved_asset_ids": ["metric_definition", "metric_definition"],
            "retrieved_citations": [
                {
                    "asset_id": "metric_definition",
                    "asset_kind": "metric_definition",
                    "citation_label": "business-mssql-source metric definition",
                    "source_id": "business-mssql-source",
                    "source_family": "mssql",
                    "source_flavor": "sqlserver-2022",
                    "dataset_contract_version": 7,
                    "schema_snapshot_version": 3,
                    "authority": "advisory_context",
                    "can_authorize_execution": False,
                },
                {
                    "asset_id": "metric_definition",
                    "asset_kind": "metric_definition",
                    "citation_label": "business-postgres-source metric definition",
                    "source_id": "business-postgres-source",
                    "source_family": "postgresql",
                    "source_flavor": "postgresql-16",
                    "dataset_contract_version": 2,
                    "schema_snapshot_version": 5,
                    "authority": "advisory_context",
                    "can_authorize_execution": False,
                },
            ],
        }
    )

    event = SourceAwareAuditEvent(**payload)

    assert event.model_dump()["retrieved_citations"] == payload["retrieved_citations"]


def test_analyst_response_audit_event_keeps_executed_evidence_separate_from_citations() -> None:
    payload = _source_aware_payload()
    execution_audit_event_id = uuid4()
    payload.update(
        {
            "event_type": "analyst_response_rendered",
            "retrieved_citations": [
                {
                    "asset_id": "metric_definition",
                    "asset_kind": "metric_definition",
                    "citation_label": "business-postgres-source metric definition",
                    "source_id": "business-postgres-source",
                    "source_family": "postgresql",
                    "source_flavor": "postgresql-16",
                    "dataset_contract_version": 2,
                    "schema_snapshot_version": 5,
                    "authority": "advisory_context",
                    "can_authorize_execution": False,
                }
            ],
            "executed_evidence": [
                {
                    "type": "executed_evidence",
                    "source_id": "business-postgres-source",
                    "source_family": "postgresql",
                    "source_flavor": "warehouse",
                    "dataset_contract_version": 2,
                    "schema_snapshot_version": 5,
                    "execution_policy_version": 3,
                    "connector_profile_version": 11,
                    "candidate_id": "candidate-123",
                    "execution_audit_event_id": execution_audit_event_id,
                    "execution_audit_event_type": "execution_completed",
                    "row_count": 12,
                    "result_truncated": False,
                    "authority": "backend_execution_result",
                    "can_authorize_execution": False,
                }
            ],
        }
    )

    event = SourceAwareAuditEvent(**payload)
    dumped = event.model_dump()

    assert dumped["retrieved_citations"][0]["authority"] == "advisory_context"
    assert dumped["executed_evidence"][0]["type"] == "executed_evidence"
    assert dumped["executed_evidence"][0]["authority"] == "backend_execution_result"
    assert "citation_label" not in dumped["executed_evidence"][0]
    assert "rows" not in dumped["executed_evidence"][0]


@pytest.mark.parametrize(
    ("authority", "can_authorize_execution"),
    [
        ("execution_evidence", False),
        ("advisory_context", True),
    ],
)
def test_retrieval_citation_audit_payload_rejects_execution_authority(
    authority: str,
    can_authorize_execution: bool,
) -> None:
    payload = _source_aware_payload()
    payload.update(
        {
            "event_type": "retrieval_completed",
            "retrieved_citations": [
                {
                    "asset_id": "metric_definition",
                    "asset_kind": "metric_definition",
                    "citation_label": "business-mssql-source metric definition",
                    "source_id": "business-mssql-source",
                    "source_family": "mssql",
                    "source_flavor": "sqlserver-2022",
                    "dataset_contract_version": 7,
                    "schema_snapshot_version": 3,
                    "authority": authority,
                    "can_authorize_execution": can_authorize_execution,
                },
            ],
        }
    )

    with pytest.raises(ValidationError):
        SourceAwareAuditEvent(**payload)


def test_executed_evidence_rejects_retrieval_citation_shape() -> None:
    payload = _source_aware_payload()
    payload.update(
        {
            "event_type": "analyst_response_rendered",
            "executed_evidence": [
                {
                    "type": "retrieval_citation",
                    "asset_id": "metric_definition",
                    "asset_kind": "metric_definition",
                    "citation_label": "business-postgres-source metric definition",
                    "source_id": "business-postgres-source",
                    "source_family": "postgresql",
                    "dataset_contract_version": 2,
                    "schema_snapshot_version": 5,
                    "candidate_id": "candidate-123",
                    "execution_audit_event_id": uuid4(),
                    "row_count": 12,
                    "result_truncated": False,
                    "authority": "advisory_context",
                    "can_authorize_execution": False,
                }
            ],
        }
    )

    with pytest.raises(ValidationError):
        SourceAwareAuditEvent(**payload)
