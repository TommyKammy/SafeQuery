from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any, Literal, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from app.features.audit.event_model import (
    NonEmptyTrimmedString,
    SourceIdentifier,
    to_camel,
)
from app.features.review_llm.schema import ReviewLLMAdapterOutput


ANSWER_PLAN_CONTRACT_VERSION = "answer_plan.v1"

_MODEL_CONFIG = ConfigDict(
    alias_generator=to_camel,
    extra="forbid",
    frozen=True,
    populate_by_name=True,
)
_REDACTED = "[redacted]"
_SOURCE_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SUPPORTED_SOURCE_FAMILIES = frozenset(("mssql", "postgresql"))
_SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s\"']+"),
    re.compile(r"(?i)\b(?:driver|server|database|uid|pwd|password)\s*=[^;\s\"']+"),
    re.compile(
        r"(?i)(?<![a-z0-9])[\"']?(?:access[_-]?token|refresh[_-]?token|"
        r"id[_-]?token|token|secret|password|passwd|pwd|credential|"
        r"client[_-]?secret|api[_-]?key|private[_-]?key)[\"']?\s*[:=]\s*"
        r"(?:[\"'][^\"']*[\"']|[^;,\s\"'}]+)"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]+"),
    re.compile(
        r"(?i)(?<![a-z0-9])(?:password|passwd|pwd|secret|token|credential|"
        r"client[_ -]?secret|api[_ -]?key|private[_ -]?key)(?![a-z0-9])"
    ),
)
_UNSAFE_INPUT_KEYS = frozenset(
    {
        "connection",
        "connection_reference",
        "connection_string",
        "connection_strings",
        "credentials",
        "raw_result_set",
        "raw_result_sets",
        "raw_rows",
        "raw_sql",
        "result_rows",
        "scratchpad",
        "hidden_prompt",
        "system_prompt",
    }
)


class AnswerPlanSemanticEvidence(BaseModel):
    model_config = _MODEL_CONFIG

    contract_version: Optional[NonEmptyTrimmedString] = None
    mapping_id: Optional[NonEmptyTrimmedString] = None
    classification: Optional[NonEmptyTrimmedString] = None
    metric: Optional[NonEmptyTrimmedString] = None
    dimensions: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    filters: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)


class AnswerPlanCandidateSummary(BaseModel):
    model_config = _MODEL_CONFIG

    candidate_id: Optional[NonEmptyTrimmedString] = None
    source_id: Optional[SourceIdentifier] = None
    source_family: Optional[NonEmptyTrimmedString] = None
    selected_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    row_limit: Optional[PositiveInt] = None


class AnswerPlanGuardSummary(BaseModel):
    model_config = _MODEL_CONFIG

    guard_decision: Optional[Literal["allow", "reject"]] = None
    guard_version: Optional[NonEmptyTrimmedString] = None
    primary_deny_code: Optional[NonEmptyTrimmedString] = None
    denial_reason: Optional[NonEmptyTrimmedString] = None


