from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import PreviewAuditEvent, PreviewCandidate, PreviewRequest
from app.db.models.schema_snapshot import SchemaSnapshot
from app.db.models.source_registry import RegisteredSource
from app.features.auth.governance_bindings import normalize_governance_binding


GovernanceBindingState = Literal[
    "valid",
    "missing",
    "ambiguous",
    "stale",
    "drifted",
]
GovernanceBindingRole = Literal[
    "owner",
    "security_review",
    "exception_policy",
]


class OperatorWorkflowSourceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(serialization_alias="sourceId")
    display_label: str = Field(serialization_alias="displayLabel")
    description: str
    activation_posture: str = Field(serialization_alias="activationPosture")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")
    governance_bindings: list["OperatorWorkflowGovernanceBindingStatus"] = Field(
        default_factory=list,
        serialization_alias="governanceBindings",
    )


class OperatorWorkflowGovernanceBindingStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: GovernanceBindingRole
    state: GovernanceBindingState
    affects_entitlement: bool = Field(serialization_alias="affectsEntitlement")
    summary: str
    recovery: str


class OperatorWorkflowHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_type: Literal["request", "candidate", "run"] = Field(serialization_alias="itemType")
    record_id: str = Field(serialization_alias="recordId")
    label: str
    source_id: str = Field(serialization_alias="sourceId")
    source_label: str = Field(serialization_alias="sourceLabel")
    lifecycle_state: str = Field(serialization_alias="lifecycleState")
    occurred_at: datetime = Field(serialization_alias="occurredAt")
    candidate_sql: Optional[str] = Field(default=None, serialization_alias="candidateSql")
    request_id: Optional[str] = Field(default=None, serialization_alias="requestId")
    guard_status: Optional[str] = Field(default=None, serialization_alias="guardStatus")
    primary_deny_code: Optional[str] = Field(
        default=None,
        serialization_alias="primaryDenyCode",
    )
    result_truncated: Optional[bool] = Field(
        default=None,
        serialization_alias="resultTruncated",
    )
    row_count: Optional[int] = Field(default=None, serialization_alias="rowCount")
    run_state: Optional[str] = Field(default=None, serialization_alias="runState")
    audit_events: list["OperatorWorkflowAuditEventSummary"] = Field(
        default_factory=list,
        serialization_alias="auditEvents",
    )
    executed_evidence: list["OperatorWorkflowExecutedEvidence"] = Field(
        default_factory=list,
        serialization_alias="executedEvidence",
    )
    retrieved_citations: list["OperatorWorkflowRetrievedCitation"] = Field(
        default_factory=list,
        serialization_alias="retrievedCitations",
    )


class OperatorWorkflowAuditEventSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(serialization_alias="eventId")
    event_type: str = Field(serialization_alias="eventType")
    occurred_at: datetime = Field(serialization_alias="occurredAt")
    request_id: str = Field(serialization_alias="requestId")
    candidate_id: Optional[str] = Field(default=None, serialization_alias="candidateId")
    source_id: str = Field(serialization_alias="sourceId")
    candidate_state: Optional[str] = Field(default=None, serialization_alias="candidateState")
    primary_deny_code: Optional[str] = Field(default=None, serialization_alias="primaryDenyCode")
    row_count: Optional[int] = Field(default=None, serialization_alias="rowCount")
    result_truncated: Optional[bool] = Field(default=None, serialization_alias="resultTruncated")


class OperatorWorkflowExecutedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["backend_execution_result"] = "backend_execution_result"
    can_authorize_execution: Literal[False] = Field(
        default=False,
        serialization_alias="canAuthorizeExecution",
    )
    candidate_id: str = Field(serialization_alias="candidateId")
    execution_audit_event_id: str = Field(serialization_alias="executionAuditEventId")
    execution_audit_event_type: Literal["execution_completed"] = Field(
        serialization_alias="executionAuditEventType",
    )
    row_count: int = Field(serialization_alias="rowCount")
    result_truncated: bool = Field(serialization_alias="resultTruncated")
    source_id: str = Field(serialization_alias="sourceId")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")
    dataset_contract_version: Optional[int] = Field(
        default=None,
        serialization_alias="datasetContractVersion",
    )
    schema_snapshot_version: Optional[int] = Field(
        default=None,
        serialization_alias="schemaSnapshotVersion",
    )
    execution_policy_version: Optional[int] = Field(
        default=None,
        serialization_alias="executionPolicyVersion",
    )
    connector_profile_version: Optional[int] = Field(
        default=None,
        serialization_alias="connectorProfileVersion",
    )


class OperatorWorkflowRetrievedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(serialization_alias="assetId")
    asset_kind: str = Field(serialization_alias="assetKind")
    authority: Literal["advisory_context"] = "advisory_context"
    can_authorize_execution: Literal[False] = Field(
        default=False,
        serialization_alias="canAuthorizeExecution",
    )
    citation_label: str = Field(serialization_alias="citationLabel")
    source_id: str = Field(serialization_alias="sourceId")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")
    dataset_contract_version: Optional[int] = Field(
        default=None,
        serialization_alias="datasetContractVersion",
    )
    schema_snapshot_version: Optional[int] = Field(
        default=None,
        serialization_alias="schemaSnapshotVersion",
    )


class OperatorWorkflowSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[OperatorWorkflowSourceOption]
    history: list[OperatorWorkflowHistoryItem] = Field(default_factory=list)


def _source_description(source: RegisteredSource) -> str:
    flavor = f" / {source.source_flavor}" if source.source_flavor else ""
    return (
        f"{source.source_family}{flavor} source with "
        f"{source.activation_posture.value} activation posture."
    )


def _governance_binding_status(
    *,
    role: GovernanceBindingRole,
    raw_binding: str | None,
    state: GovernanceBindingState,
    affects_entitlement: bool,
) -> OperatorWorkflowGovernanceBindingStatus:
    role_label = role.replace("_", " ")
    summaries = {
        "valid": f"{role_label.title()} binding is current and normalized.",
        "missing": f"{role_label.title()} binding is missing or malformed.",
        "ambiguous": f"{role_label.title()} binding overlaps another governance role.",
        "stale": f"{role_label.title()} binding is attached to a stale contract version.",
        "drifted": f"{role_label.title()} binding no longer matches the active source linkage.",
    }
    recoveries = {
        "valid": "No operator recovery is required for this binding.",
        "missing": "Reconcile the authoritative dataset contract before granting access.",
        "ambiguous": "Split or re-review role mappings before treating the binding as current.",
        "stale": "Promote or rebind the latest reviewed governance contract before retrying.",
        "drifted": "Repair source-to-contract and source-to-schema links before retrying.",
    }
    normalized = normalize_governance_binding(raw_binding)
    effective_state = "missing" if normalized is None and state == "valid" else state
    return OperatorWorkflowGovernanceBindingStatus(
        role=role,
        state=effective_state,
        affects_entitlement=affects_entitlement,
        summary=summaries[effective_state],
        recovery=recoveries[effective_state],
    )


def _source_governance_bindings(
    *,
    source: RegisteredSource,
    contract: DatasetContract | None,
    schema_snapshot: SchemaSnapshot | None,
    latest_contract_version: int | None,
) -> list[OperatorWorkflowGovernanceBindingStatus]:
    roles: list[tuple[GovernanceBindingRole, str | None, bool]] = [
        ("owner", contract.owner_binding if contract is not None else None, True),
        (
            "security_review",
            contract.security_review_binding if contract is not None else None,
            False,
        ),
        (
            "exception_policy",
            contract.exception_policy_binding if contract is not None else None,
            False,
        ),
    ]
    normalized_counts: dict[str, int] = {}
    for _, raw_binding, _ in roles:
        normalized = normalize_governance_binding(raw_binding)
        if normalized is not None:
            normalized_counts[normalized] = normalized_counts.get(normalized, 0) + 1

    drifted = (
        contract is None
        or schema_snapshot is None
        or source.dataset_contract_id != contract.id
        or source.schema_snapshot_id != schema_snapshot.id
        or contract.registered_source_id != source.id
        or schema_snapshot.registered_source_id != source.id
        or contract.schema_snapshot_id != schema_snapshot.id
    )
    stale = (
        not drifted
        and latest_contract_version is not None
        and contract is not None
        and contract.contract_version < latest_contract_version
    )

    statuses: list[OperatorWorkflowGovernanceBindingStatus] = []
    for role, raw_binding, affects_entitlement in roles:
        normalized = normalize_governance_binding(raw_binding)
        state: GovernanceBindingState = "valid"
        if drifted:
            state = "drifted"
        elif stale:
            state = "stale"
        elif normalized is None:
            state = "missing"
        elif normalized_counts.get(normalized, 0) > 1:
            state = "ambiguous"
        statuses.append(
            _governance_binding_status(
                role=role,
                raw_binding=raw_binding,
                state=state,
                affects_entitlement=affects_entitlement,
            )
        )
    return statuses


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _source_labels_by_id(sources: list[RegisteredSource]) -> dict[str, str]:
    return {source.source_id: source.display_label for source in sources}


