from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import (
    PreviewAuditEvent,
    PreviewCandidate,
    PreviewCandidateApproval,
    PreviewRequest,
)
from app.db.models.schema_snapshot import SchemaSnapshot
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.guard.deny_taxonomy import DENY_RESULT_VALIDATION_FAILED
from app.services.first_run_doctor import _alembic_heads
from app.services.health import build_operator_health
from app.services.operator_workflow import (
    OperatorWorkflowGovernanceBindingStatus,
    get_operator_workflow_snapshot,
)


_APP_VERSION = "0.1.0"
_WINDOWS_USER_PROFILE_SEGMENT = "Users"
_FORBIDDEN_EXPORT_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "connection-string-like values",
        re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s\"']+"),
    ),
    (
        "connection-string-like values",
        re.compile(r"(?i)\b(driver|server|database|uid|pwd)\s*="),
    ),
    (
        "token-like values",
        re.compile(
            r"(?i)\b(?:sk|pk|ghp|github_pat)[_-][a-z0-9][a-z0-9_-]{8,}"
        ),
    ),
    (
        "token-like values",
        re.compile(
            r"(?i)\b(?:access[_-]?token|refresh[_-]?token|id[_-]?token|token)\s*[:=]"
        ),
    ),
    (
        "raw credential names",
        re.compile(
            r"(?i)(^|[^a-z0-9])"
            r"(?:password|passwd|pwd|credential|client[_-]?secret|"
            r"api[_-]?key|private[_-]?key)\b"
        ),
    ),
    (
        "workstation-local paths",
        re.compile(r"(?i)(^|[\\/])Users[\\/][^\\/\"]+"),
    ),
    (
        "workstation-local paths",
        re.compile(rf"(?i)[a-z]:\\{_WINDOWS_USER_PROFILE_SEGMENT}\\[^\\\"]+"),
    ),
)
_IDENTITY_EXPORT_FIELD_NAMES = frozenset(
    {
        "authenticatedSubjectId",
        "ownerSubjectId",
    }
)


class SupportBundleApplication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["safequery-api"] = "safequery-api"
    version: str
    environment: str


class SupportBundleMigrationPosture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["current", "outdated", "unknown"]
    detail: str
    applied_revisions: list[str] = Field(
        default_factory=list,
        serialization_alias="appliedRevisions",
    )
    expected_heads: list[str] = Field(
        default_factory=list,
        serialization_alias="expectedHeads",
    )


class SupportBundleSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(serialization_alias="sourceId")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")
    activation_posture: str = Field(serialization_alias="activationPosture")
    dataset_contract_version: Optional[int] = Field(
        default=None,
        serialization_alias="datasetContractVersion",
    )
    schema_snapshot_version: Optional[int] = Field(
        default=None,
        serialization_alias="schemaSnapshotVersion",
    )
    governance_bindings: list[OperatorWorkflowGovernanceBindingStatus] = Field(
        default_factory=list,
        serialization_alias="governanceBindings",
    )


class SupportBundleHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    components: dict[str, object]


class SupportBundleRecentWorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_type: str = Field(serialization_alias="itemType")
    lifecycle_state: str = Field(serialization_alias="lifecycleState")
    source_id: str = Field(serialization_alias="sourceId")


class SupportBundleWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_count: int = Field(serialization_alias="historyCount")
    recent_states: list[SupportBundleRecentWorkflowState] = Field(
        serialization_alias="recentStates"
    )
    lifecycle_metrics: dict[str, object] = Field(serialization_alias="lifecycleMetrics")


class SupportBundleAuditCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["present", "empty", "error"]
    recorded_events: int = Field(serialization_alias="recordedEvents")
    sources_with_events: int = Field(serialization_alias="sourcesWithEvents")


class SupportBundleRedaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excluded: list[str]


class BoundedResultSummaryRequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(serialization_alias="requestId")
    request_state: str = Field(serialization_alias="requestState")


class BoundedResultSummaryCandidateContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(serialization_alias="candidateId")
    candidate_state: str = Field(serialization_alias="candidateState")
    guard_status: str = Field(serialization_alias="guardStatus")


class BoundedResultSummaryRunContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_run_id: str = Field(serialization_alias="executionRunId")
    event_type: Literal["execution_completed"] = Field(serialization_alias="eventType")
    occurred_at: datetime = Field(serialization_alias="occurredAt")


class BoundedResultSummarySourceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(serialization_alias="sourceId")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")
    dataset_contract_version: int = Field(serialization_alias="datasetContractVersion")
    schema_snapshot_version: int = Field(serialization_alias="schemaSnapshotVersion")


class BoundedResultSummaryAuditContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_event_id: str = Field(serialization_alias="auditEventId")
    correlation_id: str = Field(serialization_alias="correlationId")
    lifecycle_order: int = Field(serialization_alias="lifecycleOrder")


class BoundedResultSummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_kind: Literal["aggregate_only", "bounded_rows"] = Field(
        serialization_alias="summaryKind",
    )
    row_count: int = Field(serialization_alias="rowCount")
    result_truncated: bool = Field(serialization_alias="resultTruncated")
    bounded_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        serialization_alias="boundedRows",
    )
    bounded_row_count: int = Field(serialization_alias="boundedRowCount")
    bounded_row_limit: int = Field(serialization_alias="boundedRowLimit")


class BoundedResultSummaryExport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_version: Literal[1] = Field(default=1, serialization_alias="exportVersion")
    export_type: Literal["bounded_result_summary"] = Field(
        default="bounded_result_summary",
        serialization_alias="exportType",
    )
    generated_at: datetime = Field(serialization_alias="generatedAt")
    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    request: BoundedResultSummaryRequestContext
    candidate: BoundedResultSummaryCandidateContext
    run: BoundedResultSummaryRunContext
    source: BoundedResultSummarySourceContext
    audit: BoundedResultSummaryAuditContext
    result: BoundedResultSummaryResult
    limitations: list[str]
    redaction: SupportBundleRedaction


class GovernanceReviewLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(serialization_alias="eventType")
    occurred_at: datetime = Field(serialization_alias="occurredAt")
    lifecycle_order: int = Field(serialization_alias="lifecycleOrder")
    candidate_state: Optional[str] = Field(
        default=None,
        serialization_alias="candidateState",
    )
    authority: Literal["safequery_control_plane"] = "safequery_control_plane"


class GovernanceReviewActorEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    authenticated_subject_id: str = Field(serialization_alias="authenticatedSubjectId")
    auth_source: Optional[str] = Field(default=None, serialization_alias="authSource")
    governance_bindings: list[str] = Field(serialization_alias="governanceBindings")
    entitlement_decision: str = Field(serialization_alias="entitlementDecision")


class GovernanceReviewAdapterEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["subordinate_adapter"] = "subordinate_adapter"
    adapter_provider: Optional[str] = Field(
        default=None,
        serialization_alias="adapterProvider",
    )
    adapter_model: Optional[str] = Field(default=None, serialization_alias="adapterModel")
    adapter_version: Optional[str] = Field(
        default=None,
        serialization_alias="adapterVersion",
    )
    adapter_run_id: Optional[str] = Field(default=None, serialization_alias="adapterRunId")
    prompt_version: Optional[str] = Field(default=None, serialization_alias="promptVersion")
    prompt_fingerprint: Optional[str] = Field(
        default=None,
        serialization_alias="promptFingerprint",
    )


class GovernanceReviewRequestEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    request_state: str = Field(serialization_alias="requestState")
    request_text: Literal["[redacted_request_text]"] = Field(
        default="[redacted_request_text]",
        serialization_alias="requestText",
    )
    request_text_redaction: Literal["raw_request_text_excluded"] = Field(
        default="raw_request_text_excluded",
        serialization_alias="requestTextRedaction",
    )
    semantic_contract_version: Optional[str] = Field(
        default=None,
        serialization_alias="semanticContractVersion",
    )


class GovernanceReviewSemanticMappingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    status: str
    intent: Optional[str] = None
    metric: Optional[str] = None
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    insufficient_evidence_reason: Optional[str] = Field(
        default=None,
        serialization_alias="insufficientEvidenceReason",
    )
    clarification: Optional[str] = None
    unsupported_concepts: Optional[list[str]] = Field(
        default=None,
        serialization_alias="unsupportedConcepts",
    )


class GovernanceReviewSqlCandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    candidate_sql_redaction: Literal["raw_sql_excluded"] = Field(
        default="raw_sql_excluded",
        serialization_alias="candidateSqlRedaction",
    )
    release_gate_scenario_id: Optional[str] = Field(
        default=None,
        serialization_alias="releaseGateScenarioId",
    )


class GovernanceReviewGuardDecisionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    decision: str
    guard_version: Optional[str] = Field(
        default=None,
        serialization_alias="guardVersion",
    )
    guard_audit_event_id: str = Field(serialization_alias="guardAuditEventId")


class GovernanceReviewCandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    candidate_state: str = Field(serialization_alias="candidateState")
    guard_status: str = Field(serialization_alias="guardStatus")
    sql_candidate: GovernanceReviewSqlCandidateEvidence = Field(
        serialization_alias="sqlCandidate",
    )
    guard_decision: Optional[GovernanceReviewGuardDecisionEvidence] = Field(
        default=None,
        serialization_alias="guardDecision",
    )
    adapter_evidence: GovernanceReviewAdapterEvidence = Field(
        serialization_alias="adapterEvidence",
    )


class GovernanceReviewApprovalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    approval_id: str = Field(serialization_alias="approvalId")
    approval_state: str = Field(serialization_alias="approvalState")
    owner_subject_id: str = Field(serialization_alias="ownerSubjectId")
    approved_at: datetime = Field(serialization_alias="approvedAt")
    approval_expires_at: datetime = Field(serialization_alias="approvalExpiresAt")
    invalidated_at: Optional[datetime] = Field(
        default=None,
        serialization_alias="invalidatedAt",
    )
    executed_at: Optional[datetime] = Field(default=None, serialization_alias="executedAt")
    execution_policy_version: int = Field(serialization_alias="executionPolicyVersion")


class GovernanceReviewExecuteResultEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    event_type: str = Field(serialization_alias="eventType")
    occurred_at: datetime = Field(serialization_alias="occurredAt")
    row_count: Optional[int] = Field(default=None, serialization_alias="rowCount")
    result_truncated: Optional[bool] = Field(
        default=None,
        serialization_alias="resultTruncated",
    )
    validation: Optional["GovernanceReviewValidationEvidence"] = None
    redaction: Optional["GovernanceReviewRedactionEvidence"] = None
    answer: Optional["GovernanceReviewAnswerEvidence"] = None


class GovernanceReviewValidationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    status: str
    reason_codes: list[str] = Field(
        default_factory=list,
        serialization_alias="reasonCodes",
    )
    row_limit: Optional[int] = Field(default=None, serialization_alias="rowLimit")
    rows_used: Optional[int] = Field(default=None, serialization_alias="rowsUsed")


class GovernanceReviewRedactionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    status: str
    redacted_columns: list[str] = Field(
        default_factory=list,
        serialization_alias="redactedColumns",
    )


class GovernanceReviewAnswerEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    answer_state: str = Field(serialization_alias="answerState")
    summary_strategy: str = Field(serialization_alias="summaryStrategy")
    answer_evidence_id: str = Field(serialization_alias="answerEvidenceId")
    execution_run_id: str = Field(serialization_alias="executionRunId")
    insufficient_evidence_reason: Optional[str] = Field(
        default=None,
        serialization_alias="insufficientEvidenceReason",
    )


class GovernanceReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    record_type: Literal["workflow_lifecycle"] = Field(
        default="workflow_lifecycle",
        serialization_alias="recordType",
    )
    request_id: str = Field(serialization_alias="requestId")
    candidate_id: Optional[str] = Field(default=None, serialization_alias="candidateId")
    source_id: str = Field(serialization_alias="sourceId")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")
    dataset_contract_version: int = Field(serialization_alias="datasetContractVersion")
    schema_snapshot_version: int = Field(serialization_alias="schemaSnapshotVersion")
    request: GovernanceReviewRequestEvidence
    semantic_mapping: Optional[GovernanceReviewSemanticMappingEvidence] = Field(
        default=None,
        serialization_alias="semanticMapping",
    )
    lifecycle: list[GovernanceReviewLifecycleEvent]
    actor: GovernanceReviewActorEvidence
    candidate: Optional[GovernanceReviewCandidateEvidence] = None
    review: Optional[GovernanceReviewApprovalEvidence] = None
    execute_result: Optional[GovernanceReviewExecuteResultEvidence] = Field(
        default=None,
        serialization_alias="executeResult",
    )


class GovernanceReviewBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    evidence: list[GovernanceReviewEvidence]
    limitations: list[str]


class SupportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_version: Literal[1] = Field(default=1, serialization_alias="bundleVersion")
    generated_at: datetime = Field(serialization_alias="generatedAt")
    application: SupportBundleApplication
    source_posture: dict[str, object] = Field(serialization_alias="sourcePosture")
    migration_posture: SupportBundleMigrationPosture = Field(
        serialization_alias="migrationPosture"
    )
    active_sources: list[SupportBundleSource] = Field(
        serialization_alias="activeSources"
    )
    health: SupportBundleHealth
    workflow: SupportBundleWorkflow
    audit_completeness: SupportBundleAuditCompleteness = Field(
        serialization_alias="auditCompleteness"
    )
    governance_review: GovernanceReviewBundle = Field(
        serialization_alias="governanceReview",
    )
    redaction: SupportBundleRedaction


_BOUNDED_RESULT_SUMMARY_ROW_LIMIT = 20


