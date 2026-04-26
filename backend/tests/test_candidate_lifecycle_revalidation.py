from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import PreviewCandidate, PreviewCandidateApproval, PreviewRequest
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.services.candidate_lifecycle import (
    CandidateLifecycleAuditContext,
    CandidateLifecycleRecord,
    CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY,
    CandidateLifecycleRevalidationError,
    SourceBoundCandidateMetadata,
    revalidate_authoritative_candidate_approval,
    revalidate_candidate_lifecycle,
)
from app.services.source_entitlements import SourceEntitlementError


@contextmanager
def _session_scope() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_source(
    session: Session,
    *,
    source_id: str,
    source_family: str = "postgresql",
    source_flavor: str = "warehouse",
    owner_binding: str = "group:finance-analysts",
    contract_version: int = 3,
    snapshot_version: int = 7,
    activation_posture: SourceActivationPosture = SourceActivationPosture.ACTIVE,
) -> RegisteredSource:
    source = RegisteredSource(
        id=uuid4(),
        source_id=source_id,
        display_label=f"{source_id} display",
        source_family=source_family,
        source_flavor=source_flavor,
        activation_posture=activation_posture,
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
        snapshot_version=snapshot_version,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=contract_version,
        display_name=f"{source_id} contract",
        owner_binding=owner_binding,
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()
    return source


def _candidate(
    *,
    source_id: str = "sap-approved-spend",
    source_family: str = "postgresql",
    source_flavor: str = "warehouse",
    contract_version: int = 3,
    snapshot_version: int = 7,
    execution_policy_version: int | None = None,
    connector_profile_version: int | None = None,
    approval_expires_at: datetime | None = None,
    invalidated_at: datetime | None = None,
) -> CandidateLifecycleRecord:
    now = datetime.now(timezone.utc)
    effective_execution_policy_version = (
        execution_policy_version
        if execution_policy_version is not None
        else CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY[source_family]
    )
    return CandidateLifecycleRecord(
        owner_subject_id="user:alice",
        approved_at=now - timedelta(minutes=5),
        approval_expires_at=approval_expires_at or (now + timedelta(minutes=10)),
        invalidated_at=invalidated_at,
        source=SourceBoundCandidateMetadata(
            source_id=source_id,
            source_family=source_family,
            source_flavor=source_flavor,
            dataset_contract_version=contract_version,
            schema_snapshot_version=snapshot_version,
            execution_policy_version=effective_execution_policy_version,
            connector_profile_version=connector_profile_version,
        ),
    )


def _audit_context() -> CandidateLifecycleAuditContext:
    return CandidateLifecycleAuditContext(
        event_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        request_id="request-123",
        correlation_id="correlation-123",
        user_subject="user:alice",
        session_id="session-123",
        query_candidate_id="candidate-123",
        candidate_owner_subject="user:alice",
    )


def _seed_preview_candidate_approval(
    session: Session,
    *,
    source: RegisteredSource,
    candidate_id: str = "candidate-123",
    request_id: str = "request-123",
    owner_subject_id: str = "user:alice",
    approval_expires_at: datetime | None = None,
    execution_policy_version: int | None = None,
) -> PreviewCandidateApproval:
    dataset_contract = session.get(DatasetContract, source.dataset_contract_id)
    schema_snapshot = session.get(SchemaSnapshot, source.schema_snapshot_id)
    assert dataset_contract is not None
    assert schema_snapshot is not None

    preview_request = PreviewRequest(
        id=uuid4(),
        request_id=request_id,
        registered_source_id=source.id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dataset_contract_id=dataset_contract.id,
        dataset_contract_version=dataset_contract.contract_version,
        schema_snapshot_id=schema_snapshot.id,
        schema_snapshot_version=schema_snapshot.snapshot_version,
        authenticated_subject_id=owner_subject_id,
        auth_source="test-helper",
        session_id="session-123",
        governance_bindings="group:finance-analysts",
        entitlement_decision="allow",
        request_text="Show approved spend",
        request_state="previewed",
    )
    session.add(preview_request)
    session.flush()

    preview_candidate = PreviewCandidate(
        id=uuid4(),
        candidate_id=candidate_id,
        preview_request_id=preview_request.id,
        request_id=request_id,
        registered_source_id=source.id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dataset_contract_id=dataset_contract.id,
        dataset_contract_version=dataset_contract.contract_version,
        schema_snapshot_id=schema_snapshot.id,
        schema_snapshot_version=schema_snapshot.snapshot_version,
        authenticated_subject_id=owner_subject_id,
        candidate_sql="SELECT vendor_id FROM finance.approved_vendor_spend LIMIT 50",
        guard_status="allow",
        candidate_state="preview_ready",
    )
    session.add(preview_candidate)
    session.flush()

    now = datetime.now(timezone.utc)
    approval = PreviewCandidateApproval(
        id=uuid4(),
        approval_id=f"approval-{candidate_id}",
        preview_candidate_id=preview_candidate.id,
        candidate_id=candidate_id,
        request_id=request_id,
        registered_source_id=source.id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dataset_contract_version=dataset_contract.contract_version,
        schema_snapshot_version=schema_snapshot.snapshot_version,
        execution_policy_version=(
            execution_policy_version
            if execution_policy_version is not None
            else CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY[source.source_family]
        ),
        approved_sql="SELECT vendor_id FROM finance.approved_vendor_spend LIMIT 50",
        owner_subject_id=owner_subject_id,
        session_id="session-123",
        approved_at=now,
        approval_expires_at=approval_expires_at or (now + timedelta(minutes=10)),
        approval_state="approved",
    )
    session.add(approval)
    session.commit()
    return approval


def test_revalidate_candidate_lifecycle_accepts_current_source_bound_candidate() -> None:
    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        result = revalidate_candidate_lifecycle(
            candidate=_candidate(),
            authenticated_subject=AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session=session,
            as_of=datetime.now(timezone.utc),
        )

    assert result.source_id == "sap-approved-spend"
    assert result.state == "execution_eligible"


def test_authoritative_candidate_approval_is_consumed_once_for_execution() -> None:
    with _session_scope() as session:
        source = _seed_source(session, source_id="sap-approved-spend")
        approval = _seed_preview_candidate_approval(session, source=source)

        result = revalidate_authoritative_candidate_approval(
            session=session,
            candidate_id="candidate-123",
            authenticated_subject=AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            as_of=datetime.now(timezone.utc),
            selected_source_id="sap-approved-spend",
            audit_context=_audit_context(),
        )

        assert result.state == "execution_eligible"
        session.refresh(approval)
        assert approval.approval_state == "executed"
        assert approval.executed_at is not None

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_CANDIDATE_REPLAYED",
        ) as exc_info:
            revalidate_authoritative_candidate_approval(
                session=session,
                candidate_id="candidate-123",
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                as_of=datetime.now(timezone.utc),
                selected_source_id="sap-approved-spend",
                audit_context=_audit_context(),
            )

    assert exc_info.value.deny_code == "DENY_CANDIDATE_REPLAYED"


