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
from app.features.audit.event_model import SourceAwareAuditEvent
from app.services.operator_workflow import (
    _latest_candidate_events,
    _latest_request_events,
    get_operator_workflow_snapshot,
)
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionRequest,
    persist_execution_audit_events,
    submit_preview_request,
)
from app.services.source_governance import (
    SourceGovernanceResolutionError,
    resolve_authoritative_source_governance,
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


def _seed_source_with_governance_state(
    session: Session,
    *,
    source_id: str,
    owner_binding: str | None,
    security_review_binding: str | None = None,
    contract_version: int = 1,
    linked_contract_version: int | None = None,
    drift_contract_snapshot: bool = False,
) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id=source_id,
        display_label=source_id.replace("-", " ").title(),
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=SourceActivationPosture.ACTIVE,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference=f"vault:{source_id}",
    )
    session.add(source)
    session.flush()

    active_snapshot = SchemaSnapshot(
        id=uuid4(),
        registered_source_id=source.id,
        snapshot_version=1,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(active_snapshot)
    session.flush()

    contract_snapshot = active_snapshot
    if drift_contract_snapshot:
        contract_snapshot = SchemaSnapshot(
            id=uuid4(),
            registered_source_id=source.id,
            snapshot_version=2,
            review_status=SchemaSnapshotReviewStatus.APPROVED,
            reviewed_at=datetime.now(timezone.utc),
        )
        session.add(contract_snapshot)
        session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=contract_snapshot.id,
        contract_version=linked_contract_version or contract_version,
        display_name=f"{source_id} contract",
        owner_binding=owner_binding,
        security_review_binding=security_review_binding,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    if linked_contract_version is not None:
        latest_contract = DatasetContract(
            id=uuid4(),
            registered_source_id=source.id,
            schema_snapshot_id=active_snapshot.id,
            contract_version=contract_version,
            display_name=f"{source_id} latest contract",
            owner_binding=owner_binding,
            security_review_binding=security_review_binding,
            exception_policy_binding=None,
        )
        session.add(latest_contract)
        session.flush()

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = active_snapshot.id
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


def _execution_audit_event(
    *,
    event_id: UUID,
    event_type: str,
    occurred_at: datetime,
    executed_evidence: list[dict[str, object]] | None = None,
    retrieved_citations: list[dict[str, object]] | None = None,
    result_truncated: bool | None = None,
    row_count: int | None = None,
) -> SourceAwareAuditEvent:
    return SourceAwareAuditEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        request_id="preview-request-234",
        correlation_id="preview-request-234-correlation",
        user_subject="user:alice",
        session_id="preview-request-234-session",
        query_candidate_id="preview-candidate-234",
        candidate_owner_subject="user:alice",
        source_id="sap-approved-spend",
        source_family="postgresql",
        source_flavor="warehouse",
        dataset_contract_version=1,
        schema_snapshot_version=1,
        retrieved_citations=retrieved_citations,
        executed_evidence=executed_evidence,
        execution_row_count=row_count,
        result_truncated=result_truncated,
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
    assert {
        "itemType": "candidate",
        "recordId": "preview-candidate-234",
        "label": "Show approved vendors by quarterly spend",
        "sourceId": "sap-approved-spend",
        "sourceLabel": "SAP spend cube / approved_vendor_spend",
        "lifecycleState": "preview_ready",
        "occurredAt": "2026-01-02T03:04:05Z",
        "requestId": "preview-request-234",
        "guardStatus": "pending",
    }.items() <= history[0].items()
    assert {
        "itemType": "request",
        "recordId": "preview-request-234",
        "label": "Show approved vendors by quarterly spend",
        "sourceId": "sap-approved-spend",
        "sourceLabel": "SAP spend cube / approved_vendor_spend",
        "lifecycleState": "previewed",
        "occurredAt": "2026-01-02T03:04:05Z",
    }.items() <= history[1].items()
    assert history[0]["auditEvents"][0]["eventType"] == "guard_evaluated"
    assert history[0]["auditEvents"][0]["candidateId"] == "preview-candidate-234"
    assert history[1]["auditEvents"][0]["eventType"] == "guard_evaluated"


def test_operator_workflow_history_includes_execution_run_records() -> None:
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
        persist_execution_audit_events(
            session,
            candidate_id="preview-candidate-234",
            audit_events=[
                _execution_audit_event(
                    event_id=UUID("00000000-0000-4000-8000-000000000010"),
                    event_type="execution_requested",
                    occurred_at=datetime(2026, 1, 2, 3, 5, 1, tzinfo=timezone.utc),
                ),
                _execution_audit_event(
                    event_id=UUID("00000000-0000-4000-8000-000000000011"),
                    event_type="execution_started",
                    occurred_at=datetime(2026, 1, 2, 3, 5, 2, tzinfo=timezone.utc),
                ),
                _execution_audit_event(
                    event_id=UUID("00000000-0000-4000-8000-000000000012"),
                    event_type="execution_completed",
                    occurred_at=datetime(2026, 1, 2, 3, 5, 3, tzinfo=timezone.utc),
                    row_count=0,
                    result_truncated=False,
                ),
            ],
        )

        snapshot = get_operator_workflow_snapshot(session)

    history = [
        item.model_dump(mode="json", by_alias=True, exclude_none=True)
        for item in snapshot.history
    ]
    assert {
        "itemType": "run",
        "recordId": "00000000-0000-4000-8000-000000000012",
        "label": "Show approved vendors by quarterly spend",
        "sourceId": "sap-approved-spend",
        "sourceLabel": "SAP spend cube / approved_vendor_spend",
        "lifecycleState": "empty",
        "occurredAt": "2026-01-02T03:05:03Z",
        "requestId": "preview-request-234",
        "resultTruncated": False,
        "rowCount": 0,
        "runState": "empty",
    }.items() <= history[0].items()
    assert history[0]["auditEvents"] == [
        {
            "eventId": "00000000-0000-4000-8000-000000000012",
            "eventType": "execution_completed",
            "occurredAt": "2026-01-02T03:05:03Z",
            "requestId": "preview-request-234",
            "candidateId": "preview-candidate-234",
            "sourceId": "sap-approved-spend",
            "rowCount": 0,
            "resultTruncated": False,
        }
    ]


def test_operator_workflow_history_surfaces_safe_audit_evidence_and_citations() -> None:
    execution_event_id = UUID("00000000-0000-4000-8000-000000000012")
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
        persist_execution_audit_events(
            session,
            candidate_id="preview-candidate-234",
            audit_events=[
                _execution_audit_event(
                    event_id=execution_event_id,
                    event_type="execution_completed",
                    occurred_at=datetime(2026, 1, 2, 3, 5, 3, tzinfo=timezone.utc),
                    retrieved_citations=[
                        {
                            "asset_id": "spend-metric-definition",
                            "asset_kind": "metric_definition",
                            "citation_label": "Approved spend metric definition",
                            "source_id": "sap-approved-spend",
                            "source_family": "postgresql",
                            "source_flavor": "warehouse",
                            "dataset_contract_version": 1,
                            "schema_snapshot_version": 1,
                            "authority": "advisory_context",
                            "can_authorize_execution": False,
                        }
                    ],
                    executed_evidence=[
                        {
                            "type": "executed_evidence",
                            "source_id": "sap-approved-spend",
                            "source_family": "postgresql",
                            "source_flavor": "warehouse",
                            "dataset_contract_version": 1,
                            "schema_snapshot_version": 1,
                            "candidate_id": "preview-candidate-234",
                            "execution_audit_event_id": str(execution_event_id),
                            "execution_audit_event_type": "execution_completed",
                            "row_count": 12,
                            "result_truncated": False,
                            "authority": "backend_execution_result",
                            "can_authorize_execution": False,
                        }
                    ],
                    row_count=12,
                    result_truncated=False,
                ),
            ],
        )

        snapshot = get_operator_workflow_snapshot(session)

    run = snapshot.history[0].model_dump(mode="json", by_alias=True, exclude_none=True)
    assert run["auditEvents"] == [
        {
            "eventId": str(execution_event_id),
            "eventType": "execution_completed",
            "occurredAt": "2026-01-02T03:05:03Z",
            "requestId": "preview-request-234",
            "candidateId": "preview-candidate-234",
            "sourceId": "sap-approved-spend",
            "rowCount": 12,
            "resultTruncated": False,
        }
    ]
    assert run["executedEvidence"] == [
        {
            "authority": "backend_execution_result",
            "canAuthorizeExecution": False,
            "candidateId": "preview-candidate-234",
            "executionAuditEventId": str(execution_event_id),
            "executionAuditEventType": "execution_completed",
            "rowCount": 12,
            "resultTruncated": False,
            "sourceId": "sap-approved-spend",
            "sourceFamily": "postgresql",
            "sourceFlavor": "warehouse",
            "datasetContractVersion": 1,
            "schemaSnapshotVersion": 1,
        }
    ]
    assert run["retrievedCitations"] == [
        {
            "assetId": "spend-metric-definition",
            "assetKind": "metric_definition",
            "authority": "advisory_context",
            "canAuthorizeExecution": False,
            "citationLabel": "Approved spend metric definition",
            "sourceId": "sap-approved-spend",
            "sourceFamily": "postgresql",
            "sourceFlavor": "warehouse",
            "datasetContractVersion": 1,
            "schemaSnapshotVersion": 1,
        }
    ]
    serialized_run = str(run).lower()
    assert "session" not in serialized_run
    assert "secret" not in serialized_run
    assert "token" not in serialized_run


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
    assert {
        "itemType": "request",
        "recordId": "preview-request-denied-234",
        "label": "Show approved vendors by quarterly spend",
        "sourceId": "sap-approved-spend",
        "sourceLabel": "SAP spend cube / approved_vendor_spend",
        "lifecycleState": "preview_unavailable",
        "occurredAt": "2026-01-02T03:04:05Z",
    }.items() <= history[0].items()
    assert history[0]["auditEvents"][0]["eventType"] == "generation_failed"
    assert history[0]["auditEvents"][0]["primaryDenyCode"] == "DENY_SOURCE_UNAVAILABLE"
    serialized_history = str(history).lower()
    assert "csrf" not in serialized_history
    assert "cookie" not in serialized_history
    assert "token" not in serialized_history
    assert "secret" not in serialized_history


def test_operator_workflow_sources_surface_sanitized_governance_binding_states() -> None:
    with _session_scope() as session:
        _seed_source_with_governance_state(
            session,
            source_id="valid-source",
            owner_binding="group:finance-analysts",
        )
        _seed_source_with_governance_state(
            session,
            source_id="missing-source",
            owner_binding=None,
        )
        _seed_source_with_governance_state(
            session,
            source_id="ambiguous-source",
            owner_binding="group:finance-analysts",
            security_review_binding="group:finance-analysts",
        )
        _seed_source_with_governance_state(
            session,
            source_id="stale-source",
            owner_binding="group:finance-analysts",
            contract_version=2,
            linked_contract_version=1,
        )
        _seed_source_with_governance_state(
            session,
            source_id="drifted-source",
            owner_binding="group:finance-analysts",
            drift_contract_snapshot=True,
        )

        snapshot = get_operator_workflow_snapshot(session)

    payload = snapshot.model_dump(mode="json", by_alias=True)
    states_by_source = {
        source["sourceId"]: {
            binding["role"]: binding["state"]
            for binding in source["governanceBindings"]
        }
        for source in payload["sources"]
    }
    assert states_by_source["valid-source"]["owner"] == "valid"
    assert states_by_source["missing-source"]["owner"] == "missing"
    assert states_by_source["ambiguous-source"]["owner"] == "ambiguous"
    assert states_by_source["stale-source"]["owner"] == "stale"
    assert states_by_source["drifted-source"]["owner"] == "drifted"

    owner_binding = next(
        binding
        for source in payload["sources"]
        if source["sourceId"] == "stale-source"
        for binding in source["governanceBindings"]
        if binding["role"] == "owner"
    )
    assert owner_binding["affectsEntitlement"] is True
    serialized = str(payload).lower()
    assert "group:finance-analysts" not in serialized
    assert "token" not in serialized
    assert "secret" not in serialized


def test_source_governance_resolution_fails_closed_on_stale_contract_linkage() -> None:
    with _session_scope() as session:
        _seed_source_with_governance_state(
            session,
            source_id="stale-source",
            owner_binding="group:finance-analysts",
            contract_version=2,
            linked_contract_version=1,
        )

        with pytest.raises(SourceGovernanceResolutionError, match="stale"):
            resolve_authoritative_source_governance(
                session,
                source_id="stale-source",
            )
