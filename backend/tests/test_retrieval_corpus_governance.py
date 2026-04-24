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
from app.db.models.dataset_contract import DatasetContract
from app.db.models.retrieval_corpus import (
    RetrievalCorpusAsset,
    RetrievalCorpusAssetKind,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.services.retrieval_corpus import (
    RetrievalCorpusGovernanceError,
    retrieve_governed_corpus_assets,
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
    owner_binding: str,
    contract_version: int,
    snapshot_version: int,
) -> tuple[RegisteredSource, DatasetContract, SchemaSnapshot]:
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
        owner_binding=owner_binding,
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.flush()
    return source, contract, snapshot


def _seed_asset(
    session: Session,
    *,
    asset_id: str,
    source: RegisteredSource,
    contract: DatasetContract,
    snapshot: SchemaSnapshot,
    visibility_binding: str,
    text: str,
) -> RetrievalCorpusAsset:
    asset = RetrievalCorpusAsset(
        id=uuid4(),
        asset_id=asset_id,
        registered_source_id=source.id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dataset_contract_id=contract.id,
        dataset_contract_version=contract.contract_version,
        schema_snapshot_id=snapshot.id,
        schema_snapshot_version=snapshot.snapshot_version,
        asset_kind=RetrievalCorpusAssetKind.METRIC_DEFINITION,
        title=f"{source.source_id} metric",
        body=text,
        citation_label=f"{source.source_id} metric definition",
        owner_binding=contract.owner_binding,
        visibility_binding=visibility_binding,
    )
    session.add(asset)
    return asset


def test_retrieval_corpus_assets_are_source_labeled_filtered_and_advisory_only() -> None:
    with _session_scope() as session:
        mssql_source, mssql_contract, mssql_snapshot = _seed_source(
            session,
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver-2022",
            owner_binding="group:finance-analysts",
            contract_version=7,
            snapshot_version=3,
        )
        postgres_source, postgres_contract, postgres_snapshot = _seed_source(
            session,
            source_id="business-postgres-source",
            source_family="postgresql",
            source_flavor="postgresql-16",
            owner_binding="group:people-ops",
            contract_version=2,
            snapshot_version=5,
        )
        _seed_asset(
            session,
            asset_id="asset_finance_margin",
            source=mssql_source,
            contract=mssql_contract,
            snapshot=mssql_snapshot,
            visibility_binding="group:finance-analysts",
            text="Gross margin uses net revenue minus cost of goods sold.",
        )
        _seed_asset(
            session,
            asset_id="asset_people_headcount",
            source=postgres_source,
            contract=postgres_contract,
            snapshot=postgres_snapshot,
            visibility_binding="group:people-ops",
            text="Headcount is measured from the active employee roster.",
        )
        session.commit()

        retrieved = retrieve_governed_corpus_assets(
            query_text="show gross margin by quarter",
            authenticated_subject=AuthenticatedSubject(
                subject_id="user:alice",
                governance_bindings=frozenset({"group:finance-analysts"}),
            ),
            session=session,
            source_id="business-mssql-source",
        )

    assert [asset.asset_id for asset in retrieved.assets] == ["asset_finance_margin"]
    assert retrieved.audit.retrieved_asset_ids == ["asset_finance_margin"]
    assert retrieved.assets[0].source.model_dump() == {
        "source_id": "business-mssql-source",
        "source_family": "mssql",
        "source_flavor": "sqlserver-2022",
        "dataset_contract_version": 7,
        "schema_snapshot_version": 3,
    }
    assert retrieved.assets[0].authority == "advisory_context"
    assert retrieved.assets[0].can_authorize_execution is False
    assert "asset_people_headcount" not in str(retrieved.model_dump())


def test_retrieval_corpus_rejects_explicit_source_without_entitlement() -> None:
    with _session_scope() as session:
        postgres_source, postgres_contract, postgres_snapshot = _seed_source(
            session,
            source_id="business-postgres-source",
            source_family="postgresql",
            source_flavor="postgresql-16",
            owner_binding="group:people-ops",
            contract_version=2,
            snapshot_version=5,
        )
        _seed_asset(
            session,
            asset_id="asset_people_headcount",
            source=postgres_source,
            contract=postgres_contract,
            snapshot=postgres_snapshot,
            visibility_binding="group:people-ops",
            text="Headcount is measured from the active employee roster.",
        )
        session.commit()

        with pytest.raises(
            RetrievalCorpusGovernanceError,
            match=(
                "Authenticated subject 'user:alice' is not entitled to use "
                "registered source 'business-postgres-source'"
            ),
        ):
            retrieve_governed_corpus_assets(
                query_text="show headcount",
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                source_id="business-postgres-source",
            )
