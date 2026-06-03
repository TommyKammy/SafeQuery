from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.preview import (
    PreviewCandidate,
    PreviewCandidateApproval,
    PreviewReviewDecision,
)
from app.features.audit.event_model import SourceAwareAuditEvent
from app.features.auth.context import AuthenticatedSubject
from app.features.guard.deny_taxonomy import (
    DENY_APPROVAL_EXPIRED,
    DENY_CANDIDATE_INVALIDATED,
    DENY_CANDIDATE_NOT_APPROVED,
    DENY_CANDIDATE_REPLAYED,
    DENY_ENTITLEMENT_CHANGED,
    DENY_POLICY_VERSION_STALE,
    DENY_REVIEW_BLOCKED,
    DENY_REVIEW_NEEDS_CLARIFICATION,
    DENY_SOURCE_ACTIVATION_POSTURE,
    DENY_SOURCE_BINDING_MISMATCH,
    DENY_SUBJECT_MISMATCH,
)
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)
from app.services.source_governance import (
    SourceGovernanceResolutionError,
    resolve_authoritative_source_governance,
)
from app.services.source_registry import (
    SourceRegistryPostureError,
    effective_source_activation_posture,
)


CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY = {
    "mssql": 2,
    "postgresql": 3,
}

CURRENT_CONNECTOR_PROFILE_VERSION_BY_SOURCE_FAMILY = {
    "mssql": 1,
    "postgresql": 1,
}


class SourceBoundCandidateMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_family: str
    source_flavor: Optional[str] = None
    dataset_contract_version: int
    semantic_contract_version: Optional[str] = None
    schema_snapshot_version: int
    execution_policy_version: Optional[int] = None
    connector_profile_version: Optional[int] = None


class CandidateLifecycleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_subject_id: str
    approved_at: datetime
    approval_expires_at: datetime
    invalidated_at: Optional[datetime] = None
    source: SourceBoundCandidateMetadata


class CandidateLifecycleAuditContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    occurred_at: datetime
    request_id: str
    correlation_id: str
    user_subject: str
    session_id: str
    query_candidate_id: Optional[str] = None
    candidate_owner_subject: Optional[str] = None


class CandidateLifecycleRevalidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    state: Literal["execution_eligible"]
    source: SourceBoundCandidateMetadata
    approved_sql: Optional[str] = None


class CandidateLifecycleRevalidationError(PermissionError):
    def __init__(
        self,
        *,
        deny_code: str,
        message: str,
        audit_event: SourceAwareAuditEvent | None = None,
    ) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code
        self.audit_event = audit_event


def _denial_cause_for_code(deny_code: str) -> str:
    return {
        DENY_APPROVAL_EXPIRED: "approval_expired",
        DENY_CANDIDATE_INVALIDATED: "candidate_invalidated",
        DENY_CANDIDATE_NOT_APPROVED: "candidate_not_approved",
        DENY_CANDIDATE_REPLAYED: "candidate_replayed",
        DENY_ENTITLEMENT_CHANGED: "entitlement_changed",
        DENY_POLICY_VERSION_STALE: "policy_stale",
        DENY_REVIEW_BLOCKED: "review_blocked",
        DENY_REVIEW_NEEDS_CLARIFICATION: "review_needs_clarification",
        DENY_SOURCE_ACTIVATION_POSTURE: "source_activation_posture",
        DENY_SOURCE_BINDING_MISMATCH: "source_binding_mismatch",
        DENY_SUBJECT_MISMATCH: "subject_mismatch",
    }.get(deny_code, "execution_denied")


