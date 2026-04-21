from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource
from app.features.auth.context import AuthenticatedSubject
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PreviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyTrimmedString
    source_id: NonEmptyTrimmedString


class RequestRecord(BaseModel):
    question: str
    source_id: str
    state: str


class CandidateRecord(BaseModel):
    source_id: str
    state: str


class AuditRecord(BaseModel):
    source_id: str
    state: str


class EvaluationRecord(BaseModel):
    source_id: str
    state: str


class PreviewSubmissionResponse(BaseModel):
    request: RequestRecord
    candidate: CandidateRecord
    audit: AuditRecord
    evaluation: EvaluationRecord


class PreviewSubmissionContractError(ValueError):
    """Raised when a preview submission does not carry an executable source binding."""


def _resolve_authoritative_source_governance(
    session: Session,
    *,
    source_id: str,
) -> tuple[RegisteredSource, DatasetContract]:
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
        raise PreviewSubmissionContractError(
            f"Registered source '{source_id}' does not exist."
        )

    source, dataset_contract, schema_snapshot = governance_row

    if source.dataset_contract_id is None:
        raise PreviewSubmissionContractError(
            f"Registered source '{source.source_id}' has no active dataset contract."
        )
    if source.schema_snapshot_id is None:
        raise PreviewSubmissionContractError(
            f"Registered source '{source.source_id}' has no linked schema snapshot."
        )

    if (
        dataset_contract is None
        or dataset_contract.registered_source_id != source.id
        or dataset_contract.schema_snapshot_id != source.schema_snapshot_id
    ):
        raise PreviewSubmissionContractError(
            f"Registered source '{source.source_id}' is missing "
            "authoritative source-scoped governance artifacts."
        )

    if schema_snapshot is None or schema_snapshot.registered_source_id != source.id:
        raise PreviewSubmissionContractError(
            f"Registered source '{source.source_id}' has no linked schema snapshot."
        )
    if schema_snapshot.review_status != SchemaSnapshotReviewStatus.APPROVED:
        raise PreviewSubmissionContractError(
            f"Registered source '{source.source_id}' requires an approved schema snapshot."
        )

    return source, dataset_contract


def submit_preview_request(
    payload: PreviewSubmissionRequest,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
) -> PreviewSubmissionResponse:
    source, dataset_contract = _resolve_authoritative_source_governance(
        session,
        source_id=payload.source_id,
    )

    try:
        resolved_source = ensure_subject_is_entitled_for_source(
            authenticated_subject,
            source,
            dataset_contract,
        )
    except SourceEntitlementError as exc:
        raise PreviewSubmissionContractError(str(exc)) from exc

    return PreviewSubmissionResponse(
        request=RequestRecord(
            question=payload.question,
            source_id=resolved_source.source_id,
            state="submitted",
        ),
        candidate=CandidateRecord(
            source_id=resolved_source.source_id,
            state="preview_ready",
        ),
        audit=AuditRecord(
            source_id=resolved_source.source_id,
            state="recorded",
        ),
        evaluation=EvaluationRecord(
            source_id=resolved_source.source_id,
            state="pending",
        ),
    )
