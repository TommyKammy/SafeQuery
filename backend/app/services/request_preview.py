from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session
from typing import Optional
from typing_extensions import Annotated

from app.db.models.dataset_contract import DatasetContract
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
    source_family: str
    source_flavor: Optional[str]
    dataset_contract_version: int
    schema_snapshot_version: int
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
) -> tuple[RegisteredSource, DatasetContract, SchemaSnapshot]:
    try:
        source, dataset_contract, schema_snapshot = resolve_authoritative_source_governance(
            session,
            source_id=source_id,
        )
    except SourceGovernanceResolutionError as exc:
        raise PreviewSubmissionContractError(str(exc)) from exc

    return source, dataset_contract, schema_snapshot


def submit_preview_request(
    payload: PreviewSubmissionRequest,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
) -> PreviewSubmissionResponse:
    source, dataset_contract, schema_snapshot = _resolve_authoritative_source_governance(
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
            source_family=resolved_source.source_family,
            source_flavor=resolved_source.source_flavor,
            dataset_contract_version=dataset_contract.contract_version,
            schema_snapshot_version=schema_snapshot.snapshot_version,
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
