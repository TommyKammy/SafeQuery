from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Optional
from typing_extensions import Annotated
from uuid import UUID, uuid4

from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import (
    PreviewAuditEvent,
    PreviewCandidate,
    PreviewCandidateApproval,
    PreviewRequest,
)
from app.db.models.schema_snapshot import SchemaSnapshot
from app.db.models.source_registry import RegisteredSource
from app.features.audit.event_model import SourceAwareAuditEvent
from app.features.auth.context import AuthenticatedSubject
from app.features.auth.governance_bindings import normalize_governance_binding
from app.features.operator_history.payloads import GuardStatus
from app.services.candidate_lifecycle import (
    CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY,
)
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)
from app.services.source_governance import (
    SourceGovernanceResolutionError,
    resolve_authoritative_source_governance,
)
from app.services.source_registry import SourceRegistryPostureError
from app.services.generation_context import (
    GenerationContextPreparationError,
    prepare_generation_context,
)
from app.services.sql_generation_adapter import (
    SQLGenerationAdapter,
    SQLGenerationAdapterConfigurationError,
    SQLGenerationAdapterRunMetadata,
    build_sql_generation_adapter_request,
    build_sql_generation_adapter_run_metadata,
    normalize_adapter_generated_sql,
)


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PREVIEW_PENDING_GUARD_STATUS: GuardStatus = "pending"


class PreviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: NonEmptyTrimmedString
    source_id: NonEmptyTrimmedString


class RequestRecord(BaseModel):
    question: str
    request_id: str
    source_id: str
    state: str