def _active_sources(session: Session) -> list[SupportBundleSource]:
    workflow_snapshot = get_operator_workflow_snapshot(session)
    sources_by_id = {
        source.source_id: source
        for source in workflow_snapshot.sources
        if source.activation_posture == SourceActivationPosture.ACTIVE.value
    }
    sources = session.scalars(
        select(RegisteredSource)
        .where(RegisteredSource.source_id.in_(sources_by_id))
        .order_by(RegisteredSource.source_id)
    )
    bundle_sources: list[SupportBundleSource] = []
    for source in sources:
        contract = (
            session.get(DatasetContract, source.dataset_contract_id)
            if source.dataset_contract_id is not None
            else None
        )
        snapshot = (
            session.get(SchemaSnapshot, source.schema_snapshot_id)
            if source.schema_snapshot_id is not None
            else None
        )
        bundle_sources.append(
            SupportBundleSource(
                source_id=source.source_id,
                source_family=source.source_family,
                source_flavor=source.source_flavor,
                activation_posture=source.activation_posture.value,
                dataset_contract_version=(
                    contract.contract_version if contract is not None else None
                ),
                schema_snapshot_version=(
                    snapshot.snapshot_version if snapshot is not None else None
                ),
                governance_bindings=sources_by_id[
                    source.source_id
                ].governance_bindings,
            )
        )
    return bundle_sources


def _migration_posture(session: Session) -> SupportBundleMigrationPosture:
    try:
        applied_revisions = sorted(
            str(row[0])
            for row in session.execute(text("SELECT version_num FROM alembic_version"))
        )
    except SQLAlchemyError as exc:
        return SupportBundleMigrationPosture(
            status="unknown",
            detail=exc.__class__.__name__,
        )

    try:
        expected_heads = sorted(_alembic_heads())
    except Exception as exc:
        return SupportBundleMigrationPosture(
            status="unknown",
            detail=exc.__class__.__name__,
            applied_revisions=applied_revisions,
        )

    if applied_revisions == expected_heads:
        return SupportBundleMigrationPosture(
            status="current",
            detail="alembic_head_current",
            applied_revisions=applied_revisions,
            expected_heads=expected_heads,
        )
    return SupportBundleMigrationPosture(
        status="outdated",
        detail="alembic_head_mismatch",
        applied_revisions=applied_revisions,
        expected_heads=expected_heads,
    )


def _recent_workflow_states(
    session: Session,
    *,
    limit: int = 8,
) -> tuple[int, list[SupportBundleRecentWorkflowState]]:
    snapshot = get_operator_workflow_snapshot(session)
    return len(snapshot.history), [
        SupportBundleRecentWorkflowState(
            item_type=item.item_type,
            lifecycle_state=item.lifecycle_state,
            source_id=item.source_id,
        )
        for item in snapshot.history[:limit]
    ]


def _audit_completeness(metrics: Mapping[str, object]) -> SupportBundleAuditCompleteness:
    audit_persistence = metrics.get("audit_persistence")
    if not isinstance(audit_persistence, dict):
        return SupportBundleAuditCompleteness(
            status="error",
            recorded_events=0,
            sources_with_events=0,
        )

    recorded_events = audit_persistence.get("recorded_events")
    sources_with_events = audit_persistence.get("sources_with_events")
    recorded_event_count = recorded_events if isinstance(recorded_events, int) else 0
    source_count = sources_with_events if isinstance(sources_with_events, int) else 0
    return SupportBundleAuditCompleteness(
        status="present" if recorded_event_count else "empty",
        recorded_events=recorded_event_count,
        sources_with_events=source_count,
    )


def _redaction_policy() -> SupportBundleRedaction:
    return SupportBundleRedaction(
        excluded=[
            "connection_strings",
            "raw_credentials",
            "tokens",
            "raw_request_text",
            "raw_result_rows",
            "deterministic_result_hashes",
            "candidate_sql",
            "raw_identity_payloads",
            "workstation_local_paths",
            "source_connection_references",
        ]
    )


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _split_bindings(value: str | None) -> list[str]:
    if not isinstance(value, str):
        return []
    return sorted(item.strip() for item in value.split(",") if item.strip())


def _audit_event_sort_key(event: PreviewAuditEvent) -> tuple[datetime, int, str]:
    return (
        _as_utc_datetime(event.occurred_at),
        event.lifecycle_order,
        str(event.event_id),
    )


def _payload_non_negative_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def _payload_bool(payload: Mapping[str, object], key: str) -> bool | None:
    value = payload.get(key)
    return value if isinstance(value, bool) else None


def _payload_mapping(
    payload: Mapping[str, object],
    key: str,
) -> Mapping[str, object] | None:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else None


