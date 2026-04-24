from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from app.db.models.dataset_contract import DatasetContract
from app.db.models.retrieval_corpus import (
    RetrievalCorpusAsset,
    RetrievalCorpusAssetStatus,
)
from app.db.models.schema_snapshot import SchemaSnapshot
from app.db.models.source_registry import RegisteredSource
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


class RetrievedAssetSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None
    dataset_contract_version: int
    schema_snapshot_version: int


class RetrievedCorpusAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: NonEmptyTrimmedString
    asset_kind: NonEmptyTrimmedString
    title: NonEmptyTrimmedString
    body: NonEmptyTrimmedString
    citation_label: NonEmptyTrimmedString
    source: RetrievedAssetSource
    authority: Literal["advisory_context"] = "advisory_context"
    can_authorize_execution: Literal[False] = False


class RetrievalCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: NonEmptyTrimmedString
    asset_kind: NonEmptyTrimmedString
    citation_label: NonEmptyTrimmedString
    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None
    dataset_contract_version: int
    schema_snapshot_version: int
    authority: Literal["advisory_context"] = "advisory_context"
    can_authorize_execution: Literal[False] = False


class RetrievalCorpusAuditHook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_version: NonEmptyTrimmedString
    retrieved_asset_ids: list[NonEmptyTrimmedString]
    citations: list[RetrievalCitation]


class GovernedRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: NonEmptyTrimmedString
    assets: list[RetrievedCorpusAsset]
    audit: RetrievalCorpusAuditHook


class RetrievalCorpusGovernanceError(ValueError):
    """Raised when retrieval cannot be governed by source-scoped authority."""


def _normalized_binding(binding: str | None) -> str | None:
    if binding is None:
        return None
    normalized = binding.strip()
    if not normalized:
        return None
    return normalized


def _asset_matches_authoritative_source(
    asset: RetrievalCorpusAsset,
    source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
) -> bool:
    return (
        asset.registered_source_id == source.id
        and asset.source_id == source.source_id
        and asset.source_family == source.source_family
        and asset.source_flavor == source.source_flavor
        and asset.dataset_contract_id == dataset_contract.id
        and asset.dataset_contract_version == dataset_contract.contract_version
        and asset.schema_snapshot_id == schema_snapshot.id
        and asset.schema_snapshot_version == schema_snapshot.snapshot_version
        and _normalized_binding(asset.owner_binding)
        == _normalized_binding(dataset_contract.owner_binding)
    )


def _subject_can_see_asset(
    subject: AuthenticatedSubject,
    asset: RetrievalCorpusAsset,
) -> bool:
    subject_bindings = subject.normalized_governance_bindings()
    visibility_binding = _normalized_binding(asset.visibility_binding)
    owner_binding = _normalized_binding(asset.owner_binding)
    if visibility_binding is None or owner_binding is None:
        return False
    return visibility_binding in subject_bindings


def _to_retrieved_asset(asset: RetrievalCorpusAsset) -> RetrievedCorpusAsset:
    return RetrievedCorpusAsset(
        asset_id=asset.asset_id,
        asset_kind=asset.asset_kind.value,
        title=asset.title,
        body=asset.body,
        citation_label=asset.citation_label,
        source=RetrievedAssetSource(
            source_id=asset.source_id,
            source_family=asset.source_family,
            source_flavor=asset.source_flavor,
            dataset_contract_version=asset.dataset_contract_version,
            schema_snapshot_version=asset.schema_snapshot_version,
        ),
    )


def _to_retrieval_citation(asset: RetrievedCorpusAsset) -> RetrievalCitation:
    return RetrievalCitation(
        asset_id=asset.asset_id,
        asset_kind=asset.asset_kind,
        citation_label=asset.citation_label,
        source_id=asset.source.source_id,
        source_family=asset.source.source_family,
        source_flavor=asset.source.source_flavor,
        dataset_contract_version=asset.source.dataset_contract_version,
        schema_snapshot_version=asset.source.schema_snapshot_version,
        authority=asset.authority,
        can_authorize_execution=asset.can_authorize_execution,
    )


def _load_governed_source(
    *,
    session: Session,
    source_id: str,
    authenticated_subject: AuthenticatedSubject,
) -> tuple[RegisteredSource, DatasetContract, SchemaSnapshot]:
    try:
        source, dataset_contract, schema_snapshot = resolve_authoritative_source_governance(
            session,
            source_id=source_id,
        )
        ensure_subject_is_entitled_for_source(
            authenticated_subject,
            source,
            dataset_contract,
        )
    except (SourceGovernanceResolutionError, SourceEntitlementError) as exc:
        raise RetrievalCorpusGovernanceError(str(exc)) from exc
    return source, dataset_contract, schema_snapshot


def retrieve_governed_corpus_assets(
    *,
    query_text: str,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
    source_id: str | None = None,
) -> GovernedRetrievalResult:
    normalized_query = query_text.strip()
    if not normalized_query:
        raise RetrievalCorpusGovernanceError("Retrieval query text is required.")

    statement = (
        select(RetrievalCorpusAsset)
        .where(RetrievalCorpusAsset.status == RetrievalCorpusAssetStatus.APPROVED)
        .order_by(RetrievalCorpusAsset.source_id.asc(), RetrievalCorpusAsset.asset_id.asc())
    )

    governed_sources: dict[str, tuple[RegisteredSource, DatasetContract, SchemaSnapshot]] = {}
    if source_id is not None:
        normalized_source_id = source_id.strip()
        if not normalized_source_id:
            raise RetrievalCorpusGovernanceError("Retrieval source_id is required when provided.")
        governed_sources[normalized_source_id] = _load_governed_source(
            session=session,
            source_id=normalized_source_id,
            authenticated_subject=authenticated_subject,
        )
        statement = statement.where(RetrievalCorpusAsset.source_id == normalized_source_id)

    retrieved_assets: list[RetrievedCorpusAsset] = []
    for asset in session.execute(statement).scalars():
        if asset.source_id not in governed_sources:
            try:
                governed_sources[asset.source_id] = _load_governed_source(
                    session=session,
                    source_id=asset.source_id,
                    authenticated_subject=authenticated_subject,
                )
            except RetrievalCorpusGovernanceError:
                continue

        source, dataset_contract, schema_snapshot = governed_sources[asset.source_id]
        if not _asset_matches_authoritative_source(
            asset,
            source,
            dataset_contract,
            schema_snapshot,
        ):
            continue
        if not _subject_can_see_asset(authenticated_subject, asset):
            continue
        retrieved_assets.append(_to_retrieved_asset(asset))

    retrieved_asset_ids = [asset.asset_id for asset in retrieved_assets]
    citations = [_to_retrieval_citation(asset) for asset in retrieved_assets]
    return GovernedRetrievalResult(
        query_text=normalized_query,
        assets=retrieved_assets,
        audit=RetrievalCorpusAuditHook(
            corpus_version="source-aware-v1",
            retrieved_asset_ids=retrieved_asset_ids,
            citations=citations,
        ),
    )
