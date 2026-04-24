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
from app.db.models.dataset_contract import (
    DatasetContract,
    DatasetContractDataset,
    DatasetContractDatasetKind,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.features.guard.deny_taxonomy import (
    DENY_APPROVAL_EXPIRED,
    DENY_CANDIDATE_INVALIDATED,
    DENY_POLICY_VERSION_STALE,
    DENY_SUBJECT_MISMATCH,
)
from app.services.candidate_lifecycle import (
    CandidateLifecycleRecord,
    SourceBoundCandidateMetadata,
)
from app.services.mssql_vertical_slice import (
    MSSQLVerticalSliceDenied,
    run_mssql_core_vertical_slice,
)
from app.services.postgresql_vertical_slice import (
    PostgreSQLVerticalSliceDenied,
    run_postgresql_core_vertical_slice,
)
from app.services.request_preview import PreviewAuditContext, PreviewSubmissionRequest


MSSQL_TEST_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=tcp:business-mssql-source,1433;"
    "Database=business;"
    "Uid=svc_safequery_exec;"
    "Pwd=unused-test-password;"
    "Encrypt=yes;"
    "TrustServerCertificate=no"
)
POSTGRESQL_TEST_URL = (
    "postgresql://placeholder_user:placeholder_password@business-postgres-source:5432/business"
)
APPLICATION_POSTGRESQL_TEST_URL = (
    "postgresql://placeholder_user:placeholder_password@app-postgres:5432/safequery"
)


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
    source_family: str,
    source_flavor: str,
    contract_version: int,
    snapshot_version: int,
    schema_name: str,
) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id=source_id,
        display_label=f"{source_id} display",
        source_family=source_family,
        source_flavor=source_flavor,
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
        owner_binding="group:finance-analysts",
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    session.add(
        DatasetContractDataset(
            id=uuid4(),
            dataset_contract_id=contract.id,
            schema_name=schema_name,
            dataset_name="approved_vendor_spend",
            dataset_kind=DatasetContractDatasetKind.TABLE,
        )
    )

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()


def _candidate(
    *,
    source_id: str,
    source_family: str,
    source_flavor: str,
    contract_version: int,
    snapshot_version: int,
    execution_policy_version: int,
    owner_subject_id: str = "user:alice",
    approval_expires_at: datetime | None = None,
    invalidated_at: datetime | None = None,
) -> CandidateLifecycleRecord:
    now = datetime.now(timezone.utc)
    return CandidateLifecycleRecord(
        owner_subject_id=owner_subject_id,
        approved_at=now - timedelta(minutes=5),
        approval_expires_at=approval_expires_at or (now + timedelta(minutes=10)),
        invalidated_at=invalidated_at,
        source=SourceBoundCandidateMetadata(
            source_id=source_id,
            source_family=source_family,
            source_flavor=source_flavor,
            dataset_contract_version=contract_version,
            schema_snapshot_version=snapshot_version,
            execution_policy_version=execution_policy_version,
            connector_profile_version=1,
        ),
    )


def _audit_context(*, prefix: str) -> PreviewAuditContext:
    return PreviewAuditContext(
        occurred_at=datetime.now(timezone.utc),
        request_id=f"request-{prefix}",
        correlation_id=f"correlation-{prefix}",
        user_subject="user:alice",
        session_id=f"session-{prefix}",
        query_candidate_id=f"candidate-{prefix}",
        candidate_owner_subject="user:alice",
        guard_version=f"{prefix}-guard-v1",
        application_version="safequery-test",
    )


class _MSSQLAdapter:
    def generate_sql(self, request):
        return "SELECT TOP 10 vendor_name FROM dbo.approved_vendor_spend"


class _PostgreSQLAdapter:
    def generate_sql(self, request):
        return "SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 10"


def _unexpected_query_runner(**_: object) -> list[dict[str, object]]:
    raise AssertionError("execution must not run after lifecycle revalidation denies")