class AnswerPlanPayload(BaseModel):
    model_config = _MODEL_CONFIG

    contract_version: Literal[ANSWER_PLAN_CONTRACT_VERSION] = ANSWER_PLAN_CONTRACT_VERSION
    question: NonEmptyTrimmedString
    narrative: NonEmptyTrimmedString
    steps: tuple[NonEmptyTrimmedString, ...]
    assumptions: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    risks: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    clarifications: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    semantic_evidence: tuple[AnswerPlanSemanticEvidence, ...] = Field(
        default_factory=tuple
    )
    candidate_summary: AnswerPlanCandidateSummary = Field(
        default_factory=AnswerPlanCandidateSummary
    )
    guard_summary: AnswerPlanGuardSummary = Field(default_factory=AnswerPlanGuardSummary)
    advisory_only: Literal[True] = True
    can_authorize_execution: Literal[False] = False

    def to_wire_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def build_answer_plan_from_review(
    *,
    question: str,
    review: ReviewLLMAdapterOutput,
    semantic_mapping: Mapping[str, object],
    candidate_metadata: Mapping[str, object],
    guard_metadata: Mapping[str, object],
) -> AnswerPlanPayload:
    semantic_evidence = _build_semantic_evidence(semantic_mapping)
    candidate_summary = _build_candidate_summary(candidate_metadata)
    guard_summary = _build_guard_summary(guard_metadata)
    risks = _build_risks(review=review, semantic_evidence=semantic_evidence)
    clarifications = _sanitize_text_items(review.clarifying_questions)
    assumptions = _sanitize_text_items(review.assumptions)

    return AnswerPlanPayload(
        question=_sanitize_text(question),
        narrative=_build_narrative(
            review=review,
            semantic_evidence=semantic_evidence,
        ),
        steps=_build_steps(
            review=review,
            candidate_summary=candidate_summary,
        ),
        assumptions=assumptions,
        risks=risks,
        clarifications=clarifications,
        semantic_evidence=(semantic_evidence,),
        candidate_summary=candidate_summary,
        guard_summary=guard_summary,
        advisory_only=True,
        can_authorize_execution=False,
    )


def _build_semantic_evidence(
    semantic_mapping: Mapping[str, object],
) -> AnswerPlanSemanticEvidence:
    safe_mapping = _filter_safe_mapping(semantic_mapping)
    return AnswerPlanSemanticEvidence(
        contract_version=_optional_sanitized_string(safe_mapping.get("contract_version")),
        mapping_id=_optional_sanitized_string(safe_mapping.get("mapping_id")),
        classification=_optional_sanitized_string(safe_mapping.get("classification")),
        metric=_optional_sanitized_string(safe_mapping.get("metric")),
        dimensions=_sanitize_text_items(_as_iterable(safe_mapping.get("dimensions"))),
        filters=_sanitize_text_items(_as_iterable(safe_mapping.get("filters"))),
    )


def _build_candidate_summary(
    candidate_metadata: Mapping[str, object],
) -> AnswerPlanCandidateSummary:
    safe_metadata = _filter_safe_mapping(candidate_metadata)
    return AnswerPlanCandidateSummary(
        candidate_id=_optional_sanitized_string(safe_metadata.get("candidate_id")),
        source_id=_source_identifier_or_none(safe_metadata.get("source_id")),
        source_family=_source_family_or_none(safe_metadata.get("source_family")),
        selected_columns=_sanitize_text_items(
            _as_iterable(safe_metadata.get("selected_columns"))
        ),
        row_limit=_positive_int_or_none(safe_metadata.get("row_limit")),
    )


def _build_guard_summary(guard_metadata: Mapping[str, object]) -> AnswerPlanGuardSummary:
    safe_metadata = _filter_safe_mapping(guard_metadata)
    return AnswerPlanGuardSummary(
        guard_decision=_guard_decision_or_none(safe_metadata.get("guard_decision")),
        guard_version=_optional_sanitized_string(safe_metadata.get("guard_version")),
        primary_deny_code=_optional_sanitized_string(
            safe_metadata.get("primary_deny_code")
        ),
        denial_reason=_optional_sanitized_string(safe_metadata.get("denial_reason")),
    )


def _build_narrative(
    *,
    review: ReviewLLMAdapterOutput,
    semantic_evidence: AnswerPlanSemanticEvidence,
) -> str:
    narrative = (
        "The candidate is intended to "
        f"{_sentence_fragment(_sanitize_text(review.intent_summary))}."
    )
    if review.dimensions or review.metrics or review.filters:
        clauses = []
        if review.dimensions:
            clauses.append(
                "group the answer by "
                + _join_business_items(_sanitize_text_items(review.dimensions))
            )
        if review.metrics:
            clauses.append(
                "use "
                + _join_business_items(_sanitize_text_items(review.metrics))
                + " as the measure"
            )
        if review.filters:
            clauses.append(
                "apply " + _join_business_items(_sanitize_text_items(review.filters))
            )
        narrative += " It should " + _join_clauses(clauses) + "."

    evidence_label = _semantic_evidence_label(semantic_evidence)
    if evidence_label is not None:
        narrative += f" Semantic contract evidence: {evidence_label}."

    return narrative


