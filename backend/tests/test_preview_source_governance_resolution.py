from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionEntitlementError,
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


def _seed_authoritative_source_governance(
    session: Session,
    *,
    source_id: str = "persisted-approved-spend",
    source_posture: SourceActivationPosture = SourceActivationPosture.ACTIVE,
    snapshot_status: SchemaSnapshotReviewStatus = SchemaSnapshotReviewStatus.APPROVED,
    link_active_contract: bool = True,
    link_active_snapshot: bool = True,
    link_contract_snapshot: bool = True,
) -> RegisteredSource:
    source = RegisteredSource(
        id=uuid4(),
        source_id=source_id,
        display_label="Persisted approved spend",
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=source_posture,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference=f"vault:{source_id}",
    )
    session.add(source)
    session.flush()

    snapshot = SchemaSnapshot(
        id=uuid4(),
        registered_source_id=source.id,
        snapshot_version=1,
        review_status=snapshot_status,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    drift_snapshot = None
    if not link_contract_snapshot:
        drift_snapshot = SchemaSnapshot(
            id=uuid4(),
            registered_source_id=source.id,
            snapshot_version=2,
            review_status=SchemaSnapshotReviewStatus.APPROVED,
            reviewed_at=datetime.now(timezone.utc),
        )
        session.add(drift_snapshot)
        session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id if link_contract_snapshot else drift_snapshot.id,
        contract_version=1,
        display_name="Persisted approved spend contract",
        owner_binding="group:finance-analysts",
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    if link_active_contract:
        source.dataset_contract_id = contract.id
    if link_active_snapshot:
        source.schema_snapshot_id = snapshot.id

    session.commit()
    session.refresh(source)
    return source


def test_preview_submission_resolves_persisted_source_governance_records() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(session)

        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="persisted-approved-spend",
            ),
            AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session,
        )

    assert response.model_dump()["candidate"]["source_id"] == "persisted-approved-spend"


def test_preview_submission_emits_source_aware_lifecycle_audit_events() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(
            session,
            source_id="persisted-approved-spend",
        )

        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="persisted-approved-spend",
            ),
            AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime.now(timezone.utc),
                request_id="request-123",
                correlation_id="correlation-123",
                user_subject="user:alice",
                session_id="session-123",
                query_candidate_id="candidate-123",
                candidate_owner_subject="user:alice",
                guard_version="guard-profile-v1",
                application_version="safequery-test",
            ),
        )

    assert [event.event_type for event in response.audit.events] == [
        "query_submitted",
        "generation_requested",
        "generation_completed",
        "guard_evaluated",
    ]
    serialized_audit = response.model_dump()["audit"]
    assert [event["event_type"] for event in serialized_audit["events"]] == [
        "query_submitted",
        "generation_requested",
        "generation_completed",
        "guard_evaluated",
    ]
    for event in response.audit.events:
        assert {
            "request_id": "request-123",
            "correlation_id": "correlation-123",
            "user_subject": "user:alice",
            "session_id": "session-123",
            "source_id": "persisted-approved-spend",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
            "dataset_contract_version": 1,
            "schema_snapshot_version": 1,
            "application_version": "safequery-test",
        }.items() <= event.model_dump(exclude_none=True).items()

    guard_event = response.audit.events[-1].model_dump(exclude_none=True)
    assert {
        "event_type": "guard_evaluated",
        "query_candidate_id": "candidate-123",
        "candidate_owner_subject": "user:alice",
        "guard_version": "guard-profile-v1",
        "candidate_state": "preview_ready",
    }.items() <= guard_event.items()


def test_preview_lifecycle_audit_retains_safe_auth_context_for_entitlement_reconstruction() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(
            session,
            source_id="persisted-approved-spend",
        )

        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="persisted-approved-spend",
            ),
            AuthenticatedSubject(
                subject_id=" user:alice ",
                governance_bindings=frozenset(
                    {
                        " group:finance-analysts ",
                        "role:read-only-reviewer",
                    }
                ),
            ),
            session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime.now(timezone.utc),
                request_id="request-123",
                correlation_id="correlation-123",
                user_subject="user:stale-context",
                session_id="application-session-redacted",
                query_candidate_id="candidate-123",
                candidate_owner_subject="user:alice",
                guard_version="guard-profile-v1",
                application_version="safequery-test",
                auth_source="enterprise-bridge",
            ),
        )

    for event in response.audit.events:
        assert event.user_subject == "user:alice"
        assert event.session_id == "application-session-redacted"
        assert event.auth_source == "enterprise-bridge"
        assert event.governance_bindings == [
            "group:finance-analysts",
            "role:read-only-reviewer",
        ]
        assert event.entitlement_decision == "allow"
        assert event.entitlement_source_bindings == ["group:finance-analysts"]

    serialized = response.model_dump()
    assert "csrf" not in str(serialized).lower()
    assert "token" not in str(serialized).lower()
    assert "cookie" not in str(serialized).lower()


