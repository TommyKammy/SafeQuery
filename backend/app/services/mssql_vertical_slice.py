from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.features.audit.event_model import AuditEventType, SourceAwareAuditEvent, SourceFamily
from app.features.auth.context import AuthenticatedSubject
from app.features.execution import execute_candidate_sql, select_execution_connector
from app.features.execution.runtime import (
    ExecutableCandidateRecord,
    ExecutionAuditContext,
    ExecutionResult,
    NonEmptyTrimmedString,
    QueryRunner,
)
from app.features.guard import SQLGuardEvaluation, evaluate_mssql_sql_guard
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata
from app.services.generation_context import prepare_generation_context
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionRequest,
    PreviewSubmissionResponse,
    submit_preview_request,
)
from app.services.sql_generation_adapter import (
    SQLGenerationAdapter,
    SQLGenerationAdapterRequest,
    build_sql_generation_adapter_request,
)


MSSQL_DIALECT_PROFILE_VERSION = 1
MSSQL_EXECUTION_POLICY_VERSION = 2
MSSQL_CONNECTOR_PROFILE_VERSION = 1


def _normalize_business_mssql_connection_string(
    connection_string: str,
) -> NonEmptyTrimmedString:
    normalized = connection_string.strip()
    if not normalized:
        raise RuntimeError(
            "A non-empty backend-owned business MSSQL connection string is required "
            "before the MSSQL vertical slice can execute."
        )

    return cast(NonEmptyTrimmedString, normalized)


class GeneratedMSSQLCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: str
    source: SourceBoundCandidateMetadata


class MSSQLCoreVerticalSliceResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    preview: PreviewSubmissionResponse
    adapter_request: SQLGenerationAdapterRequest
    generated: GeneratedMSSQLCandidate
    guard: SQLGuardEvaluation
    execution: ExecutionResult
    audit_events: list[SourceAwareAuditEvent]


class MSSQLVerticalSliceDenied(PermissionError):
    def __init__(
        self,
        *,
        deny_code: str,
        message: str,
        guard: SQLGuardEvaluation,
        audit_events: list[SourceAwareAuditEvent],
    ) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code
        self.guard = guard
        self.audit_events = list(audit_events)
        self.audit_event = self.audit_events[-1] if self.audit_events else None


def _source_metadata_from_preview(
    preview: PreviewSubmissionResponse,
) -> SourceBoundCandidateMetadata:
    return SourceBoundCandidateMetadata(
        source_id=preview.candidate.source_id,
        source_family=preview.candidate.source_family,
        source_flavor=preview.candidate.source_flavor,
        dataset_contract_version=preview.candidate.dataset_contract_version,
        schema_snapshot_version=preview.candidate.schema_snapshot_version,
        execution_policy_version=MSSQL_EXECUTION_POLICY_VERSION,
        connector_profile_version=MSSQL_CONNECTOR_PROFILE_VERSION,
    )


def _audit_base(
    *,
    audit_context: PreviewAuditContext,
    candidate_source: SourceBoundCandidateMetadata,
    event_type: AuditEventType,
    causation_event_id: UUID | None,
    primary_deny_code: str | None = None,
    candidate_state: str | None = None,
    execution_row_count: int | None = None,
    result_truncated: bool | None = None,
) -> SourceAwareAuditEvent:
    return SourceAwareAuditEvent(
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
            if event_type
            in {
                "generation_completed",
                "guard_evaluated",
                "execution_requested",
                "execution_started",
                "execution_completed",
                "execution_denied",
            }
            else None
        ),
        candidate_owner_subject=(
            audit_context.candidate_owner_subject
            if event_type
            in {
                "generation_completed",
                "guard_evaluated",
                "execution_requested",
                "execution_started",
                "execution_completed",
                "execution_denied",
            }
            else None
        ),
        guard_version=(
            audit_context.guard_version if event_type == "guard_evaluated" else None
        ),
        application_version=audit_context.application_version,
        source_id=candidate_source.source_id,
        source_family=cast(SourceFamily, candidate_source.source_family),
        source_flavor=candidate_source.source_flavor,
        dialect_profile_version=MSSQL_DIALECT_PROFILE_VERSION,
        dataset_contract_version=candidate_source.dataset_contract_version,
        schema_snapshot_version=candidate_source.schema_snapshot_version,
        execution_policy_version=candidate_source.execution_policy_version,
        connector_profile_version=candidate_source.connector_profile_version,
        primary_deny_code=primary_deny_code,
        denial_cause="guard_rejected" if primary_deny_code is not None else None,
        candidate_state=candidate_state,
        execution_row_count=execution_row_count,
        result_truncated=result_truncated,
    )


