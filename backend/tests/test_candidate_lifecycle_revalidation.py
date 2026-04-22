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
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.services.candidate_lifecycle import (
    CandidateLifecycleRecord,
    CandidateLifecycleRevalidationError,
    SourceBoundCandidateMetadata,
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
    owner_binding: str = "group:finance-analysts",
    contract_version: int = 3,
    snapshot_version: int = 7,
    activation_posture: SourceActivationPosture = SourceActivationPosture.ACTIVE,
) -> RegisteredSource:
    source = RegisteredSource(
        id=uuid4(),
        source_id=source_id,
        display_label=f"{source_id} display",
        source_family="postgresql",
        source_flavor="warehouse",
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
    contract_version: int = 3,
    snapshot_version: int = 7,
    approval_expires_at: datetime | None = None,
    invalidated_at: datetime | None = None,
) -> CandidateLifecycleRecord:
    now = datetime.now(timezone.utc)
    return CandidateLifecycleRecord(
        owner_subject_id="user:alice",
        approved_at=now - timedelta(minutes=5),
        approval_expires_at=approval_expires_at or (now + timedelta(minutes=10)),
        invalidated_at=invalidated_at,
        source=SourceBoundCandidateMetadata(
            source_id=source_id,
            source_family="postgresql",
            source_flavor="warehouse",
            dataset_contract_version=contract_version,
            schema_snapshot_version=snapshot_version,
        ),
    )


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
            match="DENY_ENTITLEMENT_CHANGED",
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

    assert exc_info.value.deny_code == "DENY_ENTITLEMENT_CHANGED"