def _build_revalidation_audit_event(
    *,
    deny_code: str,
    candidate: CandidateLifecycleRecord,
    audit_context: CandidateLifecycleAuditContext | None,
) -> SourceAwareAuditEvent | None:
    if audit_context is None:
        return None

    event_type = (
        "candidate_invalidated"
        if deny_code == DENY_CANDIDATE_INVALIDATED
        else "execution_denied"
    )
    candidate_state = (
        "invalidated"
        if event_type == "candidate_invalidated"
        else "replayed" if deny_code == DENY_CANDIDATE_REPLAYED else "denied"
    )
    return SourceAwareAuditEvent(
        event_id=audit_context.event_id,
        event_type=event_type,
        occurred_at=audit_context.occurred_at,
        request_id=audit_context.request_id,
        correlation_id=audit_context.correlation_id,
        user_subject=audit_context.user_subject,
        session_id=audit_context.session_id,
        query_candidate_id=audit_context.query_candidate_id,
        candidate_owner_subject=candidate.owner_subject_id,
        source_id=candidate.source.source_id,
        source_family=candidate.source.source_family,
        source_flavor=candidate.source.source_flavor,
        dataset_contract_version=candidate.source.dataset_contract_version,
        schema_snapshot_version=candidate.source.schema_snapshot_version,
        execution_policy_version=candidate.source.execution_policy_version,
        connector_profile_version=candidate.source.connector_profile_version,
        primary_deny_code=deny_code,
        denial_cause=_denial_cause_for_code(deny_code),
        candidate_state=candidate_state,
    )


