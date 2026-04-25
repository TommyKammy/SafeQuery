from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.operator_history.payloads import (
    OperatorHistoryAuthContext,
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


def _auth_context() -> OperatorHistoryAuthContext:
    return OperatorHistoryAuthContext(
        actor_subject="user:alice",
        session_id="application-session-redacted",
        auth_source="enterprise-bridge",
        entitlement_decision="allow",
    )


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


def test_operator_history_summary_payloads_are_immutable() -> None:
    candidate = OperatorHistoryCandidateSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        candidate_state="preview_ready",
        guard_status="allow",
        sql_review_anchor="sha256:preview-123",
        occurred_at=datetime.now(timezone.utc),
        **_source_fields(),
    )

    with pytest.raises(ValidationError, match="Instance is frozen"):
        candidate.source_id = "marketing-spend"

    with pytest.raises(ValidationError, match="Instance is frozen"):
        candidate.reopened_draft_source_id = "marketing-spend"


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


def test_operator_history_run_summary_requires_primary_deny_code_when_execution_denied() -> None:
    with pytest.raises(ValidationError, match="include a primary_deny_code"):
        OperatorHistoryRunSummary(
            request_id="request-123",
            candidate_id="candidate-123",
            run_id="run-123",
            execution_status="execution_denied",
            occurred_at=datetime.now(timezone.utc),
            audit_event_id=uuid4(),
            **_source_fields(),
        )


def test_operator_history_payloads_can_represent_runtime_control_denials() -> None:
    run = OperatorHistoryRunSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        run_id="run-123",
        execution_status="execution_denied",
        primary_deny_code="DENY_RUNTIME_RATE_LIMIT",
        occurred_at=datetime.now(timezone.utc),
        audit_event_id=uuid4(),
        **_source_fields(),
    )
    result = OperatorHistoryResultSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        run_id="run-123",
        result_state="execution_denied",
        execution_status="execution_denied",
        primary_deny_code="DENY_RUNTIME_RATE_LIMIT",
        occurred_at=datetime.now(timezone.utc),
        audit_event_id=uuid4(),
        **_source_fields(),
    )

    assert run.primary_deny_code == "DENY_RUNTIME_RATE_LIMIT"
    assert result.primary_deny_code == "DENY_RUNTIME_RATE_LIMIT"
    assert "rows" not in run.model_dump(exclude_none=True)
    assert "rows" not in result.model_dump(exclude_none=True)


def test_operator_history_payloads_retain_minimized_auth_context_without_secrets() -> None:
    request = OperatorHistoryRequestSummary(
        request_id="request-123",
        request_state="previewed",
        summary_label="Approved vendor spend",
        occurred_at=datetime.now(timezone.utc),
        auth_context=_auth_context(),
        **_source_fields(),
    )
    denial = OperatorHistoryDenialSummary(
        request_id="request-123",
        candidate_id="candidate-123",
        terminal_state="review_denied",
        candidate_state="blocked",
        guard_status="blocked",
        primary_deny_code="DENY_ENTITLEMENT_CHANGED",
        occurred_at=datetime.now(timezone.utc),
        auth_context=OperatorHistoryAuthContext(
            actor_subject="user:alice",
            session_id="application-session-redacted",
            auth_source="enterprise-bridge",
            entitlement_decision="deny",
        ),
        **_source_fields(),
    )

    request_dump = request.model_dump(exclude_none=True)
    denial_dump = denial.model_dump(exclude_none=True)

    assert request_dump["auth_context"] == {
        "actor_subject": "user:alice",
        "session_id": "application-session-redacted",
        "auth_source": "enterprise-bridge",
        "entitlement_decision": "allow",
    }
    assert denial_dump["auth_context"]["entitlement_decision"] == "deny"
    for serialized in (str(request_dump).lower(), str(denial_dump).lower()):
        assert "csrf" not in serialized
        assert "cookie" not in serialized
        assert "token" not in serialized
        assert "secret" not in serialized


def test_operator_history_auth_context_rejects_raw_identity_provider_material() -> None:
    with pytest.raises(ValidationError):
        OperatorHistoryAuthContext(
            actor_subject="user:alice",
            session_id="application-session-redacted",
            auth_source="enterprise-bridge",
            entitlement_decision="allow",
            csrf_token="csrf-token-123",  # noqa: S106 - secret-like negative test value
        )


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


@pytest.mark.parametrize(
    ("payload_overrides", "message"),
    [
        (
            {
                "result_state": "execution_denied",
                "execution_status": "execution_denied",
            },
            "include a primary_deny_code",
        ),
        (
            {"result_state": "completed", "execution_status": "completed", "row_count": 1},
            "include truncation posture",
        ),
        (
            {
                "result_state": "empty",
                "execution_status": "empty",
                "row_count": 0,
                "result_truncated": True,
            },
            "set result_truncated=False",
        ),
    ],
)
def test_operator_history_result_summary_enforces_explicit_truncation_posture(
    payload_overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        OperatorHistoryResultSummary(
            request_id="request-123",
            candidate_id="candidate-123",
            run_id="run-123",
            occurred_at=datetime.now(timezone.utc),
            audit_event_id=uuid4(),
            **_source_fields(),
            **payload_overrides,
        )