def _request_labels_by_id(requests: list[PreviewRequest]) -> dict[str, str]:
    return {request.request_id: request.request_text for request in requests}


def _audit_event_sort_key(event: PreviewAuditEvent) -> tuple[datetime, int, str]:
    return (
        _as_utc_datetime(event.occurred_at),
        event.lifecycle_order,
        str(event.event_id),
    )


def _is_execution_event(event: PreviewAuditEvent) -> bool:
    return event.event_type.startswith("execution_")


def _latest_request_events(
    audit_events: list[PreviewAuditEvent],
) -> dict[str, PreviewAuditEvent]:
    latest: dict[str, PreviewAuditEvent] = {}
    for event in audit_events:
        if _is_execution_event(event):
            continue
        current = latest.get(event.request_id)
        if current is None or _audit_event_sort_key(event) > _audit_event_sort_key(
            current
        ):
            latest[event.request_id] = event
    return latest


def _latest_candidate_events(
    audit_events: list[PreviewAuditEvent],
) -> dict[str, PreviewAuditEvent]:
    latest: dict[str, PreviewAuditEvent] = {}
    for event in audit_events:
        if event.candidate_id is None or _is_execution_event(event):
            continue
        current = latest.get(event.candidate_id)
        if current is None or _audit_event_sort_key(event) > _audit_event_sort_key(
            current
        ):
            latest[event.candidate_id] = event
    return latest


def _run_state_for_event(event: PreviewAuditEvent) -> str | None:
    if event.event_type == "execution_completed":
        row_count = event.audit_payload.get("execution_row_count")
        return "empty" if row_count == 0 else "completed"

    if event.event_type == "execution_denied":
        return "execution_denied"

    if event.event_type == "execution_failed":
        return "canceled" if event.candidate_state == "canceled" else "failed"

    return None


def _run_row_count_for_event(event: PreviewAuditEvent, run_state: str) -> int | None:
    if run_state not in {"completed", "empty"}:
        return None

    row_count = event.audit_payload.get("execution_row_count")
    return row_count if isinstance(row_count, int) and row_count >= 0 else None


def _run_result_truncated_for_event(
    event: PreviewAuditEvent,
    run_state: str,
) -> bool | None:
    if run_state not in {"completed", "empty"}:
        return None

    result_truncated = event.audit_payload.get("result_truncated")
    return result_truncated if isinstance(result_truncated, bool) else None


def _read_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _read_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _read_non_negative_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _read_positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _read_payload_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, dict)]


def _audit_event_summary(event: PreviewAuditEvent) -> OperatorWorkflowAuditEventSummary:
    return OperatorWorkflowAuditEventSummary(
        event_id=str(event.event_id),
        event_type=event.event_type,
        occurred_at=_as_utc_datetime(event.occurred_at),
        request_id=event.request_id,
        candidate_id=event.candidate_id,
        source_id=event.source_id,
        candidate_state=event.candidate_state,
        primary_deny_code=event.primary_deny_code,
        row_count=_read_non_negative_int(event.audit_payload.get("execution_row_count")),
        result_truncated=_read_bool(event.audit_payload.get("result_truncated")),
    )