def test_mssql_vertical_slice_denies_expired_candidate_before_execution() -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
            contract_version=3,
            snapshot_version=7,
            schema_name="dbo",
        )

        with pytest.raises(MSSQLVerticalSliceDenied) as exc_info:
            run_mssql_core_vertical_slice(
                payload=PreviewSubmissionRequest(
                    question="Show approved vendors.",
                    source_id="business-mssql-source",
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                sql_generation_adapter=_MSSQLAdapter(),
                business_mssql_connection_string=MSSQL_TEST_CONNECTION_STRING,
                query_runner=_unexpected_query_runner,
                audit_context=_audit_context(prefix="mssql-expired"),
                candidate_lifecycle=_candidate(
                    source_id="business-mssql-source",
                    source_family="mssql",
                    source_flavor="sqlserver",
                    contract_version=3,
                    snapshot_version=7,
                    execution_policy_version=2,
                    approval_expires_at=datetime.now(timezone.utc)
                    - timedelta(seconds=1),
                ),
            )

    denial = exc_info.value.audit_events[-1].model_dump(exclude_none=True)
    assert exc_info.value.deny_code == DENY_APPROVAL_EXPIRED
    assert {
        "event_type": "execution_denied",
        "candidate_owner_subject": "user:alice",
        "source_id": "business-mssql-source",
        "source_family": "mssql",
        "source_flavor": "sqlserver",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": 2,
        "connector_profile_version": 1,
        "primary_deny_code": DENY_APPROVAL_EXPIRED,
        "denial_cause": "approval_expired",
        "candidate_state": "denied",
    }.items() <= denial.items()


def test_mssql_vertical_slice_denies_owner_mismatch_before_execution() -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
            contract_version=3,
            snapshot_version=7,
            schema_name="dbo",
        )

        with pytest.raises(MSSQLVerticalSliceDenied) as exc_info:
            run_mssql_core_vertical_slice(
                payload=PreviewSubmissionRequest(
                    question="Show approved vendors.",
                    source_id="business-mssql-source",
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                sql_generation_adapter=_MSSQLAdapter(),
                business_mssql_connection_string=MSSQL_TEST_CONNECTION_STRING,
                query_runner=_unexpected_query_runner,
                audit_context=_audit_context(prefix="mssql-owner"),
                candidate_lifecycle=_candidate(
                    source_id="business-mssql-source",
                    source_family="mssql",
                    source_flavor="sqlserver",
                    contract_version=3,
                    snapshot_version=7,
                    execution_policy_version=2,
                    owner_subject_id="user:bob",
                ),
            )

    denial = exc_info.value.audit_events[-1].model_dump(exclude_none=True)
    assert exc_info.value.deny_code == DENY_SUBJECT_MISMATCH
    assert {
        "event_type": "execution_denied",
        "candidate_owner_subject": "user:alice",
        "source_id": "business-mssql-source",
        "primary_deny_code": DENY_SUBJECT_MISMATCH,
        "denial_cause": "subject_mismatch",
    }.items() <= denial.items()


def test_postgresql_vertical_slice_denies_invalidated_candidate_before_execution() -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="business-postgres-source",
            source_family="postgresql",
            source_flavor="warehouse",
            contract_version=4,
            snapshot_version=9,
            schema_name="finance",
        )

        with pytest.raises(PostgreSQLVerticalSliceDenied) as exc_info:
            run_postgresql_core_vertical_slice(
                payload=PreviewSubmissionRequest(
                    question="Show approved vendors.",
                    source_id="business-postgres-source",
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                sql_generation_adapter=_PostgreSQLAdapter(),
                business_postgres_url=POSTGRESQL_TEST_URL,
                application_postgres_url=APPLICATION_POSTGRESQL_TEST_URL,
                query_runner=_unexpected_query_runner,
                audit_context=_audit_context(prefix="postgres-invalidated"),
                candidate_lifecycle=_candidate(
                    source_id="business-postgres-source",
                    source_family="postgresql",
                    source_flavor="warehouse",
                    contract_version=4,
                    snapshot_version=9,
                    execution_policy_version=3,
                    invalidated_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                ),
            )

    denial = exc_info.value.audit_events[-1].model_dump(exclude_none=True)
    assert exc_info.value.deny_code == DENY_CANDIDATE_INVALIDATED
    assert {
        "event_type": "candidate_invalidated",
        "candidate_owner_subject": "user:alice",
        "source_id": "business-postgres-source",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dataset_contract_version": 4,
        "schema_snapshot_version": 9,
        "execution_policy_version": 3,
        "connector_profile_version": 1,
        "primary_deny_code": DENY_CANDIDATE_INVALIDATED,
        "denial_cause": "candidate_invalidated",
        "candidate_state": "invalidated",
    }.items() <= denial.items()


def test_postgresql_vertical_slice_denies_stale_execution_policy_before_execution() -> None:
    with _session_scope() as session:
        _seed_source(
            session,
            source_id="business-postgres-source",
            source_family="postgresql",
            source_flavor="warehouse",
            contract_version=4,
            snapshot_version=9,
            schema_name="finance",
        )

        with pytest.raises(PostgreSQLVerticalSliceDenied) as exc_info:
            run_postgresql_core_vertical_slice(
                payload=PreviewSubmissionRequest(
                    question="Show approved vendors.",
                    source_id="business-postgres-source",
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                sql_generation_adapter=_PostgreSQLAdapter(),
                business_postgres_url=POSTGRESQL_TEST_URL,
                application_postgres_url=APPLICATION_POSTGRESQL_TEST_URL,
                query_runner=_unexpected_query_runner,
                audit_context=_audit_context(prefix="postgres-stale-policy"),
                candidate_lifecycle=_candidate(
                    source_id="business-postgres-source",
                    source_family="postgresql",
                    source_flavor="warehouse",
                    contract_version=4,
                    snapshot_version=9,
                    execution_policy_version=2,
                ),
            )

    denial = exc_info.value.audit_events[-1].model_dump(exclude_none=True)
    assert exc_info.value.deny_code == DENY_POLICY_VERSION_STALE
    assert {
        "event_type": "execution_denied",
        "source_id": "business-postgres-source",
        "source_family": "postgresql",
        "primary_deny_code": DENY_POLICY_VERSION_STALE,
        "denial_cause": "policy_stale",
    }.items() <= denial.items()