def _payload_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _payload_string_list(
    payload: Mapping[str, object],
    key: str,
) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _split_csv_reason_codes(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_forbidden_export_string(value: str) -> bool:
    return any(
        pattern.search(value) for _category, pattern in _FORBIDDEN_EXPORT_VALUE_PATTERNS
    )


def _request_text_evidence(request: PreviewRequest) -> GovernanceReviewRequestEvidence:
    return GovernanceReviewRequestEvidence(
        request_state=request.request_state,
        semantic_contract_version=request.semantic_contract_version,
    )


def _redacted_column_names_for_export(columns: list[str]) -> list[str]:
    redacted: list[str] = []
    redacted_count = 0
    for column in columns:
        if _is_forbidden_export_string(column):
            redacted_count += 1
            redacted.append(f"redacted_column_{redacted_count}")
        else:
            redacted.append(column)
    return redacted


def _latest_payload_mapping(
    events: list[PreviewAuditEvent],
    key: str,
) -> Mapping[str, object] | None:
    for event in sorted(events, key=_audit_event_sort_key, reverse=True):
        payload = _payload_mapping(event.audit_payload, key)
        if payload is not None:
            return payload
    return None


def _semantic_mapping_evidence(
    events: list[PreviewAuditEvent],
) -> GovernanceReviewSemanticMappingEvidence | None:
    intent_mapping = _latest_payload_mapping(events, "intent_mapping")
    if intent_mapping is None:
        return None
    semantic_mapping = _payload_mapping(intent_mapping, "semantic_mapping")
    mapping_payload = semantic_mapping or intent_mapping
    status = _payload_string(intent_mapping, "status")
    if status is None:
        return None
    clarification = _payload_string(intent_mapping, "clarification")
    unsupported_concepts = _payload_string_list(intent_mapping, "unsupported_concepts")
    return GovernanceReviewSemanticMappingEvidence(
        status=status,
        intent=(
            _payload_string(intent_mapping, "intent")
            or _payload_string(intent_mapping, "mapping_id")
        ),
        metric=_payload_string(mapping_payload, "metric"),
        dimensions=_payload_string_list(mapping_payload, "dimensions"),
        filters=_payload_string_list(mapping_payload, "filters"),
        insufficient_evidence_reason=_payload_string(
            intent_mapping,
            "insufficient_evidence_reason",
        )
        or clarification,
        clarification=clarification,
        unsupported_concepts=unsupported_concepts or None,
    )


def _release_gate_payload(
    events: list[PreviewAuditEvent],
) -> Mapping[str, object] | None:
    return _latest_payload_mapping(events, "release_gate_scenario")


def _guard_decision_evidence(
    events: list[PreviewAuditEvent],
) -> GovernanceReviewGuardDecisionEvidence | None:
    guard_event = next(
        (
            event
            for event in sorted(events, key=_audit_event_sort_key, reverse=True)
            if event.event_type == "guard_evaluated"
        ),
        None,
    )
    if guard_event is None:
        return None
    decision = _payload_string(guard_event.audit_payload, "guard_decision")
    if decision is None:
        return None
    return GovernanceReviewGuardDecisionEvidence(
        decision=decision,
        guard_version=_payload_string(guard_event.audit_payload, "guard_version"),
        guard_audit_event_id=str(guard_event.event_id),
    )


def _validation_evidence(
    answer_evidence: Mapping[str, object],
) -> GovernanceReviewValidationEvidence | None:
    status = _payload_string(answer_evidence, "validation_status")
    bounded_metadata = _payload_mapping(answer_evidence, "bounded_metadata")
    if status is None or bounded_metadata is None:
        return None
    return GovernanceReviewValidationEvidence(
        status=status,
        reason_codes=_payload_string_list(bounded_metadata, "reason_codes"),
        row_limit=_payload_non_negative_int(bounded_metadata, "row_limit"),
        rows_used=_payload_non_negative_int(bounded_metadata, "rows_used"),
    )


def _execution_validation_evidence(
    execution_event: PreviewAuditEvent,
    answer_evidence: Mapping[str, object] | None,
) -> GovernanceReviewValidationEvidence | None:
    if answer_evidence is not None:
        return _validation_evidence(answer_evidence)
    if (
        execution_event.event_type != "execution_denied"
        or execution_event.primary_deny_code != DENY_RESULT_VALIDATION_FAILED
    ):
        return None
    return GovernanceReviewValidationEvidence(
        status="fail",
        reason_codes=_split_csv_reason_codes(
            _payload_string(execution_event.audit_payload, "denial_reason"),
        ),
    )


def _redaction_evidence(
    answer_evidence: Mapping[str, object],
) -> GovernanceReviewRedactionEvidence | None:
    status = _payload_string(answer_evidence, "redaction_status")
    if status is None:
        return None
    bounded_metadata = _payload_mapping(answer_evidence, "bounded_metadata") or {}
    return GovernanceReviewRedactionEvidence(
        status=status,
        redacted_columns=_redacted_column_names_for_export(
            _payload_string_list(bounded_metadata, "redacted_columns"),
        ),
    )


def _answer_evidence(
    answer_evidence: Mapping[str, object],
) -> GovernanceReviewAnswerEvidence | None:
    answer_state = _payload_string(answer_evidence, "answer_state")
    summary_strategy = _payload_string(answer_evidence, "summary_strategy")
    answer_evidence_id = _payload_string(answer_evidence, "answer_id")
    execution_run_id = _payload_string(answer_evidence, "execution_run_id")
    if (
        answer_state is None
        or summary_strategy is None
        or answer_evidence_id is None
        or execution_run_id is None
    ):
        return None
    return GovernanceReviewAnswerEvidence(
        answer_state=answer_state,
        summary_strategy=summary_strategy,
        answer_evidence_id=answer_evidence_id,
        execution_run_id=execution_run_id,
        insufficient_evidence_reason=_payload_string(
            answer_evidence,
            "insufficient_evidence_reason",
        ),
    )


def _governance_review_bundle(session: Session) -> GovernanceReviewBundle:
    requests = (
        session.execute(select(PreviewRequest).order_by(PreviewRequest.created_at))
        .scalars()
        .all()
    )
    candidates = (
        session.execute(select(PreviewCandidate).order_by(PreviewCandidate.created_at))
        .scalars()
        .all()
    )
    approvals = (
        session.execute(
            select(PreviewCandidateApproval).order_by(PreviewCandidateApproval.approved_at)
        )
        .scalars()
        .all()
    )
    events = (
        session.execute(
            select(PreviewAuditEvent).order_by(
                PreviewAuditEvent.occurred_at,
                PreviewAuditEvent.lifecycle_order,
                PreviewAuditEvent.event_id,
            )
        )
        .scalars()
        .all()
    )

    candidates_by_request: dict[str, list[PreviewCandidate]] = {}
    for candidate in candidates:
        candidates_by_request.setdefault(candidate.request_id, []).append(candidate)

    approvals_by_candidate_id = {
        approval.candidate_id: approval for approval in approvals
    }
    events_by_request: dict[str, list[PreviewAuditEvent]] = {}
    for event in events:
        events_by_request.setdefault(event.request_id, []).append(event)

    evidence: list[GovernanceReviewEvidence] = []
    for request in requests:
        request_candidates: list[PreviewCandidate | None] = (
            candidates_by_request.get(request.request_id) or [None]
        )
        request_events = events_by_request.get(request.request_id, [])
        for candidate in request_candidates:
            candidate_id = candidate.candidate_id if candidate is not None else None
            lifecycle_events = [
                event
                for event in request_events
                if event.candidate_id in (None, candidate_id)
            ]
            lifecycle = [
                GovernanceReviewLifecycleEvent(
                    event_type=event.event_type,
                    occurred_at=_as_utc_datetime(event.occurred_at),
                    lifecycle_order=event.lifecycle_order,
                    candidate_state=event.candidate_state,
                )
                for event in lifecycle_events
            ]
            approval = (
                approvals_by_candidate_id.get(candidate.candidate_id)
                if candidate is not None
                else None
            )
            execution_event = next(
                (
                    event
                    for event in sorted(
                        lifecycle_events,
                        key=_audit_event_sort_key,
                        reverse=True,
                    )
                    if event.event_type.startswith("execution_")
                ),
                None,
            )
            release_gate = _release_gate_payload(lifecycle_events)
            answer_payload = (
                _payload_mapping(execution_event.audit_payload, "answer_evidence")
                if execution_event is not None
                else None
            )
            evidence.append(
                GovernanceReviewEvidence(
                    request_id=request.request_id,
                    candidate_id=candidate_id,
                    source_id=request.source_id,
                    source_family=request.source_family,
                    source_flavor=request.source_flavor,
                    dataset_contract_version=request.dataset_contract_version,
                    schema_snapshot_version=request.schema_snapshot_version,
                    request=_request_text_evidence(request),
                    semantic_mapping=_semantic_mapping_evidence(lifecycle_events),
                    lifecycle=lifecycle,
                    actor=GovernanceReviewActorEvidence(
                        authenticated_subject_id=request.authenticated_subject_id,
                        auth_source=request.auth_source,
                        governance_bindings=_split_bindings(request.governance_bindings),
                        entitlement_decision=request.entitlement_decision,
                    ),
                    candidate=(
                        GovernanceReviewCandidateEvidence(
                            candidate_state=candidate.candidate_state,
                            guard_status=candidate.guard_status,
                            sql_candidate=GovernanceReviewSqlCandidateEvidence(
                                release_gate_scenario_id=(
                                    _payload_string(release_gate, "scenario_id")
                                    if release_gate is not None
                                    else None
                                ),
                            ),
                            guard_decision=_guard_decision_evidence(lifecycle_events),
                            adapter_evidence=GovernanceReviewAdapterEvidence(
                                adapter_provider=candidate.adapter_provider,
                                adapter_model=candidate.adapter_model,
                                adapter_version=candidate.adapter_version,
                                adapter_run_id=candidate.adapter_run_id,
                                prompt_version=candidate.prompt_version,
                                prompt_fingerprint=candidate.prompt_fingerprint,
                            ),
                        )
                        if candidate is not None
                        else None
                    ),
                    review=(
                        GovernanceReviewApprovalEvidence(
                            approval_id=approval.approval_id,
                            approval_state=approval.approval_state,
                            owner_subject_id=approval.owner_subject_id,
                            approved_at=_as_utc_datetime(approval.approved_at),
                            approval_expires_at=_as_utc_datetime(
                                approval.approval_expires_at
                            ),
                            invalidated_at=(
                                _as_utc_datetime(approval.invalidated_at)
                                if approval.invalidated_at is not None
                                else None
                            ),
                            executed_at=(
                                _as_utc_datetime(approval.executed_at)
                                if approval.executed_at is not None
                                else None
                            ),
                            execution_policy_version=approval.execution_policy_version,
                        )
                        if approval is not None
                        else None
                    ),
                    execute_result=(
                        GovernanceReviewExecuteResultEvidence(
                            event_type=execution_event.event_type,
                            occurred_at=_as_utc_datetime(execution_event.occurred_at),
                            row_count=_payload_non_negative_int(
                                execution_event.audit_payload,
                                "execution_row_count",
                            ),
                            result_truncated=_payload_bool(
                                execution_event.audit_payload,
                                "result_truncated",
                            ),
                            validation=(
                                _execution_validation_evidence(
                                    execution_event,
                                    answer_payload,
                                )
                            ),
                            redaction=(
                                _redaction_evidence(answer_payload)
                                if answer_payload is not None
                                else None
                            ),
                            answer=(
                                _answer_evidence(answer_payload)
                                if answer_payload is not None
                                else None
                            ),
                        )
                        if execution_event is not None
                        else None
                    ),
                )
            )

    return GovernanceReviewBundle(
        evidence=evidence,
        limitations=[
            "Bundle is read-only review evidence and does not authorize execution.",
            "Subordinate adapter, LLM, search, analyst, MLflow, UI, and external evidence is labeled as non-authoritative.",
            "Raw prompts, raw SQL, result rows, deterministic result hashes, credentials, connection references, tokens, and workstation-local paths are excluded.",
        ],
    )


def _iter_string_values(
    value: object,
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        strings: list[tuple[tuple[str, ...], str]] = []
        for key, item in value.items():
            strings.append(((*path, str(key)), str(key)))
            strings.extend(_iter_string_values(item, (*path, str(key))))
        return strings
    if isinstance(value, list):
        strings = []
        for index, item in enumerate(value):
            strings.extend(_iter_string_values(item, (*path, str(index))))
        return strings
    return []


def _is_raw_identity_payload(path: tuple[str, ...], value: str) -> bool:
    if not path or path[-1] not in _IDENTITY_EXPORT_FIELD_NAMES:
        return False
    normalized = value.lstrip()
    return normalized.startswith("{") or normalized.startswith("[")


def _assert_bundle_is_shareable(bundle: SupportBundle) -> None:
    payload = bundle.model_dump(mode="json", by_alias=True, exclude_none=True)
    for path, value in _iter_string_values(payload):
        if _is_raw_identity_payload(path, value):
            raise ValueError(
                "Support bundle contains non-shareable raw identity payloads."
            )
        for category, pattern in _FORBIDDEN_EXPORT_VALUE_PATTERNS:
            if pattern.search(value):
                raise ValueError(
                    f"Support bundle contains non-shareable {category}."
                )


def _assert_bounded_result_summary_is_shareable(
    export: BoundedResultSummaryExport,
) -> None:
    payload = export.model_dump(mode="json", by_alias=True, exclude_none=True)
    for path, value in _iter_string_values(payload):
        if _is_raw_identity_payload(path, value):
            raise ValueError(
                "Bounded result summary contains non-shareable raw identity payloads."
            )
        for category, pattern in _FORBIDDEN_EXPORT_VALUE_PATTERNS:
            if pattern.search(value):
                raise ValueError(
                    f"Bounded result summary contains non-shareable {category}."
                )


def _bounded_operator_display_rows(
    payload: Mapping[str, object],
) -> list[dict[str, Any]]:
    rows = payload.get("operator_display_rows")
    if rows is None:
        return []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(
            "Bounded result summary contains malformed operator display rows."
        )
    if len(rows) > _BOUNDED_RESULT_SUMMARY_ROW_LIMIT:
        raise ValueError(
            "Bounded result summary contains too many operator display rows."
        )
    return [dict(row) for row in rows]


def _latest_execution_completed_event(
    session: Session,
    *,
    candidate_id: str,
) -> PreviewAuditEvent | None:
    return session.scalar(
        select(PreviewAuditEvent)
        .where(
            PreviewAuditEvent.candidate_id == candidate_id,
            PreviewAuditEvent.event_type == "execution_completed",
        )
        .order_by(
            PreviewAuditEvent.occurred_at.desc(),
            PreviewAuditEvent.lifecycle_order.desc(),
            PreviewAuditEvent.event_id.desc(),
        )
        .limit(1)
    )


def build_bounded_result_summary_export(
    session: Session,
    *,
    candidate_id: str,
    generated_at: datetime | None = None,
) -> BoundedResultSummaryExport | None:
    candidate = session.scalar(
        select(PreviewCandidate).where(PreviewCandidate.candidate_id == candidate_id)
    )
    if candidate is None:
        return None

    request = session.scalar(
        select(PreviewRequest).where(PreviewRequest.request_id == candidate.request_id)
    )
    if request is None:
        return None

    execution_event = _latest_execution_completed_event(
        session,
        candidate_id=candidate_id,
    )
    if execution_event is None:
        return None

    row_count = _payload_non_negative_int(
        execution_event.audit_payload,
        "execution_row_count",
    )
    result_truncated = _payload_bool(
        execution_event.audit_payload,
        "result_truncated",
    )
    if row_count is None or result_truncated is None:
        return None

    bounded_rows = _bounded_operator_display_rows(execution_event.audit_payload)
    generated_at = generated_at or datetime.now(timezone.utc)
    export = BoundedResultSummaryExport(
        generated_at=generated_at.astimezone(timezone.utc),
        request=BoundedResultSummaryRequestContext(
            request_id=request.request_id,
            request_state=request.request_state,
        ),
        candidate=BoundedResultSummaryCandidateContext(
            candidate_id=candidate.candidate_id,
            candidate_state=candidate.candidate_state,
            guard_status=candidate.guard_status,
        ),
        run=BoundedResultSummaryRunContext(
            execution_run_id=str(execution_event.event_id),
            event_type="execution_completed",
            occurred_at=_as_utc_datetime(execution_event.occurred_at),
        ),
        source=BoundedResultSummarySourceContext(
            source_id=execution_event.source_id,
            source_family=execution_event.source_family,
            source_flavor=execution_event.source_flavor,
            dataset_contract_version=execution_event.dataset_contract_version
            or candidate.dataset_contract_version,
            schema_snapshot_version=execution_event.schema_snapshot_version
            or candidate.schema_snapshot_version,
        ),
        audit=BoundedResultSummaryAuditContext(
            audit_event_id=str(execution_event.event_id),
            correlation_id=execution_event.correlation_id,
            lifecycle_order=execution_event.lifecycle_order,
        ),
        result=BoundedResultSummaryResult(
            summary_kind="bounded_rows" if bounded_rows else "aggregate_only",
            row_count=row_count,
            result_truncated=result_truncated,
            bounded_rows=bounded_rows,
            bounded_row_count=len(bounded_rows),
            bounded_row_limit=_BOUNDED_RESULT_SUMMARY_ROW_LIMIT,
        ),
        limitations=[
            "Export is a bounded operator handoff summary, not an authoritative audit bundle.",
            "Raw SQL, connection details, credentials, tokens, raw result rows, and workstation-local paths are excluded.",
            "Rows are included only when they were already persisted as bounded operator-display rows.",
        ],
        redaction=_redaction_policy(),
    )
    _assert_bounded_result_summary_is_shareable(export)
    return export


def build_support_bundle(
    session: Session,
    *,
    settings: Settings,
    database: Mapping[str, str],
    sql_generation: Mapping[str, object],
    generated_at: datetime | None = None,
) -> SupportBundle:
    operator_health = build_operator_health(
        session,
        database=database,
        sql_generation=sql_generation,
    )
    workflow_lifecycle_metrics = operator_health["workflow_lifecycle_metrics"]
    assert isinstance(workflow_lifecycle_metrics, dict)
    history_count, recent_states = _recent_workflow_states(session)

    generated_at = generated_at or datetime.now(timezone.utc)
    bundle = SupportBundle(
        generated_at=generated_at.astimezone(timezone.utc),
        application=SupportBundleApplication(
            version=_APP_VERSION,
            environment=settings.environment,
        ),
        source_posture=settings.source_posture_telemetry().model_dump(mode="json"),
        migration_posture=_migration_posture(session),
        active_sources=_active_sources(session),
        health=SupportBundleHealth(
            status=str(operator_health["status"]),
            components=dict(operator_health["components"]),
        ),
        workflow=SupportBundleWorkflow(
            history_count=history_count,
            recent_states=recent_states,
            lifecycle_metrics=workflow_lifecycle_metrics,
        ),
        audit_completeness=_audit_completeness(workflow_lifecycle_metrics),
        governance_review=_governance_review_bundle(session),
        redaction=_redaction_policy(),
    )
    _assert_bundle_is_shareable(bundle)
    return bundle
