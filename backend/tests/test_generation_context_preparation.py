from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
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
from app.services.generation_context import (
    GenerationContextPreparationError,
    prepare_generation_context,
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


def _seed_source_governance(
    session: Session,
    *,
    source_id: str,
    owner_binding: str = "group:finance-analysts",
    snapshot_status: SchemaSnapshotReviewStatus = SchemaSnapshotReviewStatus.APPROVED,
    include_datasets: bool = True,
    link_active_contract: bool = True,
    link_active_snapshot: bool = True,
    link_contract_snapshot: bool = True,
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
        display_name=f"{source_id} contract",
        owner_binding=owner_binding,
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    if include_datasets:
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
    if link_active_snapshot:
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

        with pytest.raises(
            GenerationContextPreparationError,
            match=r"Registered source 'sap-approved-spend' has no active dataset contract\.",
        ) as exc_info:
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

    assert exc_info.value.code == "governance_resolution_failed"


def test_prepare_generation_context_rejects_non_approved_schema_snapshot() -> None:
    with _session_scope() as session:
        _seed_source_governance(
            session,
            source_id="sap-approved-spend",
            snapshot_status=SchemaSnapshotReviewStatus.PENDING,
        )

        with pytest.raises(
            GenerationContextPreparationError,
            match=(
                r"Registered source 'sap-approved-spend' requires an approved schema snapshot\."
            ),
        ) as exc_info:
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

    assert exc_info.value.code == "governance_resolution_failed"


def test_prepare_generation_context_rejects_contract_snapshot_drift() -> None:
    with _session_scope() as session:
        _seed_source_governance(
            session,
            source_id="sap-approved-spend",
            link_contract_snapshot=False,
        )

        with pytest.raises(
            GenerationContextPreparationError,
            match=(
                r"Registered source 'sap-approved-spend' is missing "
                r"authoritative source-scoped governance artifacts\."
            ),
        ) as exc_info:
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

    assert exc_info.value.code == "governance_resolution_failed"


def test_prepare_generation_context_rejects_unentitled_subject_with_specific_code() -> None:
    with _session_scope() as session:
        _seed_source_governance(
            session,
            source_id="sap-approved-spend",
        )

        with pytest.raises(
            GenerationContextPreparationError,
            match=(
                r"Authenticated subject 'user:alice' is not entitled to use "
                r"registered source 'sap-approved-spend'\."
            ),
        ) as exc_info:
            prepare_generation_context(
                request_id="req_preview_80",
                question="Show approved vendors by quarterly spend",
                source_id="sap-approved-spend",
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:sales-analysts"}),
                ),
                session=session,
            )

    assert exc_info.value.code == "entitlement_check_failed"


def test_prepare_generation_context_rejects_missing_datasets_with_specific_code() -> None:
    with _session_scope() as session:
        _seed_source_governance(
            session,
            source_id="sap-approved-spend",
            include_datasets=False,
        )

        with pytest.raises(
            GenerationContextPreparationError,
            match=(
                r"Registered source 'sap-approved-spend' has no approved datasets "
                r"in the active contract\."
            ),
        ) as exc_info:
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

    assert exc_info.value.code == "no_approved_datasets"
