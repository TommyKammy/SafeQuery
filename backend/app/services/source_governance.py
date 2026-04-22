from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource


class SourceGovernanceResolutionError(ValueError):
    """Raised when a registered source lacks authoritative governance linkage."""


def resolve_authoritative_source_governance(
    session: Session,
    *,
    source_id: str,
) -> tuple[RegisteredSource, DatasetContract, SchemaSnapshot]:
    governance_row = session.execute(
        select(RegisteredSource, DatasetContract, SchemaSnapshot)
        .outerjoin(
            DatasetContract,
            DatasetContract.id == RegisteredSource.dataset_contract_id,
        )
        .outerjoin(
            SchemaSnapshot,
            SchemaSnapshot.id == RegisteredSource.schema_snapshot_id,
        )
        .where(RegisteredSource.source_id == source_id)
    ).one_or_none()
    if governance_row is None:
        raise SourceGovernanceResolutionError(
            f"Registered source '{source_id}' does not exist."
        )

    source, dataset_contract, schema_snapshot = governance_row

    if source.dataset_contract_id is None:
        raise SourceGovernanceResolutionError(
            f"Registered source '{source.source_id}' has no active dataset contract."
        )
    if source.schema_snapshot_id is None:
        raise SourceGovernanceResolutionError(
            f"Registered source '{source.source_id}' has no linked schema snapshot."
        )

    if (
        dataset_contract is None
        or dataset_contract.registered_source_id != source.id
        or dataset_contract.schema_snapshot_id != source.schema_snapshot_id
    ):
        raise SourceGovernanceResolutionError(
            f"Registered source '{source.source_id}' is missing "
            "authoritative source-scoped governance artifacts."
        )

    if schema_snapshot is None or schema_snapshot.registered_source_id != source.id:
        raise SourceGovernanceResolutionError(
            f"Registered source '{source.source_id}' has no linked schema snapshot."
        )
    if schema_snapshot.review_status != SchemaSnapshotReviewStatus.APPROVED:
        raise SourceGovernanceResolutionError(
            f"Registered source '{source.source_id}' requires an approved schema snapshot."
        )

    return source, dataset_contract, schema_snapshot
