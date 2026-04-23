from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, NonNegativeInt, model_validator

from app.features.audit.event_model import (
    NonEmptyTrimmedString,
    SourceFamily,
    SourceFlavor,
    SourceIdentifier,
)

RequestState = Literal["drafting", "submitted", "previewed", "blocked", "superseded"]
CandidateState = Literal[
    "pending_generation",
    "preview_ready",
    "blocked",
    "expired",
    "invalidated",
    "approved_for_execution",
    "stale",
    "superseded",
]
GuardStatus = Literal[
    "pending",
    "allow",
    "blocked",
    "expired",
    "invalidated",
    "requires_revalidation",
]
ExecutionStatus = Literal[
    "executing",
    "execution_denied",
    "failed",
    "canceled",
    "empty",
    "completed",
]
TerminalState = Literal[
    "review_denied",
    "execution_denied",
    "failed",
    "canceled",
    "empty",
    "completed",
]
ResultState = Literal["execution_denied", "failed", "canceled", "empty", "completed"]


class _SourceAwareHistoryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    occurred_at: datetime
    audit_event_id: Optional[UUID] = None


class OperatorHistoryRequestSummary(_SourceAwareHistoryPayload):
    request_id: NonEmptyTrimmedString
    request_state: RequestState
    summary_label: NonEmptyTrimmedString


class OperatorHistoryCandidateSummary(_SourceAwareHistoryPayload):
    request_id: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString
    candidate_state: CandidateState
    guard_status: GuardStatus
    sql_review_anchor: NonEmptyTrimmedString
    primary_deny_code: Optional[NonEmptyTrimmedString] = None
    reopened_draft_source_id: Optional[SourceIdentifier] = None

    @model_validator(mode="after")
    def validate_reopened_draft_source_id(self) -> "OperatorHistoryCandidateSummary":
        if (
            self.reopened_draft_source_id is not None
            and self.reopened_draft_source_id != self.source_id
        ):
            raise ValueError(
                "A reopened draft source binding must match the candidate-bound source."
            )
        return self


class OperatorHistoryRunSummary(_SourceAwareHistoryPayload):
    request_id: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString
    run_id: NonEmptyTrimmedString
    execution_status: ExecutionStatus
    row_count: Optional[NonNegativeInt] = None
    result_truncated: Optional[bool] = None
    primary_deny_code: Optional[NonEmptyTrimmedString] = None

    @model_validator(mode="after")
    def validate_run_summary(self) -> "OperatorHistoryRunSummary":
        if self.execution_status == "execution_denied" and self.primary_deny_code is None:
            raise ValueError(
                "Execution-denied run summaries must include a primary_deny_code."
            )
        return self


class OperatorHistoryDenialSummary(_SourceAwareHistoryPayload):
    request_id: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString
    run_id: Optional[NonEmptyTrimmedString] = None
    terminal_state: Literal["review_denied", "execution_denied"]
    candidate_state: CandidateState
    guard_status: Literal["blocked", "invalidated", "requires_revalidation"]
    primary_deny_code: NonEmptyTrimmedString

    @model_validator(mode="after")
    def validate_terminal_anchor(self) -> "OperatorHistoryDenialSummary":
        if self.terminal_state == "review_denied" and self.run_id is not None:
            raise ValueError("review_denied must stay candidate-anchored without a run_id.")
        if self.terminal_state == "execution_denied" and self.run_id is None:
            raise ValueError("execution_denied must stay run-anchored with a run_id.")
        return self


class OperatorHistoryInvalidationSummary(_SourceAwareHistoryPayload):
    request_id: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString
    candidate_state: Literal["invalidated"]
    guard_status: Literal["invalidated"]
    primary_deny_code: NonEmptyTrimmedString


class OperatorHistoryResultSummary(_SourceAwareHistoryPayload):
    request_id: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString
    run_id: NonEmptyTrimmedString
    result_state: ResultState
    execution_status: ResultState
    row_count: Optional[NonNegativeInt] = None
    result_truncated: Optional[bool] = None
    primary_deny_code: Optional[NonEmptyTrimmedString] = None

    @model_validator(mode="after")
    def validate_result_summary(self) -> "OperatorHistoryResultSummary":
        if self.execution_status != self.result_state:
            raise ValueError("Result state must match the authoritative execution status.")
        if self.execution_status == "execution_denied" and self.primary_deny_code is None:
            raise ValueError(
                "Execution-denied result summaries must include a primary_deny_code."
            )
        if self.execution_status in {"empty", "completed"} and self.row_count is None:
            raise ValueError(
                "Completed and empty result summaries must include a row_count summary."
            )
        if self.execution_status in {"empty", "completed"} and self.result_truncated is None:
            raise ValueError(
                "Completed and empty result summaries must include truncation posture."
            )
        if self.execution_status == "empty" and self.row_count != 0:
            raise ValueError("Empty result summaries must report row_count=0.")
        if self.execution_status == "empty" and self.result_truncated is not False:
            raise ValueError("Empty result summaries must set result_truncated=False.")
        if self.execution_status in {"execution_denied", "failed", "canceled"}:
            if self.row_count is not None:
                raise ValueError(
                    "Terminal non-result outcomes must not expose a synthesized row_count."
                )
            if self.result_truncated is not None:
                raise ValueError(
                    "Terminal non-result outcomes must not expose truncation posture."
                )
        return self
