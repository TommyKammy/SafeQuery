from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, NonNegativeInt, PositiveInt, StringConstraints
from typing_extensions import Annotated


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SourceIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    ),
]
SourceFlavor = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    ),
]

AuditEventType = Literal[
    "query_submitted",
    "retrieval_requested",
    "retrieval_completed",
    "generation_requested",
    "generation_completed",
    "generation_failed",
    "guard_evaluated",
    "execution_requested",
    "execution_started",
    "execution_completed",
    "execution_denied",
    "execution_failed",
    "analyst_response_rendered",
    "request_rate_limited",
    "concurrency_rejected",
    "candidate_invalidated",
]

SourceFamily = Literal["mssql", "postgresql"]


class RetrievalCitationAuditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: NonEmptyTrimmedString
    asset_kind: NonEmptyTrimmedString
    citation_label: NonEmptyTrimmedString
    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    authority: Literal["advisory_context"] = "advisory_context"
    can_authorize_execution: Literal[False] = False


class ExecutedEvidenceAuditPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["executed_evidence"] = "executed_evidence"
    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: Optional[PositiveInt] = None
    connector_profile_version: Optional[PositiveInt] = None
    candidate_id: NonEmptyTrimmedString
    execution_audit_event_id: UUID
    execution_audit_event_type: Literal["execution_completed"] = "execution_completed"
    row_count: NonNegativeInt
    result_truncated: bool
    authority: Literal["backend_execution_result"] = "backend_execution_result"
    can_authorize_execution: Literal[False] = False


class SourceAwareAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: AuditEventType
    occurred_at: datetime
    request_id: NonEmptyTrimmedString
    correlation_id: NonEmptyTrimmedString
    causation_event_id: Optional[UUID] = None
    user_subject: NonEmptyTrimmedString
    session_id: NonEmptyTrimmedString
    claim_or_role_snapshot: Optional[dict[str, object]] = None
    query_candidate_id: Optional[NonEmptyTrimmedString] = None
    candidate_owner_subject: Optional[NonEmptyTrimmedString] = None
    adapter_version: Optional[NonEmptyTrimmedString] = None
    guard_version: Optional[NonEmptyTrimmedString] = None
    application_version: Optional[NonEmptyTrimmedString] = None
    retrieval_corpus_version: Optional[NonEmptyTrimmedString] = None
    retrieved_asset_ids: Optional[list[NonEmptyTrimmedString]] = None
    retrieved_citations: Optional[list[RetrievalCitationAuditPayload]] = None
    executed_evidence: Optional[list[ExecutedEvidenceAuditPayload]] = None
    analyst_mode_version: Optional[NonEmptyTrimmedString] = None

    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dialect_profile_version: Optional[PositiveInt] = None
    dataset_contract_version: Optional[PositiveInt] = None
    schema_snapshot_version: Optional[PositiveInt] = None
    execution_policy_version: Optional[PositiveInt] = None
    connector_profile_version: Optional[PositiveInt] = None
    primary_deny_code: Optional[NonEmptyTrimmedString] = None
    denial_cause: Optional[NonEmptyTrimmedString] = None
    candidate_state: Optional[NonEmptyTrimmedString] = None
    execution_row_count: Optional[int] = None
    result_truncated: Optional[bool] = None
