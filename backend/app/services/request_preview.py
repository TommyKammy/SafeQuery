from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import Optional
from typing_extensions import Annotated
from uuid import UUID, uuid4

from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import PreviewCandidate, PreviewRequest
from app.db.models.schema_snapshot import SchemaSnapshot
from app.db.models.source_registry import RegisteredSource
from app.features.audit.event_model import SourceAwareAuditEvent
from app.features.auth.context import AuthenticatedSubject
from app.features.auth.governance_bindings import normalize_governance_binding
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)
from app.services.source_governance import (
    SourceGovernanceResolutionError,
    resolve_authoritative_source_governance,
)
from app.services.source_registry import SourceRegistryPostureError


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
    events: list[SourceAwareAuditEvent] = Field(default_factory=list)


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


class PreviewSubmissionEntitlementError(PreviewSubmissionContractError, PermissionError):
    """Raised when an authenticated subject lacks source execution entitlement."""

    def __init__(
        self,
        message: str,
        *,
        audit_events: list[SourceAwareAuditEvent] | None = None,
    ) -> None:
        super().__init__(message)
        self.audit_events = list(audit_events or [])


class PreviewAuditContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    request_id: str
    correlation_id: str
    user_subject: str
    session_id: str
    query_candidate_id: Optional[str] = None
    candidate_owner_subject: Optional[str] = None
    auth_source: Optional[str] = None
    governance_bindings: list[str] = Field(default_factory=list)
    entitlement_decision: Optional[str] = None
    entitlement_source_bindings: list[str] = Field(default_factory=list)
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
            auth_source=audit_context.auth_source,
            governance_bindings=audit_context.governance_bindings or None,
            entitlement_decision=audit_context.entitlement_decision,
            entitlement_source_bindings=(
                audit_context.entitlement_source_bindings or None
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


def _contract_execution_entitlement_bindings(
    dataset_contract: DatasetContract,
) -> list[str]:
    bindings = [
        normalized
        for binding in (dataset_contract.owner_binding,)
        if (normalized := normalize_governance_binding(binding)) is not None
    ]
    return sorted(bindings)


def _enrich_preview_audit_context(
    audit_context: PreviewAuditContext | None,
    *,
    authenticated_subject: AuthenticatedSubject,
    dataset_contract: DatasetContract,
    entitlement_decision: str,
) -> None:
    if audit_context is None:
        return

    audit_context.user_subject = authenticated_subject.normalized_subject_id()
    audit_context.governance_bindings = sorted(
        authenticated_subject.normalized_governance_bindings()
    )
    audit_context.entitlement_decision = entitlement_decision
    audit_context.entitlement_source_bindings = _contract_execution_entitlement_bindings(
        dataset_contract
    )


def _build_preview_entitlement_denial_audit_event(
    *,
    resolved_source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
    audit_context: PreviewAuditContext | None,
) -> list[SourceAwareAuditEvent]:
    if audit_context is None:
        return []

    return [
        SourceAwareAuditEvent(
            event_id=uuid4(),
            event_type="generation_failed",
            occurred_at=audit_context.occurred_at,
            request_id=audit_context.request_id,
            correlation_id=audit_context.correlation_id,
            user_subject=audit_context.user_subject,
            session_id=audit_context.session_id,
            auth_source=audit_context.auth_source,
            governance_bindings=audit_context.governance_bindings or None,
            entitlement_decision=audit_context.entitlement_decision,
            entitlement_source_bindings=(
                audit_context.entitlement_source_bindings or None
            ),
            application_version=audit_context.application_version,
            source_id=resolved_source.source_id,
            source_family=resolved_source.source_family,
            source_flavor=resolved_source.source_flavor,
            dataset_contract_version=dataset_contract.contract_version,
            schema_snapshot_version=schema_snapshot.snapshot_version,
            primary_deny_code="DENY_SOURCE_ENTITLEMENT",
            denial_cause="entitlement_denied",
        )
    ]


def _joined_governance_bindings(bindings: list[str]) -> str | None:
    return ",".join(sorted(bindings)) if bindings else None


def _persist_preview_submission_records(
    session: Session,
    *,
    payload: PreviewSubmissionRequest,
    resolved_source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
    authenticated_subject: AuthenticatedSubject,
    audit_context: PreviewAuditContext | None,
) -> None:
    request_id = (
        audit_context.request_id
        if audit_context is not None and audit_context.request_id.strip()
        else str(uuid4())
    )
    candidate_id = (
        audit_context.query_candidate_id
        if (
            audit_context is not None
            and audit_context.query_candidate_id is not None
            and audit_context.query_candidate_id.strip()
        )
        else str(uuid4())
    )
    subject_id = authenticated_subject.normalized_subject_id()
    governance_bindings = _joined_governance_bindings(
        sorted(authenticated_subject.normalized_governance_bindings())
    )

    preview_request = session.execute(
        select(PreviewRequest).where(PreviewRequest.request_id == request_id)
    ).scalar_one_or_none()
    if preview_request is None:
        preview_request = PreviewRequest(request_id=request_id)
        session.add(preview_request)
    elif preview_request.registered_source_id != resolved_source.id:
        raise PreviewSubmissionContractError(
            "Preview request cannot be rebound to a different source."
        )

    preview_request.registered_source_id = resolved_source.id
    preview_request.source_id = resolved_source.source_id
    preview_request.source_family = resolved_source.source_family
    preview_request.source_flavor = resolved_source.source_flavor
    preview_request.dataset_contract_id = dataset_contract.id
    preview_request.dataset_contract_version = dataset_contract.contract_version
    preview_request.schema_snapshot_id = schema_snapshot.id
    preview_request.schema_snapshot_version = schema_snapshot.snapshot_version
    preview_request.authenticated_subject_id = subject_id
    preview_request.auth_source = (
        audit_context.auth_source if audit_context is not None else None
    )
    preview_request.session_id = (
        audit_context.session_id if audit_context is not None else None
    )
    preview_request.governance_bindings = governance_bindings
    preview_request.entitlement_decision = "allow"
    preview_request.request_text = payload.question
    preview_request.request_state = "previewed"
    session.flush()

    preview_candidate = session.execute(
        select(PreviewCandidate).where(PreviewCandidate.candidate_id == candidate_id)
    ).scalar_one_or_none()
    if preview_candidate is None:
        preview_candidate = PreviewCandidate(candidate_id=candidate_id)
        session.add(preview_candidate)
    elif (
        preview_candidate.preview_request_id != preview_request.id
        or preview_candidate.registered_source_id != resolved_source.id
    ):
        raise PreviewSubmissionContractError(
            "Preview candidate cannot be rebound to a different request or source."
        )

    preview_candidate.preview_request_id = preview_request.id
    preview_candidate.request_id = request_id
    preview_candidate.registered_source_id = resolved_source.id
    preview_candidate.source_id = resolved_source.source_id
    preview_candidate.source_family = resolved_source.source_family
    preview_candidate.source_flavor = resolved_source.source_flavor
    preview_candidate.dataset_contract_id = dataset_contract.id
    preview_candidate.dataset_contract_version = dataset_contract.contract_version
    preview_candidate.schema_snapshot_id = schema_snapshot.id
    preview_candidate.schema_snapshot_version = schema_snapshot.snapshot_version
    preview_candidate.authenticated_subject_id = subject_id
    preview_candidate.candidate_sql = None
    preview_candidate.guard_status = "not_evaluated"
    preview_candidate.candidate_state = "preview_ready"
    session.commit()


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
        if isinstance(exc.__cause__, (SourceRegistryPostureError, ValueError)):
            raise PreviewSubmissionContractError(str(exc)) from exc
        _enrich_preview_audit_context(
            audit_context,
            authenticated_subject=authenticated_subject,
            dataset_contract=dataset_contract,
            entitlement_decision="deny",
        )
        raise PreviewSubmissionEntitlementError(
            str(exc),
            audit_events=_build_preview_entitlement_denial_audit_event(
                resolved_source=source,
                dataset_contract=dataset_contract,
                schema_snapshot=schema_snapshot,
                audit_context=audit_context,
            ),
        ) from exc

    _enrich_preview_audit_context(
        audit_context,
        authenticated_subject=authenticated_subject,
        dataset_contract=dataset_contract,
        entitlement_decision="allow",
    )

    audit = AuditRecord(
        source_id=resolved_source.source_id,
        state="recorded",
        events=_build_preview_lifecycle_audit_events(
            resolved_source=resolved_source,
            dataset_contract=dataset_contract,
            schema_snapshot=schema_snapshot,
            audit_context=audit_context,
        ),
    )
    _persist_preview_submission_records(
        session,
        payload=payload,
        resolved_source=resolved_source,
        dataset_contract=dataset_contract,
        schema_snapshot=schema_snapshot,
        authenticated_subject=authenticated_subject,
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