def _append_audit_event(
    events: list[SourceAwareAuditEvent],
    *,
    audit_context: PreviewAuditContext,
    candidate_source: SourceBoundCandidateMetadata,
    event_type: AuditEventType,
    primary_deny_code: str | None = None,
    candidate_state: str | None = None,
    execution_row_count: int | None = None,
    result_truncated: bool | None = None,
) -> None:
    events.append(
        _audit_base(
            audit_context=audit_context,
            candidate_source=candidate_source,
            event_type=event_type,
            causation_event_id=events[-1].event_id if events else None,
            primary_deny_code=primary_deny_code,
            candidate_state=candidate_state,
            execution_row_count=execution_row_count,
            result_truncated=result_truncated,
        )
    )


def _build_execution_audit_context(
    *,
    audit_context: PreviewAuditContext,
) -> ExecutionAuditContext:
    return ExecutionAuditContext(
        event_id=uuid4(),
        occurred_at=audit_context.occurred_at,
        request_id=audit_context.request_id,
        correlation_id=audit_context.correlation_id,
        user_subject=audit_context.user_subject,
        session_id=audit_context.session_id,
        query_candidate_id=audit_context.query_candidate_id,
        candidate_owner_subject=audit_context.candidate_owner_subject,
        execution_policy_version=MSSQL_EXECUTION_POLICY_VERSION,
        connector_profile_version=MSSQL_CONNECTOR_PROFILE_VERSION,
    )


def run_mssql_core_vertical_slice(
    *,
    payload: PreviewSubmissionRequest,
    authenticated_subject: AuthenticatedSubject,
    session: Session,
    sql_generation_adapter: SQLGenerationAdapter,
    business_mssql_connection_string: NonEmptyTrimmedString,
    query_runner: QueryRunner | None = None,
    audit_context: PreviewAuditContext,
) -> MSSQLCoreVerticalSliceResult:
    normalized_business_mssql_connection_string = (
        _normalize_business_mssql_connection_string(business_mssql_connection_string)
    )

    preview = submit_preview_request(
        payload,
        authenticated_subject,
        session,
        audit_context=None,
    )
    candidate_source = _source_metadata_from_preview(preview)
    if candidate_source.source_family != "mssql":
        raise ValueError("The MSSQL core vertical slice requires an MSSQL source.")

    audit_events: list[SourceAwareAuditEvent] = []
    _append_audit_event(
        audit_events,
        audit_context=audit_context,
        candidate_source=candidate_source,
        event_type="query_submitted",
    )

    prepared_context = prepare_generation_context(
        request_id=audit_context.request_id,
        question=payload.question,
        source_id=payload.source_id,
        authenticated_subject=authenticated_subject,
        session=session,
    )
    adapter_request = build_sql_generation_adapter_request(prepared_context)
    _append_audit_event(
        audit_events,
        audit_context=audit_context,
        candidate_source=candidate_source,
        event_type="generation_requested",
    )

    canonical_sql = sql_generation_adapter.generate_sql(adapter_request)
    generated = GeneratedMSSQLCandidate(
        canonical_sql=canonical_sql,
        source=candidate_source,
    )
    _append_audit_event(
        audit_events,
        audit_context=audit_context,
        candidate_source=candidate_source,
        event_type="generation_completed",
        candidate_state="generated",
    )

    guard = evaluate_mssql_sql_guard(
        {
            "canonical_sql": canonical_sql,
            "source": {
                "source_id": candidate_source.source_id,
                "source_family": candidate_source.source_family,
                "source_flavor": candidate_source.source_flavor,
            },
        }
    )
    if guard.decision != "allow":
        primary_deny_code = guard.rejections[0].code if guard.rejections else "guard_rejected"
        _append_audit_event(
            audit_events,
            audit_context=audit_context,
            candidate_source=candidate_source,
            event_type="guard_evaluated",
            primary_deny_code=primary_deny_code,
            candidate_state="denied",
        )
        raise MSSQLVerticalSliceDenied(
            deny_code=primary_deny_code,
            message="MSSQL guard rejected the generated candidate.",
            guard=guard,
            audit_events=audit_events,
        )

    _append_audit_event(
        audit_events,
        audit_context=audit_context,
        candidate_source=candidate_source,
        event_type="guard_evaluated",
        candidate_state="preview_ready",
    )

    selection = select_execution_connector(candidate_source=candidate_source)
    execution = execute_candidate_sql(
        candidate=ExecutableCandidateRecord(
            canonical_sql=canonical_sql,
            source=candidate_source,
        ),
        selection=selection,
        business_mssql_connection_string=normalized_business_mssql_connection_string,
        query_runner=query_runner,
        audit_context=_build_execution_audit_context(audit_context=audit_context),
    )
    audit_events.extend(execution.audit_events)

    return MSSQLCoreVerticalSliceResult(
        preview=preview,
        adapter_request=adapter_request,
        generated=generated,
        guard=guard,
        execution=execution,
        audit_events=audit_events,
    )