def test_authoritative_candidate_approval_rejects_stale_persisted_execution_policy() -> None:
    with _session_scope() as session:
        source = _seed_source(session, source_id="sap-approved-spend")
        _seed_preview_candidate_approval(
            session,
            source=source,
            execution_policy_version=(
                CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY[
                    source.source_family
                ]
                - 1
            ),
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_POLICY_VERSION_STALE",
        ) as exc_info:
            revalidate_authoritative_candidate_approval(
                session=session,
                candidate_id="candidate-123",
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                as_of=datetime.now(timezone.utc),
                selected_source_id="sap-approved-spend",
                audit_context=_audit_context(),
            )

    assert exc_info.value.deny_code == "DENY_POLICY_VERSION_STALE"
    audit_event = exc_info.value.audit_event
    assert audit_event is not None
    assert audit_event.execution_policy_version == 2


def test_authoritative_candidate_approval_denial_audit_uses_persisted_owner() -> None:
    with _session_scope() as session:
        source = _seed_source(session, source_id="sap-approved-spend")
        _seed_preview_candidate_approval(
            session,
            source=source,
            owner_subject_id="user:alice",
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_SUBJECT_MISMATCH",
        ) as exc_info:
            revalidate_authoritative_candidate_approval(
                session=session,
                candidate_id="candidate-123",
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:bob",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                as_of=datetime.now(timezone.utc),
                selected_source_id="sap-approved-spend",
                audit_context=_audit_context().model_copy(
                    update={
                        "user_subject": "user:bob",
                        "candidate_owner_subject": "user:bob",
                    }
                ),
            )

    assert exc_info.value.deny_code == "DENY_SUBJECT_MISMATCH"
    audit_event = exc_info.value.audit_event
    assert audit_event is not None
    assert audit_event.user_subject == "user:bob"
    assert audit_event.candidate_owner_subject == "user:alice"


