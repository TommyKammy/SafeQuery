from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.features.audit.event_model import SourceAwareAuditEvent
from app.features.auth.context import AuthenticatedSubject
from app.features.guard.deny_taxonomy import (
    DENY_APPROVAL_EXPIRED,
    DENY_CANDIDATE_INVALIDATED,
    DENY_ENTITLEMENT_CHANGED,
    DENY_POLICY_VERSION_STALE,
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
from app.services.source_registry import SourceRegistryPostureError


class SourceBoundCandidateMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_family: str
    source_flavor: Optional[str] = None
    dataset_contract_version: int
    schema_snapshot_version: int


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
        DENY_ENTITLEMENT_CHANGED: "entitlement_changed",
        DENY_POLICY_VERSION_STALE: "policy_stale",
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
    candidate_state = "invalidated" if event_type == "candidate_invalidated" else "denied"
    return SourceAwareAuditEvent(
        event_id=audit_context.event_id,
        event_type=event_type,
        occurred_at=audit_context.occurred_at,
        request_id=audit_context.request_id,
        correlation_id=audit_context.correlation_id,
        user_subject=audit_context.user_subject,
        session_id=audit_context.session_id,
        query_candidate_id=audit_context.query_candidate_id,
        candidate_owner_subject=(
            audit_context.candidate_owner_subject or candidate.owner_subject_id
        ),
        source_id=candidate.source.source_id,
        source_family=candidate.source.source_family,
        source_flavor=candidate.source.source_flavor,
        dataset_contract_version=candidate.source.dataset_contract_version,
        schema_snapshot_version=candidate.source.schema_snapshot_version,
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
    )
