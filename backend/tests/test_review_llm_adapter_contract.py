from __future__ import annotations

import json

import pytest

from app.features.review_llm.schema import (
    ReviewLLMAdapterOutput,
    ReviewLLMAdapterOutputError,
    parse_review_llm_adapter_output,
)


def _ready_payload() -> dict[str, object]:
    return {
        "status": "ready",
        "confidence": "high",
        "intent_summary": "Compare approved vendor spend by quarter.",
        "data_used": ["approved_vendor_spend semantic contract v2"],
        "metrics": ["total_spend"],
        "dimensions": ["vendor_id", "calendar_quarter"],
        "filters": ["approval_status = approved"],
        "assumptions": ["Quarter means calendar quarter."],
        "risk_flags": [],
        "clarifying_questions": [],
        "diagnostics": {
            "adapter_version": "review_llm_contract.v1",
            "model": "contract-test",
            "raw_output_excerpt": "No execution authority requested.",
        },
    }


def test_review_llm_adapter_output_has_serializable_explicit_status() -> None:
    output = ReviewLLMAdapterOutput.model_validate(_ready_payload())

    assert output.status == "ready"
    assert output.to_wire_payload()["status"] == "ready"
    assert "canAuthorizeExecution" not in output.to_wire_payload()
    assert "executionAuthorized" not in output.to_wire_payload()


def test_review_llm_adapter_rejects_malformed_output() -> None:
    with pytest.raises(ReviewLLMAdapterOutputError, match="malformed"):
        parse_review_llm_adapter_output("{not-json")

    with pytest.raises(ReviewLLMAdapterOutputError, match="malformed"):
        parse_review_llm_adapter_output(json.dumps({"status": "ready"}))


@pytest.mark.parametrize("payload", [b"\xff", bytearray(b"\xff")])
def test_review_llm_adapter_rejects_invalid_utf8_bytes(payload: bytes | bytearray) -> None:
    with pytest.raises(ReviewLLMAdapterOutputError, match="malformed"):
        parse_review_llm_adapter_output(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "can_authorize_execution",
        "execution_authorized",
        "approved_for_execution",
        "approval_status",
    ],
)
def test_review_llm_adapter_rejects_execution_authorizing_fields(field_name: str) -> None:
    payload = {**_ready_payload(), field_name: True}

    with pytest.raises(ReviewLLMAdapterOutputError, match="execution authority"):
        parse_review_llm_adapter_output(payload)


def test_review_llm_adapter_rejects_deep_execution_authority_without_recursion_error() -> None:
    nested: dict[str, object] = {"execution_authorized": True}
    for _ in range(1500):
        nested = {"wrap": [nested]}

    payload = {**_ready_payload(), "untrusted_context": nested}

    with pytest.raises(ReviewLLMAdapterOutputError, match="execution authority"):
        parse_review_llm_adapter_output(payload)


@pytest.mark.parametrize("status", ["needs_clarification", "blocked"])
def test_review_llm_adapter_allows_low_confidence_only_when_not_ready(status: str) -> None:
    payload = {
        **_ready_payload(),
        "status": status,
        "confidence": "low",
        "clarifying_questions": ["Which fiscal calendar should be used?"],
    }

    output = parse_review_llm_adapter_output(payload)

    assert output.status == status
    assert output.confidence == "low"


def test_review_llm_adapter_rejects_low_confidence_ready_state() -> None:
    payload = {**_ready_payload(), "confidence": "low"}

    with pytest.raises(ReviewLLMAdapterOutputError, match="Low confidence"):
        parse_review_llm_adapter_output(payload)