def _build_steps(
    *,
    review: ReviewLLMAdapterOutput,
    candidate_summary: AnswerPlanCandidateSummary,
) -> tuple[str, ...]:
    steps = []
    if candidate_summary.candidate_id and candidate_summary.source_id:
        steps.append(
            "Answer the question using candidate "
            f"{candidate_summary.candidate_id} for source {candidate_summary.source_id}."
        )
    elif candidate_summary.candidate_id:
        steps.append(f"Answer the question using candidate {candidate_summary.candidate_id}.")

    metrics = _sanitize_text_items(review.metrics)
    if metrics:
        steps.append(f"Use the approved business metric {_join_business_items(metrics)}.")

    dimensions = _sanitize_text_items(review.dimensions)
    if dimensions:
        steps.append(f"Group or label the answer by {_join_business_items(dimensions)}.")

    filters = _sanitize_text_items(review.filters)
    if filters:
        steps.append(f"Apply the business filter {_join_business_items(filters)}.")

    steps.append(
        "Keep the output at plan level; do not summarize result rows in this step."
    )
    return tuple(steps)


def _build_risks(
    *,
    review: ReviewLLMAdapterOutput,
    semantic_evidence: AnswerPlanSemanticEvidence,
) -> tuple[str, ...]:
    risks = list(_sanitize_text_items(review.risk_flags))
    if semantic_evidence.classification in {"ambiguous", "unsupported"}:
        risks.append(
            "Semantic mapping is "
            f"{semantic_evidence.classification}; do not present the plan as a final answer."
        )
    if review.status == "blocked":
        risks.append("Review output is blocked and must not be used as an answer.")
    return _dedupe(risks)


def _semantic_evidence_label(
    semantic_evidence: AnswerPlanSemanticEvidence,
) -> str | None:
    if semantic_evidence.contract_version and semantic_evidence.mapping_id:
        return f"{semantic_evidence.contract_version} / {semantic_evidence.mapping_id}"
    return semantic_evidence.contract_version or semantic_evidence.mapping_id


def _filter_safe_mapping(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        str(key): value
        for key, value in payload.items()
        if str(key).casefold() not in _UNSAFE_INPUT_KEYS
    }


def _sanitize_text_items(values: Iterable[object]) -> tuple[str, ...]:
    return _dedupe(_sanitize_text(value) for value in values if value is not None)


def _sanitize_text(value: object) -> str:
    sanitized = str(value).strip()
    for pattern in _SECRET_VALUE_PATTERNS:
        sanitized = pattern.sub(_REDACTED, sanitized)
    return sanitized


def _optional_sanitized_string(value: object) -> str | None:
    if value is None:
        return None
    sanitized = _sanitize_text(value)
    return sanitized or None


def _as_iterable(value: object) -> Iterable[object]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return value
    return (value,)


def _positive_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _guard_decision_or_none(value: object) -> Optional[Literal["allow", "reject"]]:
    if value in {"allow", "reject"}:
        return value
    return None


def _source_identifier_or_none(value: object) -> SourceIdentifier | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if _SOURCE_IDENTIFIER_PATTERN.fullmatch(normalized):
        return cast(SourceIdentifier, normalized)
    return None


def _source_family_or_none(value: object) -> str | None:
    sanitized = _optional_sanitized_string(value)
    if sanitized in _SUPPORTED_SOURCE_FAMILIES:
        return sanitized
    return None


def _sentence_fragment(value: str) -> str:
    value = value.rstrip(".")
    if not value:
        return value
    return value[0].lower() + value[1:]


def _join_business_items(values: Iterable[str]) -> str:
    items = tuple(values)
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _join_clauses(values: Iterable[str]) -> str:
    clauses = tuple(values)
    if len(clauses) <= 1:
        return "".join(clauses)
    return ", ".join(clauses[:-1]) + f", and {clauses[-1]}"


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return tuple(deduped)