class CandidateRecord(BaseModel):
    candidate_id: str
    candidate_sql: Optional[str]
    guard_status: GuardStatus
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

    def __init__(
        self,
        message: str,
        *,
        public_code: str | None = None,
        public_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.public_code = public_code
        self.public_message = public_message


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
    adapter_metadata: SQLGenerationAdapterRunMetadata | None = None,
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
            adapter_provider=(
                adapter_metadata.adapter_provider
                if adapter_metadata is not None
                and event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            adapter_model=(
                adapter_metadata.adapter_model
                if adapter_metadata is not None
                and event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            adapter_version=(
                adapter_metadata.adapter_version
                if adapter_metadata is not None
                and event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            adapter_run_id=(
                adapter_metadata.adapter_run_id
                if adapter_metadata is not None
                and event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            prompt_version=(
                adapter_metadata.prompt_version
                if adapter_metadata is not None
                and event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            prompt_fingerprint=(
                adapter_metadata.prompt_fingerprint
                if adapter_metadata is not None
                and event_type in {"generation_completed", "guard_evaluated"}
                else None
            ),
            source_id=resolved_source.source_id,
            source_family=resolved_source.source_family,
            source_flavor=resolved_source.source_flavor,
            dataset_contract_version=dataset_contract.contract_version,
            schema_snapshot_version=schema_snapshot.snapshot_version,
            candidate_state=(
                "generated"
                if adapter_metadata is not None and event_type == "generation_completed"
                else "preview_ready" if event_type == "guard_evaluated" else None
            ),
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


def _build_preview_unavailable_audit_event(
    *,
    resolved_source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
    audit_context: PreviewAuditContext | None,
    primary_deny_code: str,
    denial_cause: str,
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
            primary_deny_code=primary_deny_code,
            denial_cause=denial_cause,
        )
    ]


def _build_preview_generation_failed_audit_event(
    *,
    resolved_source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
    audit_context: PreviewAuditContext | None,
    failure_code: str,
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
            primary_deny_code="DENY_SQL_GENERATION_FAILED",
            denial_cause=failure_code,
        )
    ]


def _joined_governance_bindings(bindings: list[str]) -> str | None:
    return ",".join(sorted(bindings)) if bindings else None


def _persist_preview_audit_events(
    session: Session,
    *,
    preview_request: PreviewRequest,
    preview_candidate: PreviewCandidate | None,
    audit_events: list[SourceAwareAuditEvent],
    starting_lifecycle_order: int = 1,
) -> None:
    event_ids = [event.event_id for event in audit_events]
    existing_event_ids = set(
        session.execute(
            select(PreviewAuditEvent.event_id).where(
                PreviewAuditEvent.event_id.in_(event_ids)
            )
        ).scalars()
    )
    for lifecycle_order, event in enumerate(
        audit_events,
        start=starting_lifecycle_order,
    ):
        if event.event_id in existing_event_ids:
            continue
        payload = event.model_dump(mode="json", exclude_none=True)
        session.add(
            PreviewAuditEvent(
                event_id=event.event_id,
                lifecycle_order=lifecycle_order,
                preview_request_id=preview_request.id,
                preview_candidate_id=(
                    preview_candidate.id if preview_candidate is not None else None
                ),
                request_id=event.request_id,
                candidate_id=event.query_candidate_id,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
                causation_event_id=event.causation_event_id,
                authenticated_subject_id=event.user_subject,
                session_id=event.session_id,
                auth_source=event.auth_source,
                governance_bindings=_joined_governance_bindings(
                    list(event.governance_bindings or [])
                ),
                entitlement_decision=event.entitlement_decision,
                entitlement_source_bindings=_joined_governance_bindings(
                    list(event.entitlement_source_bindings or [])
                ),
                adapter_provider=event.adapter_provider,
                adapter_model=event.adapter_model,
                adapter_version=event.adapter_version,
                adapter_run_id=event.adapter_run_id,
                prompt_version=event.prompt_version,
                prompt_fingerprint=event.prompt_fingerprint,
                application_version=event.application_version,
                source_id=event.source_id,
                source_family=event.source_family,
                source_flavor=event.source_flavor,
                dataset_contract_version=event.dataset_contract_version,
                schema_snapshot_version=event.schema_snapshot_version,
                primary_deny_code=event.primary_deny_code,
                denial_cause=event.denial_cause,
                candidate_state=event.candidate_state,
                audit_payload=payload,
            )
        )


def _next_audit_lifecycle_order(
    session: Session,
    *,
    preview_request: PreviewRequest,
) -> int:
    latest_order = session.execute(
        select(func.max(PreviewAuditEvent.lifecycle_order)).where(
            PreviewAuditEvent.preview_request_id == preview_request.id
        )
    ).scalar_one()
    if latest_order is None:
        return 1
    return int(latest_order) + 1


def persist_execution_audit_events(
    session: Session,
    *,
    candidate_id: str,
    audit_events: list[SourceAwareAuditEvent],
) -> None:
    if not audit_events:
        return

    try:
        preview_candidate = session.execute(
            select(PreviewCandidate).where(
                PreviewCandidate.candidate_id == candidate_id
            )
        ).scalar_one_or_none()
        if preview_candidate is None:
            _raise_preview_persistence_contract_error(
                session,
                "Execution audit events cannot be persisted without a bound preview candidate.",
            )

        assert preview_candidate is not None
        preview_request = session.get(
            PreviewRequest,
            preview_candidate.preview_request_id,
        )
        if preview_request is None:
            _raise_preview_persistence_contract_error(
                session,
                "Execution audit events cannot be persisted without a bound preview request.",
            )

        assert preview_request is not None
        if preview_candidate.request_id != preview_request.request_id:
            _raise_preview_persistence_contract_error(
                session,
                "Execution audit events cannot be rebound to a different request.",
            )

        for event in audit_events:
            if event.query_candidate_id != preview_candidate.candidate_id:
                _raise_preview_persistence_contract_error(
                    session,
                    "Execution audit events must stay bound to the preview candidate.",
                )
            if event.request_id != preview_request.request_id:
                _raise_preview_persistence_contract_error(
                    session,
                    "Execution audit events must stay bound to the preview request.",
                )
            if event.source_id != preview_candidate.source_id:
                _raise_preview_persistence_contract_error(
                    session,
                    "Execution audit events must stay bound to the preview source.",
                )

        _persist_preview_audit_events(
            session,
            preview_request=preview_request,
            preview_candidate=preview_candidate,
            audit_events=audit_events,
            starting_lifecycle_order=_next_audit_lifecycle_order(
                session,
                preview_request=preview_request,
            ),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PreviewSubmissionContractError(
            "Execution audit events could not be persisted consistently."
        ) from exc


def _raise_preview_persistence_contract_error(
    session: Session,
    message: str,
) -> None:
    session.rollback()
    raise PreviewSubmissionContractError(message)


def _persist_candidate_approval_record(
    session: Session,
    *,
    preview_candidate: PreviewCandidate,
    authenticated_subject_id: str,
    session_id: str | None,
    occurred_at: datetime | None,
    candidate_state: str,
    guard_status: GuardStatus | None,
) -> None:
    existing = session.execute(
        select(PreviewCandidateApproval).where(
            PreviewCandidateApproval.candidate_id == preview_candidate.candidate_id
        )
    ).scalar_one_or_none()
    effective_occurred_at = occurred_at or datetime.now(timezone.utc)

    if existing is None:
        existing = PreviewCandidateApproval(
            approval_id=f"approval-{preview_candidate.candidate_id}",
            candidate_id=preview_candidate.candidate_id,
            preview_candidate_id=preview_candidate.id,
        )
        session.add(existing)
    elif existing.preview_candidate_id != preview_candidate.id:
        _raise_preview_persistence_contract_error(
            session,
            "Candidate approval cannot be rebound to a different preview candidate.",
        )

    if existing.approval_state == "executed":
        return

    execution_policy_version = CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY.get(
        preview_candidate.source_family
    )
    if execution_policy_version is None:
        _raise_preview_persistence_contract_error(
            session,
            "Preview candidate approval requires a backend-owned execution policy version.",
        )

    existing.request_id = preview_candidate.request_id
    existing.registered_source_id = preview_candidate.registered_source_id
    existing.source_id = preview_candidate.source_id
    existing.source_family = preview_candidate.source_family
    existing.source_flavor = preview_candidate.source_flavor
    existing.dataset_contract_version = preview_candidate.dataset_contract_version
    existing.schema_snapshot_version = preview_candidate.schema_snapshot_version
    existing.execution_policy_version = execution_policy_version
    existing.owner_subject_id = authenticated_subject_id
    existing.session_id = session_id
    if existing.approved_at is None:
        existing.approved_at = effective_occurred_at
    if existing.approval_expires_at is None:
        existing.approval_expires_at = effective_occurred_at + timedelta(minutes=5)

    if candidate_state != "preview_ready":
        existing.approval_state = "invalidated"
        existing.approved_sql = None
        existing.invalidated_at = effective_occurred_at
    elif guard_status == "allow":
        existing.approval_state = "approved"
        existing.approved_sql = preview_candidate.candidate_sql
        existing.invalidated_at = None
        existing.approval_expires_at = effective_occurred_at + timedelta(minutes=5)
    elif guard_status in {None, PREVIEW_PENDING_GUARD_STATUS}:
        existing.approval_state = "pending_guard"
        existing.approved_sql = None
        existing.invalidated_at = None
        existing.approval_expires_at = effective_occurred_at + timedelta(minutes=5)
    else:
        existing.approval_state = "invalidated"
        existing.approved_sql = None
        existing.invalidated_at = effective_occurred_at


def _persist_preview_submission_records(
    session: Session,
    *,
    payload: PreviewSubmissionRequest,
    resolved_source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
    authenticated_subject: AuthenticatedSubject,
    audit_context: PreviewAuditContext | None,
    audit_events: list[SourceAwareAuditEvent],
    candidate_sql: str | None = None,
    adapter_metadata: SQLGenerationAdapterRunMetadata | None = None,
    request_state: str = "previewed",
    candidate_state: str = "preview_ready",
) -> tuple[str, str]:
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

    for attempt in range(2):
        try:
            preview_request = session.execute(
                select(PreviewRequest).where(PreviewRequest.request_id == request_id)
            ).scalar_one_or_none()
            if preview_request is None:
                preview_request = PreviewRequest(request_id=request_id)
                session.add(preview_request)
            elif preview_request.registered_source_id != resolved_source.id:
                _raise_preview_persistence_contract_error(
                    session,
                    "Preview request cannot be rebound to a different source.",
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
            preview_request.request_state = request_state
            session.flush()

            preview_candidate = session.execute(
                select(PreviewCandidate).where(
                    PreviewCandidate.request_id == request_id,
                    PreviewCandidate.source_id == resolved_source.source_id,
                )
            ).scalar_one_or_none()
            if preview_candidate is None:
                preview_candidate = session.execute(
                    select(PreviewCandidate).where(
                        PreviewCandidate.candidate_id == candidate_id
                    )
                ).scalar_one_or_none()
                if preview_candidate is None:
                    preview_candidate = PreviewCandidate(candidate_id=candidate_id)
                    session.add(preview_candidate)
                elif (
                    preview_candidate.request_id != request_id
                    or preview_candidate.source_id != resolved_source.source_id
                ):
                    _raise_preview_persistence_contract_error(
                        session,
                        "Preview candidate cannot be rebound to a different request or source.",
                    )
            elif preview_candidate.candidate_id != candidate_id:
                _raise_preview_persistence_contract_error(
                    session,
                    "Preview candidate cannot be rebound to a different candidate.",
                )

            if (
                preview_candidate.preview_request_id is not None
                and preview_candidate.preview_request_id != preview_request.id
            ) or (
                preview_candidate.registered_source_id is not None
                and preview_candidate.registered_source_id != resolved_source.id
            ):
                _raise_preview_persistence_contract_error(
                    session,
                    "Preview candidate cannot be rebound to a different request or source.",
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
            preview_candidate.candidate_sql = candidate_sql
            preview_candidate.adapter_provider = (
                adapter_metadata.adapter_provider if adapter_metadata is not None else None
            )
            preview_candidate.adapter_model = (
                adapter_metadata.adapter_model if adapter_metadata is not None else None
            )
            preview_candidate.adapter_version = (
                adapter_metadata.adapter_version if adapter_metadata is not None else None
            )
            preview_candidate.adapter_run_id = (
                adapter_metadata.adapter_run_id if adapter_metadata is not None else None
            )
            preview_candidate.prompt_version = (
                adapter_metadata.prompt_version if adapter_metadata is not None else None
            )
            preview_candidate.prompt_fingerprint = (
                adapter_metadata.prompt_fingerprint if adapter_metadata is not None else None
            )
            preview_candidate.guard_status = PREVIEW_PENDING_GUARD_STATUS
            preview_candidate.candidate_state = candidate_state
            session.flush()
            _persist_candidate_approval_record(
                session,
                preview_candidate=preview_candidate,
                authenticated_subject_id=subject_id,
                session_id=preview_request.session_id,
                occurred_at=(
                    audit_context.occurred_at if audit_context is not None else None
                ),
                candidate_state=candidate_state,
                guard_status=preview_candidate.guard_status,
            )
            _persist_preview_audit_events(
                session,
                preview_request=preview_request,
                preview_candidate=preview_candidate,
                audit_events=audit_events,
            )
            session.commit()
            return request_id, candidate_id
        except IntegrityError as exc:
            session.rollback()
            if attempt == 0:
                continue
            raise PreviewSubmissionContractError(
                "Preview submission could not be persisted consistently."
            ) from exc


def persist_generated_candidate_audit_context(
    session: Session,
    *,
    request_id: str,
    candidate_id: str,
    candidate_sql: str,
    adapter_metadata: SQLGenerationAdapterRunMetadata,
    audit_events: list[SourceAwareAuditEvent],
    request_state: str | None = None,
    candidate_state: str | None = None,
    guard_status: GuardStatus | None = None,
) -> None:
    try:
        preview_request = session.execute(
            select(PreviewRequest).where(PreviewRequest.request_id == request_id)
        ).scalar_one_or_none()
        preview_candidate = session.execute(
            select(PreviewCandidate).where(
                PreviewCandidate.request_id == request_id,
                PreviewCandidate.candidate_id == candidate_id,
            )
        ).scalar_one_or_none()
        if preview_request is None or preview_candidate is None:
            _raise_preview_persistence_contract_error(
                session,
                "Generated candidate metadata cannot be persisted without a bound preview record.",
            )
        if preview_candidate.preview_request_id != preview_request.id:
            _raise_preview_persistence_contract_error(
                session,
                "Generated candidate metadata cannot be rebound to a different request.",
            )

        if request_state is not None:
            preview_request.request_state = request_state
        preview_candidate.candidate_sql = candidate_sql
        preview_candidate.adapter_provider = adapter_metadata.adapter_provider
        preview_candidate.adapter_model = adapter_metadata.adapter_model
        preview_candidate.adapter_version = adapter_metadata.adapter_version
        preview_candidate.adapter_run_id = adapter_metadata.adapter_run_id
        preview_candidate.prompt_version = adapter_metadata.prompt_version
        preview_candidate.prompt_fingerprint = adapter_metadata.prompt_fingerprint
        if candidate_state is not None:
            preview_candidate.candidate_state = candidate_state
        if guard_status is not None:
            preview_candidate.guard_status = guard_status
        if candidate_state is not None:
            _persist_candidate_approval_record(
                session,
                preview_candidate=preview_candidate,
                authenticated_subject_id=preview_candidate.authenticated_subject_id,
                session_id=preview_request.session_id,
                occurred_at=(
                    audit_events[-1].occurred_at if audit_events else None
                ),
                candidate_state=candidate_state,
                guard_status=guard_status,
            )
        _persist_preview_audit_events(
            session,
            preview_request=preview_request,
            preview_candidate=preview_candidate,
            audit_events=audit_events,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PreviewSubmissionContractError(
            "Generated candidate metadata could not be persisted consistently."
        ) from exc


def _persist_preview_denial_records(
    session: Session,
    *,
    payload: PreviewSubmissionRequest,
    resolved_source: RegisteredSource,
    dataset_contract: DatasetContract,
    schema_snapshot: SchemaSnapshot,
    authenticated_subject: AuthenticatedSubject,
    audit_context: PreviewAuditContext | None,
    audit_events: list[SourceAwareAuditEvent],
    request_state: str = "preview_denied",
    entitlement_decision: str = "deny",
) -> None:
    request_id = (
        audit_context.request_id
        if audit_context is not None and audit_context.request_id.strip()
        else str(uuid4())
    )
    subject_id = authenticated_subject.normalized_subject_id()
    governance_bindings = _joined_governance_bindings(
        sorted(authenticated_subject.normalized_governance_bindings())
    )

    try:
        preview_request = session.execute(
            select(PreviewRequest).where(PreviewRequest.request_id == request_id)
        ).scalar_one_or_none()
        if preview_request is None:
            preview_request = PreviewRequest(request_id=request_id)
            session.add(preview_request)
        elif preview_request.registered_source_id != resolved_source.id:
            _raise_preview_persistence_contract_error(
                session,
                "Preview request cannot be rebound to a different source.",
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
        preview_request.entitlement_decision = entitlement_decision
        preview_request.request_text = payload.question
        preview_request.request_state = request_state
        session.flush()
        _persist_preview_audit_events(
            session,
            preview_request=preview_request,
            preview_candidate=None,
            audit_events=audit_events,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PreviewSubmissionContractError(
            "Preview denial could not be persisted consistently."
        ) from exc


def submit_preview_request(
    payload: PreviewSubmissionRequest,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
    audit_context: PreviewAuditContext | None = None,
    sql_generation_adapter: SQLGenerationAdapter | None = None,
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
            _enrich_preview_audit_context(
                audit_context,
                authenticated_subject=authenticated_subject,
                dataset_contract=dataset_contract,
                entitlement_decision="deny",
            )
            audit_events = _build_preview_unavailable_audit_event(
                resolved_source=source,
                dataset_contract=dataset_contract,
                schema_snapshot=schema_snapshot,
                audit_context=audit_context,
                primary_deny_code=(
                    "DENY_SOURCE_GOVERNANCE_INVALID"
                    if isinstance(exc.__cause__, ValueError)
                    else "DENY_SOURCE_UNAVAILABLE"
                ),
                denial_cause=(
                    "source_governance_invalid"
                    if isinstance(exc.__cause__, ValueError)
                    else "source_unavailable"
                ),
            )
            _persist_preview_denial_records(
                session,
                payload=payload,
                resolved_source=source,
                dataset_contract=dataset_contract,
                schema_snapshot=schema_snapshot,
                authenticated_subject=authenticated_subject,
                audit_context=audit_context,
                audit_events=audit_events,
                request_state=(
                    "preview_malformed"
                    if isinstance(exc.__cause__, ValueError)
                    else "preview_unavailable"
                ),
            )
            raise PreviewSubmissionContractError(
                str(exc),
                public_code=(
                    "preview_source_malformed"
                    if isinstance(exc.__cause__, ValueError)
                    else "preview_source_unavailable"
                ),
                public_message=(
                    "Selected source governance is malformed."
                    if isinstance(exc.__cause__, ValueError)
                    else "Selected source is unavailable for preview."
                ),
            ) from exc
        _enrich_preview_audit_context(
            audit_context,
            authenticated_subject=authenticated_subject,
            dataset_contract=dataset_contract,
            entitlement_decision="deny",
        )
        audit_events = _build_preview_entitlement_denial_audit_event(
            resolved_source=source,
            dataset_contract=dataset_contract,
            schema_snapshot=schema_snapshot,
            audit_context=audit_context,
        )
        _persist_preview_denial_records(
            session,
            payload=payload,
            resolved_source=source,
            dataset_contract=dataset_contract,
            schema_snapshot=schema_snapshot,
            authenticated_subject=authenticated_subject,
            audit_context=audit_context,
            audit_events=audit_events,
        )
        raise PreviewSubmissionEntitlementError(
            str(exc),
            audit_events=audit_events,
        ) from exc

    _enrich_preview_audit_context(
        audit_context,
        authenticated_subject=authenticated_subject,
        dataset_contract=dataset_contract,
        entitlement_decision="allow",
    )

    candidate_sql: str | None = None
    adapter_metadata: SQLGenerationAdapterRunMetadata | None = None
    if sql_generation_adapter is not None:
        if audit_context is None:
            raise PreviewSubmissionContractError(
                "SQL generation preview requires an audit context."
            )
        try:
            prepared_context = prepare_generation_context(
                request_id=audit_context.request_id,
                question=payload.question,
                source_id=resolved_source.source_id,
                authenticated_subject=authenticated_subject,
                session=session,
            )
            adapter_request = build_sql_generation_adapter_request(prepared_context)
            adapter_response = sql_generation_adapter.generate_sql(adapter_request)
            candidate_sql = normalize_adapter_generated_sql(
                adapter_response.candidate_sql
            )
            adapter_metadata = build_sql_generation_adapter_run_metadata(
                adapter_request=adapter_request,
                adapter_response=adapter_response,
                adapter_run_id=audit_context.correlation_id,
            )
        except (
            GenerationContextPreparationError,
            SQLGenerationAdapterConfigurationError,
        ) as exc:
            failure_code = getattr(exc, "code", "sql_generation_context_unavailable")
            audit_events = _build_preview_generation_failed_audit_event(
                resolved_source=resolved_source,
                dataset_contract=dataset_contract,
                schema_snapshot=schema_snapshot,
                audit_context=audit_context,
                failure_code=failure_code,
            )
            _persist_preview_denial_records(
                session,
                payload=payload,
                resolved_source=resolved_source,
                dataset_contract=dataset_contract,
                schema_snapshot=schema_snapshot,
                authenticated_subject=authenticated_subject,
                audit_context=audit_context,
                audit_events=audit_events,
                request_state="preview_generation_failed",
                entitlement_decision="allow",
            )
            raise PreviewSubmissionContractError(
                str(exc),
                public_code="preview_generation_failed",
                public_message=(
                    "SQL generation failed before an authoritative preview "
                    "candidate was created."
                ),
            ) from exc

    audit = AuditRecord(
        source_id=resolved_source.source_id,
        state="recorded",
        events=_build_preview_lifecycle_audit_events(
            resolved_source=resolved_source,
            dataset_contract=dataset_contract,
            schema_snapshot=schema_snapshot,
            audit_context=audit_context,
            adapter_metadata=adapter_metadata,
        ),
    )
    request_id, candidate_id = _persist_preview_submission_records(
        session,
        payload=payload,
        resolved_source=resolved_source,
        dataset_contract=dataset_contract,
        schema_snapshot=schema_snapshot,
        authenticated_subject=authenticated_subject,
        audit_context=audit_context,
        audit_events=audit.events,
        candidate_sql=candidate_sql,
        adapter_metadata=adapter_metadata,
    )

    return PreviewSubmissionResponse(
        request=RequestRecord(
            question=payload.question,
            request_id=request_id,
            source_id=resolved_source.source_id,
            state="submitted",
        ),
        candidate=CandidateRecord(
            candidate_id=candidate_id,
            candidate_sql=candidate_sql,
            guard_status=PREVIEW_PENDING_GUARD_STATUS,
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