def _executed_evidence_for_event(
    event: PreviewAuditEvent,
) -> list[OperatorWorkflowExecutedEvidence]:
    evidence: list[OperatorWorkflowExecutedEvidence] = []
    for item in _read_payload_items(event.audit_payload.get("executed_evidence")):
        if (
            item.get("type") != "executed_evidence"
            or item.get("authority") != "backend_execution_result"
            or item.get("can_authorize_execution") is not False
        ):
            continue

        candidate_id = _read_text(item.get("candidate_id"))
        execution_audit_event_id = _read_text(item.get("execution_audit_event_id"))
        row_count = _read_non_negative_int(item.get("row_count"))
        result_truncated = _read_bool(item.get("result_truncated"))
        source_id = _read_text(item.get("source_id"))
        source_family = _read_text(item.get("source_family"))
        if (
            candidate_id is None
            or execution_audit_event_id is None
            or item.get("execution_audit_event_type") != "execution_completed"
            or row_count is None
            or result_truncated is None
            or source_id != event.source_id
            or source_family is None
        ):
            continue

        evidence.append(
            OperatorWorkflowExecutedEvidence(
                candidate_id=candidate_id,
                execution_audit_event_id=execution_audit_event_id,
                execution_audit_event_type="execution_completed",
                row_count=row_count,
                result_truncated=result_truncated,
                source_id=source_id,
                source_family=source_family,
                source_flavor=_read_text(item.get("source_flavor")),
                dataset_contract_version=_read_positive_int(
                    item.get("dataset_contract_version")
                ),
                schema_snapshot_version=_read_positive_int(
                    item.get("schema_snapshot_version")
                ),
                execution_policy_version=_read_positive_int(
                    item.get("execution_policy_version")
                ),
                connector_profile_version=_read_positive_int(
                    item.get("connector_profile_version")
                ),
            )
        )
    return evidence


def _retrieved_citations_for_event(
    event: PreviewAuditEvent,
) -> list[OperatorWorkflowRetrievedCitation]:
    citations: list[OperatorWorkflowRetrievedCitation] = []
    for item in _read_payload_items(event.audit_payload.get("retrieved_citations")):
        if (
            item.get("authority") != "advisory_context"
            or item.get("can_authorize_execution") is not False
        ):
            continue

        asset_id = _read_text(item.get("asset_id"))
        asset_kind = _read_text(item.get("asset_kind"))
        citation_label = _read_text(item.get("citation_label"))
        source_id = _read_text(item.get("source_id"))
        source_family = _read_text(item.get("source_family"))
        if (
            asset_id is None
            or asset_kind is None
            or citation_label is None
            or source_id != event.source_id
            or source_family is None
        ):
            continue

        citations.append(
            OperatorWorkflowRetrievedCitation(
                asset_id=asset_id,
                asset_kind=asset_kind,
                citation_label=citation_label,
                source_id=source_id,
                source_family=source_family,
                source_flavor=_read_text(item.get("source_flavor")),
                dataset_contract_version=_read_positive_int(
                    item.get("dataset_contract_version")
                ),
                schema_snapshot_version=_read_positive_int(
                    item.get("schema_snapshot_version")
                ),
            )
        )
    return citations


def _terminal_run_events(
    audit_events: list[PreviewAuditEvent],
) -> list[tuple[PreviewAuditEvent, str]]:
    terminal_events: list[tuple[PreviewAuditEvent, str]] = []
    for event in audit_events:
        if event.candidate_id is None:
            continue

        run_state = _run_state_for_event(event)
        if run_state is None:
            continue

        terminal_events.append((event, run_state))

    return terminal_events


def _history_occurred_at(
    event: PreviewAuditEvent | None,
    fallback: datetime,
) -> datetime:
    return _as_utc_datetime(event.occurred_at if event is not None else fallback)


