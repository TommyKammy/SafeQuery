from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from app.db.models.dataset_contract import DatasetContractDataset
from app.features.auth.context import AuthenticatedSubject
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)
from app.services.source_governance import (
    SourceGovernanceResolutionError,
    resolve_authoritative_source_governance,
)


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DatasetKindLiteral = Literal["view", "table", "materialized_view"]


class GenerationContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyTrimmedString
    question: NonEmptyTrimmedString


class GenerationContextSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    display_label: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None


class GenerationContextGovernance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_contract_id: NonEmptyTrimmedString
    schema_snapshot_id: NonEmptyTrimmedString


class GenerationContextDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: NonEmptyTrimmedString
    dataset_name: NonEmptyTrimmedString
    dataset_kind: DatasetKindLiteral


class PreparedGenerationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: GenerationContextRequest
    source: GenerationContextSource
    governance: GenerationContextGovernance
    datasets: list[GenerationContextDataset]


class GenerationContextPreparationError(ValueError):
    """Raised when curated generation context cannot be prepared safely."""


def prepare_generation_context(
    *,
    request_id: str,
    question: str,
    source_id: str,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
) -> PreparedGenerationContext:
    try:
        source, dataset_contract, schema_snapshot = resolve_authoritative_source_governance(
            session,
            source_id=source_id,
        )
        resolved_source = ensure_subject_is_entitled_for_source(
            authenticated_subject,
            source,
            dataset_contract,
        )
    except (SourceGovernanceResolutionError, SourceEntitlementError) as exc:
        raise GenerationContextPreparationError(str(exc)) from exc

    approved_datasets = session.execute(
        select(DatasetContractDataset)
        .where(DatasetContractDataset.dataset_contract_id == dataset_contract.id)
        .order_by(
            DatasetContractDataset.schema_name.asc(),
            DatasetContractDataset.dataset_name.asc(),
        )
    ).scalars().all()
    if not approved_datasets:
        raise GenerationContextPreparationError(
            f"Registered source '{resolved_source.source_id}' has no approved datasets in the active contract."
        )

    return PreparedGenerationContext(
        request=GenerationContextRequest(
            request_id=request_id,
            question=question,
        ),
        source=GenerationContextSource(
            source_id=resolved_source.source_id,
            display_label=resolved_source.display_label,
            source_family=resolved_source.source_family,
            source_flavor=resolved_source.source_flavor,
        ),
        governance=GenerationContextGovernance(
            dataset_contract_id=str(dataset_contract.id),
            schema_snapshot_id=str(schema_snapshot.id),
        ),
        datasets=[
            GenerationContextDataset(
                schema_name=dataset.schema_name,
                dataset_name=dataset.dataset_name,
                dataset_kind=dataset.dataset_kind.value,
            )
            for dataset in approved_datasets
        ],
    )
