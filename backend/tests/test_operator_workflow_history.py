from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import PreviewAuditEvent
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.services.operator_workflow import (
    _latest_candidate_events,
    _latest_request_events,
    get_operator_workflow_snapshot,
)
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionRequest,
    submit_preview_request,
)


@contextmanager
def _session_scope() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed_authoritative_source_governance(
    session: Session,
    *,
    source_posture: SourceActivationPosture = SourceActivationPosture.ACTIVE,
) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id="sap-approved-spend",
        display_label="SAP spend cube / approved_vendor_spend",
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=source_posture,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference="vault:sap-approved-spend",
    )
    session.add(source)
    session.flush()

    snapshot = SchemaSnapshot(
        id=uuid4(),
        registered_source_id=source.id,
        snapshot_version=1,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=1,
        display_name="SAP spend cube contract",
        owner_binding="group:finance-analysts",
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()


def _audit_context(*, request_id: str, candidate_id: str | None = None) -> PreviewAuditContext:
    return PreviewAuditContext(
        occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        request_id=request_id,
        correlation_id=f"{request_id}-correlation",
        user_subject="user:alice",
        session_id=f"{request_id}-session",
        query_candidate_id=candidate_id,
        candidate_owner_subject="user:alice" if candidate_id is not None else None,
        auth_source="test-helper",
    )


def _audit_event(
    *,
    event_id: UUID,
    lifecycle_order: int,
    event_type: str,
    request_id: str = "preview-request-234",
    candidate_id: str | None = None,
) -> PreviewAuditEvent:
    return PreviewAuditEvent(
        event_id=event_id,
        lifecycle_order=lifecycle_order,
        preview_request_id=uuid4(),
        preview_candidate_id=uuid4() if candidate_id is not None else None,
        request_id=request_id,
        candidate_id=candidate_id,
        event_type=event_type,
        occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        correlation_id=f"{request_id}-correlation",
        authenticated_subject_id="user:alice",
        session_id=f"{request_id}-session",
        source_id="sap-approved-spend",
        source_family="postgresql",
        source_flavor="warehouse",
        audit_payload={"event_type": event_type},
    )


def test_latest_audit_event_selection_uses_lifecycle_order_when_timestamps_tie() -> None:
    submitted = _audit_event(
        event_id=UUID("00000000-0000-4000-8000-000000000001"),
        lifecycle_order=1,
        event_type="query_submitted",
    )
    completed = _audit_event(
        event_id=UUID("00000000-0000-4000-8000-000000000002"),
        lifecycle_order=3,
        event_type="generation_completed",
        candidate_id="preview-candidate-234",
    )
    evaluated = _audit_event(
        event_id=UUID("00000000-0000-4000-8000-000000000003"),
        lifecycle_order=4,
        event_type="guard_evaluated",
        candidate_id="preview-candidate-234",
    )

    assert (
        _latest_request_events([submitted, completed, evaluated])["preview-request-234"]
        is evaluated
    )
    assert (
        _latest_candidate_events([completed, evaluated])["preview-candidate-234"]
        is evaluated
    )


def test_latest_audit_event_selection_uses_event_id_when_lifecycle_order_ties() -> None:
    lower_event_id = _audit_event(
        event_id=UUID("00000000-0000-4000-8000-000000000001"),
        lifecycle_order=4,
        event_type="guard_evaluated",
        candidate_id="preview-candidate-234",
    )
    higher_event_id = _audit_event(
        event_id=UUID("00000000-0000-4000-8000-000000000002"),
        lifecycle_order=4,
        event_type="guard_evaluated_retry",
        candidate_id="preview-candidate-234",
    )

    assert (
        _latest_request_events([lower_event_id, higher_event_id])[
            "preview-request-234"
        ]
        is higher_event_id
    )
    assert (
        _latest_candidate_events([lower_event_id, higher_event_id])[
            "preview-candidate-234"
        ]
        is higher_event_id
    )


def test_operator_workflow_history_is_built_from_preview_request_and_candidate_records() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(session)

        submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="sap-approved-spend",
            ),
            AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session,
            audit_context=_audit_context(
                request_id="preview-request-234",
                candidate_id="preview-candidate-234",
            ),
        )

        snapshot = get_operator_workflow_snapshot(session)

    history = [
        item.model_dump(mode="json", by_alias=True, exclude_none=True)
        for item in snapshot.history
    ]
    assert history == [
        {
            "itemType": "candidate",
            "recordId": "preview-candidate-234",
            "label": "Show approved vendors by quarterly spend",
            "sourceId": "sap-approved-spend",
            "sourceLabel": "SAP spend cube / approved_vendor_spend",
            "lifecycleState": "preview_ready",
            "occurredAt": "2026-01-02T03:04:05Z",
            "guardStatus": "pending",
        },
        {
            "itemType": "request",
            "recordId": "preview-request-234",
            "label": "Show approved vendors by quarterly spend",
            "sourceId": "sap-approved-spend",
            "sourceLabel": "SAP spend cube / approved_vendor_spend",
            "lifecycleState": "previewed",
            "occurredAt": "2026-01-02T03:04:05Z",
        },
    ]


def test_operator_workflow_history_includes_audit_safe_unavailable_preview_denials() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(
            session,
            source_posture=SourceActivationPosture.PAUSED,
        )

        with pytest.raises(PreviewSubmissionContractError):
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by quarterly spend",
                    source_id="sap-approved-spend",
                ),
                AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session,
                audit_context=_audit_context(request_id="preview-request-denied-234"),
            )

        snapshot = get_operator_workflow_snapshot(session)

    history = [
        item.model_dump(mode="json", by_alias=True, exclude_none=True)
        for item in snapshot.history
    ]
    assert history == [
        {
            "itemType": "request",
            "recordId": "preview-request-denied-234",
            "label": "Show approved vendors by quarterly spend",
            "sourceId": "sap-approved-spend",
            "sourceLabel": "SAP spend cube / approved_vendor_spend",
            "lifecycleState": "preview_unavailable",
            "occurredAt": "2026-01-02T03:04:05Z",
        }
    ]
    serialized_history = str(history).lower()
    assert "csrf" not in serialized_history
    assert "cookie" not in serialized_history
    assert "token" not in serialized_history
    assert "secret" not in serialized_history
