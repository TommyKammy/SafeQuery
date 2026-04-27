from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Literal, Optional

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
from app.services.first_run_doctor import _alembic_heads
from app.services.health import build_operator_health
from app.services.operator_workflow import get_operator_workflow_snapshot


_APP_VERSION = "0.1.0"
_WINDOWS_USER_PROFILE_SEGMENT = "Users"
_FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\\s\"']+"),
    re.compile(r"(?i)\b(driver|server|database|uid|pwd)\s*="),
    re.compile(r"(?i)\b(sk|pk|ghp|github_pat)-[a-z0-9][a-z0-9_-]{8,}"),
    re.compile(r"(?i)(^|[\\/])Users[\\/][^\\/\"]+"),
    re.compile(rf"(?i)[a-z]:\\{_WINDOWS_USER_PROFILE_SEGMENT}\\[^\\\"]+"),
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


class GovernanceReviewCandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["safequery_control_plane"] = "safequery_control_plane"
    candidate_state: str = Field(serialization_alias="candidateState")
    guard_status: str = Field(serialization_alias="guardStatus")
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


def _active_sources(session: Session) -> list[SupportBundleSource]:
    sources = session.scalars(
        select(RegisteredSource)
        .where(RegisteredSource.activation_posture == SourceActivationPosture.ACTIVE)
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
            "raw_result_rows",
            "candidate_sql",
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
            evidence.append(
                GovernanceReviewEvidence(
                    request_id=request.request_id,
                    candidate_id=candidate_id,
                    source_id=request.source_id,
                    source_family=request.source_family,
                    source_flavor=request.source_flavor,
                    dataset_contract_version=request.dataset_contract_version,
                    schema_snapshot_version=request.schema_snapshot_version,
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
            "Raw SQL, result rows, credentials, connection references, tokens, and workstation-local paths are excluded.",
        ],
    )


def _iter_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_iter_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_iter_strings(item))
        return strings
    return []


def _assert_bundle_is_shareable(bundle: SupportBundle) -> None:
    payload = bundle.model_dump(mode="json", by_alias=True, exclude_none=True)
    for value in _iter_strings(payload):
        for pattern in _FORBIDDEN_VALUE_PATTERNS:
            if pattern.search(value):
                raise ValueError(
                    "Support bundle contains a non-shareable diagnostic value."
                )


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