def test_revalidate_candidate_lifecycle_rejects_expired_approval() -> None:
    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_APPROVAL_EXPIRED",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(
                    approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert exc_info.value.deny_code == "DENY_APPROVAL_EXPIRED"


def test_revalidate_candidate_lifecycle_attaches_source_aware_expiry_audit_event() -> None:
    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        with pytest.raises(CandidateLifecycleRevalidationError) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(
                    approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
                audit_context=_audit_context(),
            )

    audit_event = exc_info.value.audit_event
    assert audit_event is not None
    assert {
        "event_type": "execution_denied",
        "request_id": "request-123",
        "correlation_id": "correlation-123",
        "user_subject": "user:alice",
        "session_id": "session-123",
        "query_candidate_id": "candidate-123",
        "candidate_owner_subject": "user:alice",
        "source_id": "sap-approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "primary_deny_code": "DENY_APPROVAL_EXPIRED",
        "denial_cause": "approval_expired",
    }.items() <= audit_event.model_dump(exclude_none=True).items()


def test_revalidate_candidate_lifecycle_rejects_invalidated_candidate() -> None:
    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_CANDIDATE_INVALIDATED",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(invalidated_at=datetime.now(timezone.utc)),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert exc_info.value.deny_code == "DENY_CANDIDATE_INVALIDATED"


def test_revalidate_candidate_lifecycle_attaches_source_aware_invalidation_audit_event() -> None:
    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        with pytest.raises(CandidateLifecycleRevalidationError) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(invalidated_at=datetime.now(timezone.utc)),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
                audit_context=_audit_context(),
            )

    audit_event = exc_info.value.audit_event
    assert audit_event is not None
    assert {
        "event_type": "candidate_invalidated",
        "source_id": "sap-approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "primary_deny_code": "DENY_CANDIDATE_INVALIDATED",
        "denial_cause": "candidate_invalidated",
        "candidate_state": "invalidated",
    }.items() <= audit_event.model_dump(exclude_none=True).items()


def test_revalidate_candidate_lifecycle_allows_future_dated_invalidation() -> None:
    as_of = datetime.now(timezone.utc)

    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        result = revalidate_candidate_lifecycle(
            candidate=_candidate(invalidated_at=as_of + timedelta(minutes=1)),
            authenticated_subject=AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session=session,
            as_of=as_of,
        )

    assert result.source_id == "sap-approved-spend"
    assert result.state == "execution_eligible"


def test_revalidate_candidate_lifecycle_rejects_entitlement_drift_on_bound_source() -> None:
    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")
        _seed_source(
            session,
            source_id="marketing-approved-spend",
            owner_binding="group:marketing-analysts",
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_ENTITLEMENT_CHANGED",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(source_id="sap-approved-spend"),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:marketing-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert exc_info.value.deny_code == "DENY_ENTITLEMENT_CHANGED"


def test_revalidate_candidate_lifecycle_rejects_cross_subject_candidate_owner() -> None:
    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_SUBJECT_MISMATCH",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:bob",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
                audit_context=_audit_context().model_copy(
                    update={"user_subject": "user:bob"}
                ),
            )

    assert exc_info.value.deny_code == "DENY_SUBJECT_MISMATCH"
    audit_event = exc_info.value.audit_event
    assert audit_event is not None
    assert {
        "event_type": "execution_denied",
        "user_subject": "user:bob",
        "query_candidate_id": "candidate-123",
        "candidate_owner_subject": "user:alice",
        "source_id": "sap-approved-spend",
        "source_family": "postgresql",
        "primary_deny_code": "DENY_SUBJECT_MISMATCH",
        "denial_cause": "subject_mismatch",
        "candidate_state": "denied",
    }.items() <= audit_event.model_dump(exclude_none=True).items()


def test_revalidate_candidate_lifecycle_rejects_stale_source_policy_versions() -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="sap-approved-spend",
            contract_version=4,
            snapshot_version=8,
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_POLICY_VERSION_STALE",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(contract_version=3, snapshot_version=7),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert exc_info.value.deny_code == "DENY_POLICY_VERSION_STALE"