def _build_operator_history(
    session: Session,
    *,
    sources: list[RegisteredSource],
) -> list[OperatorWorkflowHistoryItem]:
    requests = session.execute(select(PreviewRequest)).scalars().all()
    candidates = session.execute(select(PreviewCandidate)).scalars().all()
    audit_events = (
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

    source_labels = _source_labels_by_id(sources)
    request_labels = _request_labels_by_id(requests)
    request_events = _latest_request_events(audit_events)
    candidate_events = _latest_candidate_events(audit_events)

    history: list[OperatorWorkflowHistoryItem] = []
    for event, run_state in _terminal_run_events(audit_events):
        history.append(
            OperatorWorkflowHistoryItem(
                item_type="run",
                record_id=str(event.event_id),
                label=request_labels.get(event.request_id, "Execution run"),
                source_id=event.source_id,
                source_label=source_labels.get(event.source_id, event.source_id),
                lifecycle_state=run_state,
                occurred_at=_as_utc_datetime(event.occurred_at),
                request_id=event.request_id,
                primary_deny_code=event.primary_deny_code,
                result_truncated=_run_result_truncated_for_event(event, run_state),
                row_count=_run_row_count_for_event(event, run_state),
                run_state=run_state,
                audit_events=[_audit_event_summary(event)],
                executed_evidence=_executed_evidence_for_event(event),
                retrieved_citations=_retrieved_citations_for_event(event),
            )
        )

    for candidate in candidates:
        candidate_event = candidate_events.get(candidate.candidate_id)
        history.append(
            OperatorWorkflowHistoryItem(
                item_type="candidate",
                record_id=candidate.candidate_id,
                label=request_labels.get(candidate.request_id, "SQL preview"),
                source_id=candidate.source_id,
                source_label=source_labels.get(candidate.source_id, candidate.source_id),
                lifecycle_state=candidate.candidate_state,
                occurred_at=_history_occurred_at(
                    candidate_event,
                    candidate.updated_at or candidate.created_at,
                ),
                candidate_sql=candidate.candidate_sql,
                request_id=candidate.request_id,
                guard_status=candidate.guard_status,
                audit_events=(
                    [_audit_event_summary(candidate_event)] if candidate_event else []
                ),
                executed_evidence=(
                    _executed_evidence_for_event(candidate_event) if candidate_event else []
                ),
                retrieved_citations=(
                    _retrieved_citations_for_event(candidate_event) if candidate_event else []
                ),
            )
        )

    for request in requests:
        request_event = request_events.get(request.request_id)
        history.append(
            OperatorWorkflowHistoryItem(
                item_type="request",
                record_id=request.request_id,
                label=request.request_text,
                source_id=request.source_id,
                source_label=source_labels.get(request.source_id, request.source_id),
                lifecycle_state=request.request_state,
                occurred_at=_history_occurred_at(
                    request_event,
                    request.updated_at or request.created_at,
                ),
                audit_events=(
                    [_audit_event_summary(request_event)] if request_event else []
                ),
                executed_evidence=(
                    _executed_evidence_for_event(request_event) if request_event else []
                ),
                retrieved_citations=(
                    _retrieved_citations_for_event(request_event) if request_event else []
                ),
            )
        )

    item_priority = {"candidate": 0, "request": 1, "run": 2}
    return sorted(
        history,
        key=lambda item: (
            item.occurred_at,
            -item_priority[item.item_type],
            item.record_id,
        ),
        reverse=True,
    )


def get_operator_workflow_snapshot(session: Session) -> OperatorWorkflowSnapshot:
    source_rows = (
        session.execute(
            select(RegisteredSource, DatasetContract, SchemaSnapshot)
            .outerjoin(
                DatasetContract,
                DatasetContract.id == RegisteredSource.dataset_contract_id,
            )
            .outerjoin(
                SchemaSnapshot,
                SchemaSnapshot.id == RegisteredSource.schema_snapshot_id,
            )
            .order_by(RegisteredSource.source_id)
        )
        .all()
    )
    sources = [row[0] for row in source_rows]
    latest_contract_versions = dict(
        session.execute(
            select(
                DatasetContract.registered_source_id,
                func.max(DatasetContract.contract_version),
            ).group_by(DatasetContract.registered_source_id)
        ).all()
    )

    source_options = [
        OperatorWorkflowSourceOption(
            source_id=source.source_id,
            display_label=source.display_label,
            description=_source_description(source),
            activation_posture=source.activation_posture.value,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
            governance_bindings=_source_governance_bindings(
                source=source,
                contract=dataset_contract,
                schema_snapshot=schema_snapshot,
                latest_contract_version=latest_contract_versions.get(source.id),
            ),
        )
        for source, dataset_contract, schema_snapshot in source_rows
    ]

    return OperatorWorkflowSnapshot(
        sources=source_options,
        history=_build_operator_history(session, sources=sources),
    )
