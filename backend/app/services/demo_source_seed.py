from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.dataset_contract import (
    DatasetContract,
    DatasetContractDataset,
    DatasetContractDatasetKind,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture


DEMO_SOURCE_ID = "demo-business-postgres"
DEMO_SOURCE_UUID = UUID("11111111-1111-4111-8111-111111111111")
DEMO_SCHEMA_SNAPSHOT_UUID = UUID("22222222-2222-4222-8222-222222222222")
DEMO_DATASET_CONTRACT_UUID = UUID("33333333-3333-4333-8333-333333333333")
DEMO_APPROVED_VENDORS_DATASET_UUID = UUID("44444444-4444-4444-8444-444444444444")
DEMO_QUARTERLY_SPEND_DATASET_UUID = UUID("55555555-5555-4555-8555-555555555555")
DEMO_REVIEWED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
DEMO_DEV_SUBJECT_ID = "user:demo-local-operator"
DEMO_DEV_GOVERNANCE_BINDING = "group:safequery-demo-local-operators"


@dataclass(frozen=True)
class DemoSourceSeedResult:
    source_id: str
    created: bool
    source_record_id: UUID
    dataset_contract_id: UUID
    schema_snapshot_id: UUID


@dataclass(frozen=True)
class _DemoDatasetSeed:
    record_id: UUID
    schema_name: str
    dataset_name: str
    dataset_kind: DatasetContractDatasetKind


_DEMO_DATASETS = (
    _DemoDatasetSeed(
        record_id=DEMO_APPROVED_VENDORS_DATASET_UUID,
        schema_name="public",
        dataset_name="approved_vendors",
        dataset_kind=DatasetContractDatasetKind.TABLE,
    ),
    _DemoDatasetSeed(
        record_id=DEMO_QUARTERLY_SPEND_DATASET_UUID,
        schema_name="public",
        dataset_name="quarterly_spend",
        dataset_kind=DatasetContractDatasetKind.TABLE,
    ),
)


def _upsert_demo_source(session: Session) -> tuple[RegisteredSource, bool]:
    source = session.scalar(
        select(RegisteredSource).where(RegisteredSource.source_id == DEMO_SOURCE_ID)
    )
    created = source is None
    if source is None:
        source = RegisteredSource(
            id=DEMO_SOURCE_UUID,
            source_id=DEMO_SOURCE_ID,
            display_label="Demo business PostgreSQL",
            source_family="postgresql",
            source_flavor="demo",
            activation_posture=SourceActivationPosture.ACTIVE,
            connector_profile_id=None,
            dialect_profile_id=None,
            dataset_contract_id=None,
            schema_snapshot_id=None,
            execution_policy_id=None,
            connection_reference="env:SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        )
        session.add(source)

    source.display_label = "Demo business PostgreSQL"
    source.source_family = "postgresql"
    source.source_flavor = "demo"
    source.activation_posture = SourceActivationPosture.ACTIVE
    source.connector_profile_id = None
    source.dialect_profile_id = None
    source.execution_policy_id = None
    source.connection_reference = "env:SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL"
    session.flush()
    return source, created


def _upsert_demo_schema_snapshot(
    session: Session,
    *,
    source: RegisteredSource,
) -> SchemaSnapshot:
    snapshot = session.scalar(
        select(SchemaSnapshot).where(SchemaSnapshot.id == DEMO_SCHEMA_SNAPSHOT_UUID)
    )
    if snapshot is None:
        snapshot = SchemaSnapshot(
            id=DEMO_SCHEMA_SNAPSHOT_UUID,
            registered_source_id=source.id,
            snapshot_version=1,
            review_status=SchemaSnapshotReviewStatus.APPROVED,
            reviewed_at=DEMO_REVIEWED_AT,
        )
        session.add(snapshot)

    snapshot.registered_source_id = source.id
    snapshot.snapshot_version = 1
    snapshot.review_status = SchemaSnapshotReviewStatus.APPROVED
    snapshot.reviewed_at = DEMO_REVIEWED_AT
    session.flush()
    return snapshot


def _upsert_demo_dataset_contract(
    session: Session,
    *,
    source: RegisteredSource,
    snapshot: SchemaSnapshot,
) -> DatasetContract:
    # Dev/local fixture only. Later dev auth middleware may grant this exact
    # binding to DEMO_DEV_SUBJECT_ID; production auth must supply trusted
    # source-scoped bindings from its own identity boundary.
    contract = session.scalar(
        select(DatasetContract).where(DatasetContract.id == DEMO_DATASET_CONTRACT_UUID)
    )
    if contract is None:
        contract = DatasetContract(
            id=DEMO_DATASET_CONTRACT_UUID,
            registered_source_id=source.id,
            schema_snapshot_id=snapshot.id,
            contract_version=1,
            display_name="Demo business PostgreSQL contract",
            owner_binding=DEMO_DEV_GOVERNANCE_BINDING,
            security_review_binding="group:security-reviewers",
            exception_policy_binding=None,
        )
        session.add(contract)

    contract.registered_source_id = source.id
    contract.schema_snapshot_id = snapshot.id
    contract.contract_version = 1
    contract.display_name = "Demo business PostgreSQL contract"
    contract.owner_binding = DEMO_DEV_GOVERNANCE_BINDING
    contract.security_review_binding = "group:security-reviewers"
    contract.exception_policy_binding = None
    session.flush()
    return contract


def _upsert_demo_dataset(
    session: Session,
    *,
    contract: DatasetContract,
    dataset_seed: _DemoDatasetSeed,
) -> DatasetContractDataset:
    dataset = session.scalar(
        select(DatasetContractDataset).where(
            DatasetContractDataset.id == dataset_seed.record_id
        )
    )
    if dataset is None:
        dataset = DatasetContractDataset(
            id=dataset_seed.record_id,
            dataset_contract_id=contract.id,
            schema_name=dataset_seed.schema_name,
            dataset_name=dataset_seed.dataset_name,
            dataset_kind=dataset_seed.dataset_kind,
        )
        session.add(dataset)

    dataset.dataset_contract_id = contract.id
    dataset.schema_name = dataset_seed.schema_name
    dataset.dataset_name = dataset_seed.dataset_name
    dataset.dataset_kind = dataset_seed.dataset_kind
    session.flush()
    return dataset


def seed_demo_source_governance(session: Session) -> DemoSourceSeedResult:
    try:
        source, created = _upsert_demo_source(session)
        snapshot = _upsert_demo_schema_snapshot(session, source=source)
        contract = _upsert_demo_dataset_contract(
            session,
            source=source,
            snapshot=snapshot,
        )
        for dataset_seed in _DEMO_DATASETS:
            _upsert_demo_dataset(
                session,
                contract=contract,
                dataset_seed=dataset_seed,
            )

        source.dataset_contract_id = contract.id
        source.schema_snapshot_id = snapshot.id
        session.commit()
    except Exception:
        session.rollback()
        raise

    return DemoSourceSeedResult(
        source_id=source.source_id,
        created=created,
        source_record_id=source.id,
        dataset_contract_id=contract.id,
        schema_snapshot_id=snapshot.id,
    )