@pytest.mark.parametrize(
    ("source_family", "source_flavor", "current_policy_version"),
    (
        ("mssql", "sqlserver", 2),
        ("postgresql", "warehouse", 3),
    ),
)
def test_revalidate_candidate_lifecycle_rejects_stale_execution_policy_version_for_each_source_family(
    source_family: str,
    source_flavor: str,
    current_policy_version: int,
) -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="sap-approved-spend",
            source_family=source_family,
            source_flavor=source_flavor,
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_POLICY_VERSION_STALE",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(
                    source_family=source_family,
                    source_flavor=source_flavor,
                    execution_policy_version=current_policy_version - 1,
                    connector_profile_version=11,
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
                audit_context=_audit_context(),
            )

    assert exc_info.value.deny_code == "DENY_POLICY_VERSION_STALE"
    audit_event = exc_info.value.audit_event
    assert audit_event is not None
    assert {
        "event_type": "execution_denied",
        "query_candidate_id": "candidate-123",
        "candidate_owner_subject": "user:alice",
        "source_id": "sap-approved-spend",
        "source_family": source_family,
        "source_flavor": source_flavor,
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": current_policy_version - 1,
        "connector_profile_version": 11,
        "primary_deny_code": "DENY_POLICY_VERSION_STALE",
        "denial_cause": "policy_stale",
        "candidate_state": "denied",
    }.items() <= audit_event.model_dump(exclude_none=True).items()


@pytest.mark.parametrize(
    ("source_family", "source_flavor", "current_policy_version"),
    (
        ("mssql", "sqlserver", 2),
        ("postgresql", "warehouse", 3),
    ),
)
def test_revalidate_candidate_lifecycle_rejects_missing_backend_policy_version_for_each_source_family(
    monkeypatch: pytest.MonkeyPatch,
    source_family: str,
    source_flavor: str,
    current_policy_version: int,
) -> None:
    monkeypatch.delitem(
        CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY,
        source_family,
    )

    with _session_scope() as session:
        _seed_source(
            session,
            source_id="sap-approved-spend",
            source_family=source_family,
            source_flavor=source_flavor,
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="No backend-owned execution policy version is configured",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(
                    source_family=source_family,
                    source_flavor=source_flavor,
                    execution_policy_version=current_policy_version,
                    connector_profile_version=11,
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
                audit_context=_audit_context(),
            )

    assert exc_info.value.deny_code == "DENY_POLICY_VERSION_STALE"
    audit_event = exc_info.value.audit_event
    assert audit_event is not None
    assert {
        "event_type": "execution_denied",
        "query_candidate_id": "candidate-123",
        "candidate_owner_subject": "user:alice",
        "source_id": "sap-approved-spend",
        "source_family": source_family,
        "source_flavor": source_flavor,
        "execution_policy_version": current_policy_version,
        "connector_profile_version": 11,
        "primary_deny_code": "DENY_POLICY_VERSION_STALE",
        "denial_cause": "policy_stale",
        "candidate_state": "denied",
    }.items() <= audit_event.model_dump(exclude_none=True).items()


def test_revalidate_candidate_lifecycle_rejects_non_executable_bound_source() -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="sap-approved-spend",
            activation_posture=SourceActivationPosture.PAUSED,
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_POLICY_VERSION_STALE",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert exc_info.value.deny_code == "DENY_POLICY_VERSION_STALE"


def test_revalidate_candidate_lifecycle_classifies_wrapped_value_error_as_stale_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_wrapped_value_error(
        authenticated_subject: AuthenticatedSubject,
        source: object,
        dataset_contract: object,
    ) -> object:
        del authenticated_subject, source, dataset_contract
        try:
            raise ValueError("Registered source posture metadata is invalid.")
        except ValueError as exc:
            raise SourceEntitlementError(str(exc)) from exc

    monkeypatch.setattr(
        "app.services.candidate_lifecycle.ensure_subject_is_entitled_for_source",
        _raise_wrapped_value_error,
    )

    with _session_scope() as session:
        _seed_source(session, source_id="sap-approved-spend")

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_POLICY_VERSION_STALE",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert exc_info.value.deny_code == "DENY_POLICY_VERSION_STALE"


def test_revalidate_candidate_lifecycle_does_not_switch_to_another_source() -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="sap-approved-spend",
            owner_binding="group:finance-analysts",
        )
        _seed_source(
            session,
            source_id="marketing-approved-spend",
            owner_binding="group:marketing-analysts",
        )

        with pytest.raises(
            CandidateLifecycleRevalidationError,
            match="DENY_SOURCE_BINDING_MISMATCH",
        ) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_candidate(source_id="sap-approved-spend"),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset(
                        {"group:finance-analysts", "group:marketing-analysts"}
                    ),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
                selected_source_id="marketing-approved-spend",
            )

    assert exc_info.value.deny_code == "DENY_SOURCE_BINDING_MISMATCH"
