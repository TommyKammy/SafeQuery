from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.services.request_preview import PreviewSubmissionRequest, submit_preview_request


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


def _seed_authoritative_source_governance(session: Session) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id="sap-approved-spend",
        display_label="SAP spend cube / approved_vendor_spend",
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=SourceActivationPosture.ACTIVE,
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
        snapshot_version=7,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=3,
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


def test_preview_candidate_carries_authoritative_source_metadata() -> None:
    with _session_scope() as session:
        _seed_authoritative_source_governance(session)

        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="sap-approved-spend",
            ),
            AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session,
        )

    candidate = response.model_dump()["candidate"]
    assert {
        "source_id": "sap-approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "state": "preview_ready",
        "candidate_sql": None,
        "guard_status": "pending",
    }.items() <= candidate.items()
    assert candidate["candidate_id"]
