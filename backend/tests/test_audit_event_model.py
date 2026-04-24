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
