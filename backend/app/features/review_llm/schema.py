from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.features.audit.event_model import NonEmptyTrimmedString, to_camel


ReviewLLMStatus = Literal["ready", "needs_clarification", "blocked"]
ReviewLLMConfidence = Literal["low", "medium", "high", "unknown"]

REVIEW_LLM_CONTRACT_VERSION = "review_llm_adapter_output.v1"

_REVIEW_LLM_MODEL_CONFIG = ConfigDict(
    alias_generator=to_camel,
    extra="forbid",
    frozen=True,
    populate_by_name=True,
)

_EXECUTION_AUTHORITY_KEYS = frozenset(
    {
        "approval_status",
        "approved_for_execution",
        "authorize_execution",
        "authorized_for_execution",
        "can_authorize_execution",
        "can_execute",
        "execute",
        "execution_approved",
        "execution_authority",
        "execution_authorized",
        "execution_decision",
        "execution_permission",
        "is_executable",
        "query_candidate_id",
        "run_query",
        "sql_execution_approved",
    }
)


class ReviewLLMAdapterOutputError(ValueError):
    """Raised when review LLM output cannot satisfy the critique-only contract."""


class ReviewLLMAdapterDiagnostics(BaseModel):
    model_config = _REVIEW_LLM_MODEL_CONFIG

    adapter_version: NonEmptyTrimmedString
    model: Optional[NonEmptyTrimmedString] = None
    provider: Optional[NonEmptyTrimmedString] = None
    prompt_version: Optional[NonEmptyTrimmedString] = None
    response_id: Optional[NonEmptyTrimmedString] = None
    raw_output_excerpt: Optional[NonEmptyTrimmedString] = None


class ReviewLLMAdapterOutput(BaseModel):
    model_config = _REVIEW_LLM_MODEL_CONFIG

    contract_version: Literal[REVIEW_LLM_CONTRACT_VERSION] = REVIEW_LLM_CONTRACT_VERSION
    status: ReviewLLMStatus
    confidence: ReviewLLMConfidence = "unknown"
    intent_summary: NonEmptyTrimmedString
    data_used: list[NonEmptyTrimmedString] = Field(default_factory=list)
    metrics: list[NonEmptyTrimmedString] = Field(default_factory=list)
    dimensions: list[NonEmptyTrimmedString] = Field(default_factory=list)
    filters: list[NonEmptyTrimmedString] = Field(default_factory=list)
    assumptions: list[NonEmptyTrimmedString] = Field(default_factory=list)
    risk_flags: list[NonEmptyTrimmedString] = Field(default_factory=list)
    clarifying_questions: list[NonEmptyTrimmedString] = Field(default_factory=list)
    diagnostics: ReviewLLMAdapterDiagnostics

    def to_wire_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)

    @model_validator(mode="after")
    def validate_confidence_status(self) -> "ReviewLLMAdapterOutput":
        if self.confidence == "low" and self.status == "ready":
            raise ValueError(
                "Low confidence review output must use needs_clarification or blocked status."
            )
        return self


def parse_review_llm_adapter_output(
    output: str | bytes | bytearray | Mapping[str, object],
) -> ReviewLLMAdapterOutput:
    decoded = _decode_review_llm_output(output)
    forbidden_key = _find_execution_authority_key(decoded)
    if forbidden_key is not None:
        raise ReviewLLMAdapterOutputError(
            "Review LLM output cannot carry execution authority field "
            f"'{forbidden_key}'."
        )

    try:
        return ReviewLLMAdapterOutput.model_validate(decoded)
    except (RecursionError, ValidationError) as exc:
        raise ReviewLLMAdapterOutputError(
            f"Review LLM adapter output is malformed: {exc}"
        ) from exc


def _decode_review_llm_output(
    output: str | bytes | bytearray | Mapping[str, object],
) -> Mapping[str, object]:
    if isinstance(output, Mapping):
        return output

    try:
        decoded = json.loads(output)
    except (
        RecursionError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ReviewLLMAdapterOutputError(
            "Review LLM adapter output is malformed: expected a JSON object."
        ) from exc

    if not isinstance(decoded, Mapping):
        raise ReviewLLMAdapterOutputError(
            "Review LLM adapter output is malformed: expected a JSON object."
        )

    return decoded


def _find_execution_authority_key(value: object) -> str | None:
    stack = [value]
    seen_container_ids: set[int] = set()

    while stack:
        current_value = stack.pop()
        if isinstance(current_value, Mapping):
            container_id = id(current_value)
            if container_id in seen_container_ids:
                continue
            seen_container_ids.add(container_id)

            for key, nested_value in current_value.items():
                normalized_key = str(key).strip()
                snake_key = "".join(
                    f"_{character.lower()}" if character.isupper() else character
                    for character in normalized_key
                ).strip("_")
                if snake_key.casefold() in _EXECUTION_AUTHORITY_KEYS:
                    return str(key)
                if isinstance(nested_value, (Mapping, list)):
                    stack.append(nested_value)
        elif isinstance(current_value, list):
            container_id = id(current_value)
            if container_id in seen_container_ids:
                continue
            seen_container_ids.add(container_id)

            for item in current_value:
                if isinstance(item, (Mapping, list)):
                    stack.append(item)

    return None
