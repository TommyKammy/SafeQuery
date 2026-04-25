from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract, DatasetContractDataset
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.services.demo_source_seed import DEMO_SOURCE_ID, seed_demo_source_governance
from app.services.operator_workflow import get_operator_workflow_snapshot
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


def test_demo_source_seed_creates_preview_governance_records() -> None:
    with _session_scope() as session:
        result = seed_demo_source_governance(session)

        source = session.scalar(
            select(RegisteredSource).where(RegisteredSource.source_id == DEMO_SOURCE_ID)
        )
        contract = session.scalar(
            select(DatasetContract).where(DatasetContract.id == source.dataset_contract_id)
        )
        snapshot = session.scalar(
            select(SchemaSnapshot).where(SchemaSnapshot.id == source.schema_snapshot_id)
        )

        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id=DEMO_SOURCE_ID,
            ),
            AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session,
        )

    assert result.created is True
    assert source is not None
    assert source.display_label == "Demo business PostgreSQL"
    assert source.activation_posture == SourceActivationPosture.ACTIVE
    assert source.source_family == "postgresql"
    assert source.source_flavor == "demo"
    assert source.connection_reference == "env:SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL"
    assert contract is not None
    assert contract.contract_version == 1
    assert contract.owner_binding == "group:finance-analysts"
    assert snapshot is not None
    assert snapshot.review_status == SchemaSnapshotReviewStatus.APPROVED
    assert response.candidate.source_id == DEMO_SOURCE_ID
    assert response.candidate.dataset_contract_version == 1
    assert response.candidate.schema_snapshot_version == 1


def test_demo_source_seed_is_idempotent_and_visible_to_operator_workflow() -> None:
    with _session_scope() as session:
        first = seed_demo_source_governance(session)
        second = seed_demo_source_governance(session)

        sources = session.scalars(select(RegisteredSource)).all()
        contracts = session.scalars(select(DatasetContract)).all()
        snapshots = session.scalars(select(SchemaSnapshot)).all()
        datasets = session.scalars(select(DatasetContractDataset)).all()
        workflow = get_operator_workflow_snapshot(session)

    assert first.created is True
    assert second.created is False
    assert len(sources) == 1
    assert len(contracts) == 1
    assert len(snapshots) == 1
    assert len(datasets) == 2
    assert [source.source_id for source in workflow.sources] == [DEMO_SOURCE_ID]
    assert workflow.sources[0].activation_posture == "active"
    assert workflow.sources[0].source_family == "postgresql"
    assert workflow.sources[0].source_flavor == "demo"
