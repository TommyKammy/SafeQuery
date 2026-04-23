from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.operator_history.payloads import (
    OperatorHistoryCandidateSummary,
    OperatorHistoryDenialSummary,
    OperatorHistoryInvalidationSummary,
    OperatorHistoryRequestSummary,
    OperatorHistoryResultSummary,
    OperatorHistoryRunSummary,
)


def _source_fields() -> dict[str, object]:
    return {
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
    }


def test_operator_history_summary_payloads_are_source_aware_and_minimized() -> None:
    request = OperatorHistoryRequestSummary(
        request_id="request-123",
        request_state="previewed",
        summary_label="Approved vendor spend",
        occurred_at=datetime.now(timezone.utc),
        **_source_fields(),
    )
    candidate = OperatorHistoryCandidateSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        candidate_state="preview_ready",
        guard_status="allow",
        sql_review_anchor="sha256:preview-123",
        occurred_at=datetime.now(timezone.utc),
        audit_event_id=uuid4(),
        **_source_fields(),
    )
    run = OperatorHistoryRunSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        run_id="run-123",
        execution_status="completed",
        row_count=12,
        result_truncated=True,
        occurred_at=datetime.now(timezone.utc),
        audit_event_id=uuid4(),
        **_source_fields(),
    )

    request_dump = request.model_dump(exclude_none=True)
    candidate_dump = candidate.model_dump(exclude_none=True)
    run_dump = run.model_dump(exclude_none=True)

    assert request_dump["source_id"] == "approved-spend"
    assert candidate_dump["guard_status"] == "allow"
    assert run_dump["execution_status"] == "completed"
    assert run_dump["row_count"] == 12
    assert run_dump["result_truncated"] is True
    assert "question" not in request_dump
    assert "canonical_sql" not in candidate_dump
    assert "rows" not in run_dump


def test_operator_history_candidate_summary_rejects_reopen_source_retargeting() -> None:
    with pytest.raises(ValidationError, match="reopened draft source binding"):
        OperatorHistoryCandidateSummary(
            request_id="request-123",
            candidate_id="candidate-123",
            candidate_state="preview_ready",
            guard_status="allow",
            sql_review_anchor="sha256:preview-123",
            occurred_at=datetime.now(timezone.utc),
            reopened_draft_source_id="marketing-spend",
            **_source_fields(),
        )


def test_operator_history_terminal_summaries_preserve_authoritative_state_mapping() -> None:
    denial = OperatorHistoryDenialSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        terminal_state="review_denied",
        candidate_state="invalidated",
        guard_status="blocked",
        primary_deny_code="DENY_CANDIDATE_INVALIDATED",
        occurred_at=datetime.now(timezone.utc),
        audit_event_id=uuid4(),
        **_source_fields(),
    )
    invalidation = OperatorHistoryInvalidationSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        candidate_state="invalidated",
        guard_status="invalidated",
        primary_deny_code="DENY_CANDIDATE_INVALIDATED",
        occurred_at=datetime.now(timezone.utc),
        audit_event_id=uuid4(),
        **_source_fields(),
    )
    result = OperatorHistoryResultSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        run_id="run-123",
        result_state="empty",
        execution_status="empty",
        row_count=0,
        result_truncated=False,
        occurred_at=datetime.now(timezone.utc),
        audit_event_id=uuid4(),
        **_source_fields(),
    )

    assert denial.terminal_state == "review_denied"
    assert denial.run_id is None
    assert invalidation.guard_status == "invalidated"
    assert result.execution_status == "empty"
    assert result.row_count == 0


def test_operator_history_result_summary_rejects_raw_result_rows() -> None:
    with pytest.raises(ValidationError):
        OperatorHistoryResultSummary(
            request_id="request-123",
            candidate_id="candidate-123",
            run_id="run-123",
            result_state="completed",
            execution_status="completed",
            row_count=1,
            result_truncated=False,
            occurred_at=datetime.now(timezone.utc),
            rows=[{"vendor_name": "Acme"}],
            **_source_fields(),
        )
