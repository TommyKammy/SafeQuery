from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource
from app.features.auth.context import AuthenticatedSubject
from app.features.guard.deny_taxonomy import (
    DENY_APPROVAL_EXPIRED,
    DENY_CANDIDATE_INVALIDATED,
    DENY_EXTERNAL_DATA_ACCESS,
    DENY_POLICY_VERSION_STALE,
    DENY_WRITE_OPERATION,
    EXECUTION_DENY_CODES,
    GUARD_DENY_CODES,
)
from app.features.guard.sql_guard import (
    evaluate_mssql_sql_guard,
    evaluate_postgresql_sql_guard,
)
from app.services.candidate_lifecycle import (
    CandidateLifecycleRecord,
    CandidateLifecycleRevalidationError,
    SourceBoundCandidateMetadata,
    revalidate_candidate_lifecycle,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_source(session: Session, *, source_id: str) -> None:
    source = RegisteredSource(
        source_id=source_id,
        display_label=f"{source_id} display",
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture="active",
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
        registered_source_id=source.id,
        snapshot_version=7,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=3,
        display_name=f"{source_id} contract",
        owner_binding="group:finance-analysts",
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()


def _candidate(
    *,
    approval_expires_at: datetime | None = None,
    invalidated_at: datetime | None = None,
    contract_version: int = 3,
) -> CandidateLifecycleRecord:
    now = datetime.now(timezone.utc)
    return CandidateLifecycleRecord(
        owner_subject_id="user:alice",
        approved_at=now - timedelta(minutes=5),
        approval_expires_at=approval_expires_at or (now + timedelta(minutes=10)),
        invalidated_at=invalidated_at,
        source=SourceBoundCandidateMetadata(
            source_id="sap-approved-spend",
            source_family="postgresql",
            source_flavor="warehouse",
            dataset_contract_version=contract_version,
            schema_snapshot_version=7,
            execution_policy_version=3,
        ),
    )


def test_guard_deny_taxonomy_uses_shared_machine_readable_codes() -> None:
    mssql_result = evaluate_mssql_sql_guard(
        {
            "canonical_sql": "SELECT * FROM OPENQUERY(remote, 'SELECT 1')",
            "source": {
                "source_id": "business-mssql-source",
                "source_family": "mssql",
                "source_flavor": "sqlserver",
            },
        }
    )
    postgresql_result = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": (
                "WITH archived AS (DELETE FROM finance.approved_vendor_spend RETURNING 1) "
                "SELECT * FROM archived"
            ),
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert mssql_result.rejections[0].code == DENY_EXTERNAL_DATA_ACCESS
    assert postgresql_result.rejections[0].code == DENY_WRITE_OPERATION
    assert mssql_result.rejections[0].code in GUARD_DENY_CODES
    assert postgresql_result.rejections[0].code in GUARD_DENY_CODES


@pytest.mark.parametrize(
    ("candidate", "expected_code"),
    (
        (
            _candidate(
                approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
            ),
            DENY_APPROVAL_EXPIRED,
        ),
        (
            _candidate(invalidated_at=datetime.now(timezone.utc)),
            DENY_CANDIDATE_INVALIDATED,
        ),
        (
            _candidate(contract_version=2),
            DENY_POLICY_VERSION_STALE,
        ),
    ),
)
def test_execute_time_revalidation_uses_shared_machine_readable_codes(
    candidate: CandidateLifecycleRecord,
    expected_code: str,
) -> None:
    with _session() as session:
        _seed_source(session, source_id="sap-approved-spend")

        with pytest.raises(CandidateLifecycleRevalidationError) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=candidate,
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert exc_info.value.deny_code == expected_code
    assert exc_info.value.deny_code in EXECUTION_DENY_CODES
