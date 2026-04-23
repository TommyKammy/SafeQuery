from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, PrivateAttr, StringConstraints
from sqlalchemy.orm import Session
from typing import Optional
from typing_extensions import Annotated
from uuid import UUID, uuid4

from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot
from app.db.models.source_registry import RegisteredSource
from app.features.audit.event_model import SourceAwareAuditEvent
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
    _events: list[SourceAwareAuditEvent] = PrivateAttr(default_factory=list)

    @property
    def events(self) -> list[SourceAwareAuditEvent]:
        return list(self._events)


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


class PreviewAuditContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    request_id: str
    correlation_id: str
    user_subject: str
    session_id: str
    query_candidate_id: Optional[str] = None
    candidate_owner_subject: Optional[str] = None
    guard_version: Optional[str] = None
    application_version: Optional[str] = None


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


def _build_preview_lifecycle_audit_events(
    *,
    resolved_source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
    audit_context: PreviewAuditContext | None,
) -> list[SourceAwareAuditEvent]:
    if audit_context is None:
        return []

    events: list[SourceAwareAuditEvent] = []
    causation_event_id: UUID | None = None
    for event_type in (
        "query_submitted",
        "generation_requested",
        "generation_completed",
        "guard_evaluated",
    ):
        event = SourceAwareAuditEvent(
            event_id=uuid4(),
            event_type=event_type,
            occurred_at=audit_context.occurred_at,
            request_id=audit_context.request_id,
            correlation_id=audit_context.correlation_id,
            causation_event_id=causation_event_id,
            user_subject=audit_context.user_subject,
            session_id=audit_context.session_id,
            query_candidate_id=(
                audit_context.query_candidate_id
                if event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            candidate_owner_subject=(
                audit_context.candidate_owner_subject
                if event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            guard_version=(
                audit_context.guard_version if event_type == "guard_evaluated" else None
            ),
            application_version=audit_context.application_version,
            source_id=resolved_source.source_id,
            source_family=resolved_source.source_family,
            source_flavor=resolved_source.source_flavor,
            dataset_contract_version=dataset_contract.contract_version,
            schema_snapshot_version=schema_snapshot.snapshot_version,
            candidate_state="preview_ready" if event_type == "guard_evaluated" else None,
        )
        causation_event_id = event.event_id
        events.append(event)

    return events


def submit_preview_request(
    payload: PreviewSubmissionRequest,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
    audit_context: PreviewAuditContext | None = None,
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

    audit = AuditRecord(
        source_id=resolved_source.source_id,
        state="recorded",
    )
    audit._events = _build_preview_lifecycle_audit_events(
        resolved_source=resolved_source,
        dataset_contract=dataset_contract,
        schema_snapshot=schema_snapshot,
        audit_context=audit_context,
    )

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
        audit=audit,
        evaluation=EvaluationRecord(
            source_id=resolved_source.source_id,
            state="pending",
        ),
    )