def _require_aware_datetime(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CandidateLifecycleRevalidationError(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=f"Candidate {field_name} must be timezone-aware.",
        )
    return value


def _raise_revalidation_error(
    *,
    deny_code: str,
    message: str,
    candidate: CandidateLifecycleRecord,
    audit_context: CandidateLifecycleAuditContext | None,
) -> None:
    raise CandidateLifecycleRevalidationError(
        deny_code=deny_code,
        message=message,
        audit_event=_build_revalidation_audit_event(
            deny_code=deny_code,
            candidate=candidate,
            audit_context=audit_context,
        ),
    )


def revalidate_candidate_lifecycle(
    *,
    candidate: CandidateLifecycleRecord,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
    as_of: datetime,
    selected_source_id: str | None = None,
    audit_context: CandidateLifecycleAuditContext | None = None,
) -> CandidateLifecycleRevalidationResult:
    effective_as_of = _require_aware_datetime(as_of, field_name="as_of")
    approval_expires_at = _require_aware_datetime(
        candidate.approval_expires_at,
        field_name="approval_expires_at",
    )

    if selected_source_id is not None and selected_source_id != candidate.source.source_id:
        _raise_revalidation_error(
            deny_code=DENY_SOURCE_BINDING_MISMATCH,
            message=(
                "Candidate source binding does not match the selected source. "
                f"Expected '{candidate.source.source_id}' and received '{selected_source_id}'."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )

    normalized_subject_id = authenticated_subject.normalized_subject_id()
    if normalized_subject_id != candidate.owner_subject_id.strip():
        _raise_revalidation_error(
            deny_code=DENY_SUBJECT_MISMATCH,
            message=(
                f"Candidate owner '{candidate.owner_subject_id}' does not match "
                f"authenticated subject '{normalized_subject_id}'."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )

    if approval_expires_at <= effective_as_of:
        _raise_revalidation_error(
            deny_code=DENY_APPROVAL_EXPIRED,
            message=(
                f"Candidate approval for source '{candidate.source.source_id}' expired "
                "before lifecycle revalidation completed."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )

    if candidate.invalidated_at is not None:
        invalidated_at = _require_aware_datetime(
            candidate.invalidated_at,
            field_name="invalidated_at",
        )
        if invalidated_at <= effective_as_of:
            _raise_revalidation_error(
                deny_code=DENY_CANDIDATE_INVALIDATED,
                message=(
                    f"Candidate for source '{candidate.source.source_id}' was invalidated "
                    "before lifecycle revalidation completed."
                ),
                candidate=candidate,
                audit_context=audit_context,
            )

    try:
        source, dataset_contract, schema_snapshot = resolve_authoritative_source_governance(
            session,
            source_id=candidate.source.source_id,
        )
    except SourceGovernanceResolutionError as exc:
        _raise_revalidation_error(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=str(exc),
            candidate=candidate,
            audit_context=audit_context,
        )

    effective_activation_posture = effective_source_activation_posture(source)
    if not effective_activation_posture.is_executable:
        _raise_revalidation_error(
            deny_code=DENY_SOURCE_ACTIVATION_POSTURE,
            message=(
                f"Registered source '{source.source_id}' is not executable while in "
                f"{effective_activation_posture.value} posture."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )

    if source.source_family != candidate.source.source_family:
        _raise_revalidation_error(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=(
                f"Candidate source family '{candidate.source.source_family}' no longer "
                f"matches authoritative source '{source.source_family}'."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )
    if source.source_flavor != candidate.source.source_flavor:
        _raise_revalidation_error(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=(
                f"Candidate source flavor '{candidate.source.source_flavor}' no longer "
                "matches the authoritative source posture."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )
    if dataset_contract.contract_version != candidate.source.dataset_contract_version:
        _raise_revalidation_error(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=(
                "Candidate dataset contract version is stale against the "
                "authoritative source-scoped governance record."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )
    if schema_snapshot.snapshot_version != candidate.source.schema_snapshot_version:
        _raise_revalidation_error(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=(
                "Candidate schema snapshot version is stale against the "
                "authoritative source-scoped governance record."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )

    current_execution_policy_version = CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY.get(
        source.source_family
    )
    if current_execution_policy_version is None:
        _raise_revalidation_error(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=(
                "No backend-owned execution policy version is configured for "
                f"source family '{source.source_family}'."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )
    if candidate.source.execution_policy_version != current_execution_policy_version:
        _raise_revalidation_error(
            deny_code=DENY_POLICY_VERSION_STALE,
            message=(
                "Candidate execution policy version is stale against the "
                "backend-owned source-family policy."
            ),
            candidate=candidate,
            audit_context=audit_context,
        )

    try:
        ensure_subject_is_entitled_for_source(
            authenticated_subject,
            source,
            dataset_contract,
        )
    except SourceEntitlementError as exc:
        message = str(exc)
        cause = exc.__cause__
        deny_code = (
            DENY_POLICY_VERSION_STALE
            if isinstance(cause, (SourceRegistryPostureError, ValueError))
            else DENY_ENTITLEMENT_CHANGED
        )
        _raise_revalidation_error(
            deny_code=deny_code,
            message=message,
            candidate=candidate,
            audit_context=audit_context,
        )

    return CandidateLifecycleRevalidationResult(
        source_id=source.source_id,
        state="execution_eligible",
        source=candidate.source,
    )


def _persisted_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _raise_authoritative_approval_error(
    *,
    deny_code: str,
    message: str,
    approval: PreviewCandidateApproval | None,
    audit_context: CandidateLifecycleAuditContext | None,
    candidate: CandidateLifecycleRecord | None = None,
) -> None:
    candidate_record = candidate or CandidateLifecycleRecord(
        owner_subject_id=(
            approval.owner_subject_id if approval is not None else "unknown"
        ),
        approved_at=(
            _persisted_datetime(approval.approved_at)
            if approval is not None
            else datetime.now(timezone.utc)
        ),
        approval_expires_at=(
            _persisted_datetime(approval.approval_expires_at)
            if approval is not None
            else datetime.now(timezone.utc)
        ),
        invalidated_at=(
            _persisted_datetime(approval.invalidated_at)
            if approval is not None and approval.invalidated_at is not None
            else None
        ),
        source=SourceBoundCandidateMetadata(
            source_id=approval.source_id if approval is not None else "unknown",
            source_family=approval.source_family if approval is not None else "unknown",
            source_flavor=approval.source_flavor if approval is not None else None,
            dataset_contract_version=(
                approval.dataset_contract_version if approval is not None else 0
            ),
            semantic_contract_version=None,
            schema_snapshot_version=(
                approval.schema_snapshot_version if approval is not None else 0
            ),
            execution_policy_version=(
                approval.execution_policy_version if approval is not None else None
            ),
            connector_profile_version=(
                CURRENT_CONNECTOR_PROFILE_VERSION_BY_SOURCE_FAMILY.get(
                    approval.source_family
                )
                if approval is not None
                else None
            ),
        ),
    )
    _raise_revalidation_error(
        deny_code=deny_code,
        message=message,
        candidate=candidate_record,
        audit_context=audit_context,
    )


def _candidate_lifecycle_from_preview_candidate(
    preview_candidate: PreviewCandidate,
) -> CandidateLifecycleRecord:
    return CandidateLifecycleRecord(
        owner_subject_id=preview_candidate.authenticated_subject_id,
        approved_at=datetime.now(timezone.utc),
        approval_expires_at=datetime.now(timezone.utc),
        source=SourceBoundCandidateMetadata(
            source_id=preview_candidate.source_id,
            source_family=preview_candidate.source_family,
            source_flavor=preview_candidate.source_flavor,
            dataset_contract_version=preview_candidate.dataset_contract_version,
            semantic_contract_version=preview_candidate.semantic_contract_version,
            schema_snapshot_version=preview_candidate.schema_snapshot_version,
            execution_policy_version=(
                CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY.get(
                    preview_candidate.source_family
                )
            ),
            connector_profile_version=(
                CURRENT_CONNECTOR_PROFILE_VERSION_BY_SOURCE_FAMILY.get(
                    preview_candidate.source_family
                )
            ),
        ),
    )


def _candidate_lifecycle_from_approval(
    approval: PreviewCandidateApproval,
) -> CandidateLifecycleRecord:
    return CandidateLifecycleRecord(
        owner_subject_id=approval.owner_subject_id,
        approved_at=_persisted_datetime(approval.approved_at),
        approval_expires_at=_persisted_datetime(approval.approval_expires_at),
        invalidated_at=(
            _persisted_datetime(approval.invalidated_at)
            if approval.invalidated_at is not None
            else None
        ),
        source=SourceBoundCandidateMetadata(
            source_id=approval.source_id,
            source_family=approval.source_family,
            source_flavor=approval.source_flavor,
            dataset_contract_version=approval.dataset_contract_version,
            semantic_contract_version=None,
            schema_snapshot_version=approval.schema_snapshot_version,
            execution_policy_version=approval.execution_policy_version,
            connector_profile_version=(
                CURRENT_CONNECTOR_PROFILE_VERSION_BY_SOURCE_FAMILY.get(
                    approval.source_family
                )
            ),
        ),
    )


def _approved_sql_from_approval(
    approval: PreviewCandidateApproval,
    *,
    audit_context: CandidateLifecycleAuditContext | None,
) -> str:
    if not isinstance(approval.approved_sql, str) or not approval.approved_sql.strip():
        _raise_authoritative_approval_error(
            deny_code=DENY_CANDIDATE_NOT_APPROVED,
            message="Candidate approval snapshot is unavailable for execution.",
            approval=approval,
            audit_context=audit_context,
        )
    return approval.approved_sql


def _deny_if_review_blocks_execution(
    *,
    session: Session,
    approval: PreviewCandidateApproval,
    audit_context: CandidateLifecycleAuditContext | None,
) -> None:
    review_decision = session.scalar(
        select(PreviewReviewDecision).where(
            PreviewReviewDecision.preview_candidate_id == approval.preview_candidate_id
        )
    )
    review_status = review_decision.review_status if review_decision is not None else None
    if review_status == "blocked":
        _raise_authoritative_approval_error(
            deny_code=DENY_REVIEW_BLOCKED,
            message="Review LLM blocked this candidate before execution.",
            approval=approval,
            audit_context=audit_context,
        )
    if review_status == "needs_clarification":
        _raise_authoritative_approval_error(
            deny_code=DENY_REVIEW_NEEDS_CLARIFICATION,
            message="Review LLM requires clarification before execution.",
            approval=approval,
            audit_context=audit_context,
        )


def revalidate_authoritative_candidate_approval(
    *,
    session: Session,
    candidate_id: str,
    authenticated_subject: AuthenticatedSubject,
    as_of: datetime,
    selected_source_id: str | None = None,
    audit_context: CandidateLifecycleAuditContext | None = None,
    mark_executed: bool = True,
    before_mark_executed: (
        Callable[[CandidateLifecycleRevalidationResult], None] | None
    ) = None,
) -> CandidateLifecycleRevalidationResult:
    approval = (
        session.execute(
            select(PreviewCandidateApproval)
            .join(
                PreviewCandidate,
                PreviewCandidate.id == PreviewCandidateApproval.preview_candidate_id,
            )
            .where(PreviewCandidateApproval.candidate_id == candidate_id)
            .with_for_update()
        )
        .scalars()
        .one_or_none()
    )
    if approval is None:
        preview_candidate = session.scalar(
            select(PreviewCandidate).where(PreviewCandidate.candidate_id == candidate_id)
        )
        _raise_authoritative_approval_error(
            deny_code=DENY_CANDIDATE_NOT_APPROVED,
            message="Candidate has no authoritative preview approval record.",
            approval=None,
            audit_context=audit_context,
            candidate=(
                _candidate_lifecycle_from_preview_candidate(preview_candidate)
                if preview_candidate is not None
                else None
            ),
        )

    assert approval is not None
    preview_candidate = session.get(PreviewCandidate, approval.preview_candidate_id)
    if preview_candidate is None or preview_candidate.candidate_state != "preview_ready":
        _raise_authoritative_approval_error(
            deny_code=DENY_CANDIDATE_NOT_APPROVED,
            message="Candidate is not in an authoritative preview-ready state.",
            approval=approval,
            audit_context=audit_context,
        )
    if preview_candidate.guard_status != "allow":
        _raise_authoritative_approval_error(
            deny_code=DENY_CANDIDATE_NOT_APPROVED,
            message="Candidate SQL Guard status is not execution-eligible.",
            approval=approval,
            audit_context=audit_context,
        )

    if approval.approval_state == "executed" or approval.executed_at is not None:
        _raise_authoritative_approval_error(
            deny_code=DENY_CANDIDATE_REPLAYED,
            message="Candidate approval has already been consumed for execution.",
            approval=approval,
            audit_context=audit_context,
        )
    if approval.approval_state == "invalidated" or approval.invalidated_at is not None:
        _raise_authoritative_approval_error(
            deny_code=DENY_CANDIDATE_INVALIDATED,
            message="Candidate approval was invalidated before execution.",
            approval=approval,
            audit_context=audit_context,
        )
    if approval.approval_state != "approved":
        _raise_authoritative_approval_error(
            deny_code=DENY_CANDIDATE_NOT_APPROVED,
            message="Candidate approval is not eligible for execution.",
            approval=approval,
            audit_context=audit_context,
        )
    approved_sql = _approved_sql_from_approval(
        approval,
        audit_context=audit_context,
    )
    _deny_if_review_blocks_execution(
        session=session,
        approval=approval,
        audit_context=audit_context,
    )

    result = revalidate_candidate_lifecycle(
        candidate=_candidate_lifecycle_from_approval(approval),
        authenticated_subject=authenticated_subject,
        session=session,
        as_of=as_of,
        selected_source_id=selected_source_id,
        audit_context=audit_context,
    )
    result = result.model_copy(update={"approved_sql": approved_sql})
    if before_mark_executed is not None:
        before_mark_executed(result)
    if mark_executed:
        approval.executed_at = _persisted_datetime(as_of)
        approval.approval_state = "executed"
        session.add(approval)
        session.commit()
    return result
