from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.preview import PreviewAuditEvent, PreviewCandidate, PreviewRequest
from app.db.models.source_registry import RegisteredSource


class OperatorWorkflowSourceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(serialization_alias="sourceId")
    display_label: str = Field(serialization_alias="displayLabel")
    description: str
    activation_posture: str = Field(serialization_alias="activationPosture")
    source_family: str = Field(serialization_alias="sourceFamily")
    source_flavor: Optional[str] = Field(default=None, serialization_alias="sourceFlavor")


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
            )
        )

    for candidate in candidates:
        history.append(
            OperatorWorkflowHistoryItem(
                item_type="candidate",
                record_id=candidate.candidate_id,
                label=request_labels.get(candidate.request_id, "SQL preview"),
                source_id=candidate.source_id,
                source_label=source_labels.get(candidate.source_id, candidate.source_id),
                lifecycle_state=candidate.candidate_state,
                occurred_at=_history_occurred_at(
                    candidate_events.get(candidate.candidate_id),
                    candidate.updated_at or candidate.created_at,
                ),
                candidate_sql=candidate.candidate_sql,
                request_id=candidate.request_id,
                guard_status=candidate.guard_status,
            )
        )

    for request in requests:
        history.append(
            OperatorWorkflowHistoryItem(
                item_type="request",
                record_id=request.request_id,
                label=request.request_text,
                source_id=request.source_id,
                source_label=source_labels.get(request.source_id, request.source_id),
                lifecycle_state=request.request_state,
                occurred_at=_history_occurred_at(
                    request_events.get(request.request_id),
                    request.updated_at or request.created_at,
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
    sources = (
        session.execute(select(RegisteredSource).order_by(RegisteredSource.source_id))
        .scalars()
        .all()
    )

    source_options = [
        OperatorWorkflowSourceOption(
            source_id=source.source_id,
            display_label=source.display_label,
            description=_source_description(source),
            activation_posture=source.activation_posture.value,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
        )
        for source in sources
    ]

    return OperatorWorkflowSnapshot(
        sources=source_options,
        history=_build_operator_history(session, sources=sources),
    )
