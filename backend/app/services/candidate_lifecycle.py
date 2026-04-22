from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.features.auth.context import AuthenticatedSubject
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)
from app.services.source_governance import (
    SourceGovernanceResolutionError,
    resolve_authoritative_source_governance,
)


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


class CandidateLifecycleRevalidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    state: Literal["execution_eligible"]


class CandidateLifecycleRevalidationError(PermissionError):
    def __init__(self, *, deny_code: str, message: str) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code


def _require_aware_datetime(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CandidateLifecycleRevalidationError(
            deny_code="DENY_POLICY_VERSION_STALE",
            message=f"Candidate {field_name} must be timezone-aware.",
        )
    return value


def _raise_revalidation_error(*, deny_code: str, message: str) -> None:
    raise CandidateLifecycleRevalidationError(
        deny_code=deny_code,
        message=message,
    )


def revalidate_candidate_lifecycle(
    *,
    candidate: CandidateLifecycleRecord,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
    as_of: datetime,
    selected_source_id: str | None = None,
) -> CandidateLifecycleRevalidationResult:
    effective_as_of = _require_aware_datetime(as_of, field_name="as_of")
    approval_expires_at = _require_aware_datetime(
        candidate.approval_expires_at,
        field_name="approval_expires_at",
    )

    if selected_source_id is not None and selected_source_id != candidate.source.source_id:
        _raise_revalidation_error(
            deny_code="DENY_ENTITLEMENT_CHANGED",
            message=(
                "Candidate source binding does not match the selected source. "
                f"Expected '{candidate.source.source_id}' and received '{selected_source_id}'."
            ),
        )

    normalized_subject_id = authenticated_subject.normalized_subject_id()
    if normalized_subject_id != candidate.owner_subject_id.strip():
        _raise_revalidation_error(
            deny_code="DENY_CANDIDATE_OWNER_MISMATCH",
            message=(
                f"Candidate owner '{candidate.owner_subject_id}' does not match "
                f"authenticated subject '{normalized_subject_id}'."
            ),
        )

    if approval_expires_at <= effective_as_of:
        _raise_revalidation_error(
            deny_code="DENY_APPROVAL_EXPIRED",
            message=(
                f"Candidate approval for source '{candidate.source.source_id}' expired "
                "before lifecycle revalidation completed."
            ),
        )

    if candidate.invalidated_at is not None:
        _require_aware_datetime(candidate.invalidated_at, field_name="invalidated_at")
        _raise_revalidation_error(
            deny_code="DENY_CANDIDATE_INVALIDATED",
            message=(
                f"Candidate for source '{candidate.source.source_id}' was invalidated "
                "before lifecycle revalidation completed."
            ),
        )

    try:
        source, dataset_contract, schema_snapshot = resolve_authoritative_source_governance(
            session,
            source_id=candidate.source.source_id,
        )
    except SourceGovernanceResolutionError as exc:
        _raise_revalidation_error(
            deny_code="DENY_POLICY_VERSION_STALE",
            message=str(exc),
        )

    if source.source_family != candidate.source.source_family:
        _raise_revalidation_error(
            deny_code="DENY_POLICY_VERSION_STALE",
            message=(
                f"Candidate source family '{candidate.source.source_family}' no longer "
                f"matches authoritative source '{source.source_family}'."
            ),
        )
    if source.source_flavor != candidate.source.source_flavor:
        _raise_revalidation_error(
            deny_code="DENY_POLICY_VERSION_STALE",
            message=(
                f"Candidate source flavor '{candidate.source.source_flavor}' no longer "
                "matches the authoritative source posture."
            ),
        )
    if dataset_contract.contract_version != candidate.source.dataset_contract_version:
        _raise_revalidation_error(
            deny_code="DENY_POLICY_VERSION_STALE",
            message=(
                "Candidate dataset contract version is stale against the "
                "authoritative source-scoped governance record."
            ),
        )
    if schema_snapshot.snapshot_version != candidate.source.schema_snapshot_version:
        _raise_revalidation_error(
            deny_code="DENY_POLICY_VERSION_STALE",
            message=(
                "Candidate schema snapshot version is stale against the "
                "authoritative source-scoped governance record."
            ),
        )

    try:
        ensure_subject_is_entitled_for_source(
            authenticated_subject,
            source,
            dataset_contract,
        )
    except SourceEntitlementError as exc:
        message = str(exc)
        deny_code = (
            "DENY_POLICY_VERSION_STALE"
            if "not executable" in message
            else "DENY_ENTITLEMENT_CHANGED"
        )
        _raise_revalidation_error(
            deny_code=deny_code,
            message=message,
        )

    return CandidateLifecycleRevalidationResult(
        source_id=source.source_id,
        state="execution_eligible",
    )