def test_preview_entitlement_denial_preserves_audit_safe_auth_context() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(
            session,
            source_id="persisted-approved-spend",
        )

        try:
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by quarterly spend",
                    source_id="persisted-approved-spend",
                ),
                AuthenticatedSubject(
                    subject_id="user:bob",
                    governance_bindings=frozenset({"group:unauthorized"}),
                ),
                session,
                audit_context=PreviewAuditContext(
                    occurred_at=datetime.now(timezone.utc),
                    request_id="request-123",
                    correlation_id="correlation-123",
                    user_subject="user:stale-context",
                    session_id="application-session-redacted",
                    auth_source="enterprise-bridge",
                    application_version="safequery-test",
                ),
            )
        except PreviewSubmissionEntitlementError as exc:
            audit_events = exc.audit_events
        else:
            raise AssertionError("preview submission unexpectedly accepted unauthorized subject")

    assert len(audit_events) == 1
    denial_event = audit_events[0].model_dump(exclude_none=True)
    assert {
        "event_type": "generation_failed",
        "request_id": "request-123",
        "correlation_id": "correlation-123",
        "user_subject": "user:bob",
        "session_id": "application-session-redacted",
        "auth_source": "enterprise-bridge",
        "governance_bindings": ["group:unauthorized"],
        "entitlement_decision": "deny",
        "entitlement_source_bindings": ["group:finance-analysts"],
        "primary_deny_code": "DENY_SOURCE_ENTITLEMENT",
        "denial_cause": "entitlement_denied",
        "source_id": "persisted-approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
    }.items() <= denial_event.items()
    assert "csrf" not in str(denial_event).lower()
    assert "token" not in str(denial_event).lower()
    assert "cookie" not in str(denial_event).lower()


def test_preview_submission_rejects_missing_active_contract_linkage() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(session, link_active_contract=False)

        try:
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by quarterly spend",
                    source_id="persisted-approved-spend",
                ),
                AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session,
            )
        except PreviewSubmissionContractError as exc:
            assert str(exc) == (
                "Registered source 'persisted-approved-spend' has no active dataset contract."
            )
        else:
            raise AssertionError("preview submission unexpectedly accepted missing contract linkage")


def test_preview_submission_rejects_missing_linked_schema_snapshot() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(session, link_active_snapshot=False)

        try:
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by quarterly spend",
                    source_id="persisted-approved-spend",
                ),
                AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session,
            )
        except PreviewSubmissionContractError as exc:
            assert str(exc) == (
                "Registered source 'persisted-approved-spend' has no linked schema snapshot."
            )
        else:
            raise AssertionError("preview submission unexpectedly accepted missing snapshot linkage")


def test_preview_submission_rejects_non_approved_schema_snapshot() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(
            session,
            snapshot_status=SchemaSnapshotReviewStatus.PENDING,
        )

        try:
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by quarterly spend",
                    source_id="persisted-approved-spend",
                ),
                AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session,
            )
        except PreviewSubmissionContractError as exc:
            assert str(exc) == (
                "Registered source 'persisted-approved-spend' requires an approved schema snapshot."
            )
        else:
            raise AssertionError("preview submission unexpectedly accepted a non-approved snapshot")


def test_preview_submission_rejects_contract_snapshot_drift() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(session, link_contract_snapshot=False)

        try:
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by quarterly spend",
                    source_id="persisted-approved-spend",
                ),
                AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session,
            )
        except PreviewSubmissionContractError as exc:
            assert str(exc) == (
                "Registered source 'persisted-approved-spend' is missing authoritative "
                "source-scoped governance artifacts."
            )
        else:
            raise AssertionError("preview submission unexpectedly accepted drifted contract linkage")
