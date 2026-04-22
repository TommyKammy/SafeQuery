from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

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
from app.services.generation_context import (
    GenerationContextPreparationError,
    prepare_generation_context,
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


def _seed_source_governance(
    session: Session,
    *,
    source_id: str,
    owner_binding: str = "group:finance-analysts",
    link_active_contract: bool = True,
) -> RegisteredSource:
    source = RegisteredSource(
        id=uuid4(),
        source_id=source_id,
        display_label=f"{source_id} display",
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
        display_name=f"{source_id} contract",
        owner_binding=owner_binding,
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    session.add_all(
        [
            DatasetContractDataset(
                id=uuid4(),
                dataset_contract_id=contract.id,
                schema_name="finance",
                dataset_name=f"{source_id}_spend",
                dataset_kind=DatasetContractDatasetKind.TABLE,
            ),
            DatasetContractDataset(
                id=uuid4(),
                dataset_contract_id=contract.id,
                schema_name="analytics",
                dataset_name=f"{source_id}_summary",
                dataset_kind=DatasetContractDatasetKind.VIEW,
            ),
        ]
    )

    if link_active_contract:
        source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id

    session.commit()
    session.refresh(source)
    return source


def test_prepare_generation_context_uses_only_selected_source_governance() -> None:
    with _session_scope() as session:
        selected_source = _seed_source_governance(
            session,
            source_id="sap-approved-spend",
        )
        other_source = _seed_source_governance(
            session,
            source_id="crm-pipeline",
            owner_binding="group:sales-analysts",
        )

        prepared = prepare_generation_context(
            request_id="req_preview_80",
            question="Show approved vendors by quarterly spend",
            source_id="sap-approved-spend",
            authenticated_subject=AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session=session,
        )

    assert prepared.model_dump() == {
        "request": {
            "request_id": "req_preview_80",
            "question": "Show approved vendors by quarterly spend",
        },
        "source": {
            "source_id": "sap-approved-spend",
            "display_label": "sap-approved-spend display",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "governance": {
            "dataset_contract_id": str(selected_source.dataset_contract_id),
            "schema_snapshot_id": str(selected_source.schema_snapshot_id),
        },
        "datasets": [
            {
                "schema_name": "analytics",
                "dataset_name": "sap-approved-spend_summary",
                "dataset_kind": "view",
            },
            {
                "schema_name": "finance",
                "dataset_name": "sap-approved-spend_spend",
                "dataset_kind": "table",
            },
        ],
    }
    assert "crm-pipeline" not in str(prepared.model_dump())
    assert str(other_source.dataset_contract_id) not in str(prepared.model_dump())
    assert "connection_reference" not in prepared.model_dump()


def test_prepare_generation_context_rejects_missing_active_contract_linkage() -> None:
    with _session_scope() as session:
        _seed_source_governance(
            session,
            source_id="sap-approved-spend",
            link_active_contract=False,
        )

        try:
            prepare_generation_context(
                request_id="req_preview_80",
                question="Show approved vendors by quarterly spend",
                source_id="sap-approved-spend",
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
            )
        except GenerationContextPreparationError as exc:
            assert str(exc) == (
                "Registered source 'sap-approved-spend' has no active dataset contract."
            )
        else:
            raise AssertionError(
                "generation context preparation unexpectedly accepted missing contract linkage"
            )
