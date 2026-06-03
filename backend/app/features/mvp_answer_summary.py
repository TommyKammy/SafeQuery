from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from app.features.audit.event_model import (
    NonEmptyTrimmedString,
    SourceFamily,
    SourceIdentifier,
    to_camel,
)
from app.features.result_validation import (
    ResultRedactionStatus,
    ResultValidationOutcome,
    ResultValidationReason,
    ResultValidationStatus,
)
from app.features.review_llm.answer_plan import sanitize_review_llm_surface_text_items

MVP_ANSWER_SUMMARY_CONTRACT_VERSION = "mvp_answer_summary.v1"
_MODEL_CONFIG = ConfigDict(
    alias_generator=to_camel,
    extra="forbid",
    frozen=True,
    populate_by_name=True,
)
_MAX_SUMMARY_ROWS = 5
_MAX_CELL_TEXT_CHARS = 160
_TRUNCATED_CELL_SUFFIX = "... [truncated]"
_UNNAMED_COLUMN_LABEL = "unnamed column"
_VENDOR_COLUMN = "vendor_name"
_QUARTER_COLUMN = "fiscal_quarter"
_SPEND_COLUMNS = ("approved_spend", "approved_amount")

MVPAnswerTruncationStatus = Literal["not_truncated", "truncated"]
MVPAnswerState = Literal["answered", "insufficient_evidence"]
MVPInsufficientEvidenceReason = Literal[
    "no_rows",
    "missing_columns",
    "unsafe_truncation",
    "blocking_validation_warnings",
]
MVPInsufficientEvidenceNextAction = Literal[
    "revise_query_filters_or_source",
    "revise_query_or_semantic_contract_columns",
    "rerun_with_trusted_top_n_or_higher_limit",
    "inspect_blocking_validation_warnings",
]


class MVPAnswerSource(BaseModel):
    model_config = _MODEL_CONFIG

    source_id: SourceIdentifier
    source_family: Optional[SourceFamily] = None
    semantic_contract_version: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString


class MVPAnswerSummary(BaseModel):
    model_config = _MODEL_CONFIG

    contract_version: Literal[MVP_ANSWER_SUMMARY_CONTRACT_VERSION] = (
        MVP_ANSWER_SUMMARY_CONTRACT_VERSION
    )
    answer_state: MVPAnswerState = "answered"
    answer_text: NonEmptyTrimmedString
    source: MVPAnswerSource
    assumptions: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    validation_status: ResultValidationStatus
    validation_reason_codes: tuple[ResultValidationReason, ...] = Field(
        default_factory=tuple
    )
    insufficient_evidence_reason: Optional[MVPInsufficientEvidenceReason] = None
    next_action: Optional[MVPInsufficientEvidenceNextAction] = None
    truncation_status: MVPAnswerTruncationStatus
    redaction_status: ResultRedactionStatus
    rows_used: NonNegativeInt

    def to_wire_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def generate_mvp_answer_summary(
    *,
    rows: list[dict[str, Any]],
    validation: ResultValidationOutcome,
    source_id: str,
    source_family: str | None = None,
    assumptions: tuple[str, ...] = (),
    truncation_reason: str | None = None,
    freeform_llm_answer: str | None = None,
) -> MVPAnswerSummary:
    del freeform_llm_answer

    safe_assumptions = _safe_text_items(assumptions)
    source = MVPAnswerSource(
        source_id=source_id,
        source_family=source_family,
        semantic_contract_version=validation.semantic_contract_version,
        candidate_id=validation.candidate_id,
    )
    display_rows = rows[:_MAX_SUMMARY_ROWS]
    rows_used = len(display_rows)
    truncation_status: MVPAnswerTruncationStatus = (
        "truncated" if validation.evidence.result_truncated else "not_truncated"
    )
    redaction_status = validation.evidence.redaction_status
    insufficient_evidence = _insufficient_evidence_decision(validation)

    answer_text = (
        _insufficient_evidence_answer_text(insufficient_evidence)
        if insufficient_evidence is not None
        else _answer_text(
            rows=display_rows,
            total_row_count=validation.evidence.row_count,
            source=source,
            assumptions=safe_assumptions,
            validation=validation,
            truncation_status=truncation_status,
            truncation_reason=truncation_reason,
            redaction_status=redaction_status,
        )
    )
    return MVPAnswerSummary(
        answer_state=(
            "insufficient_evidence"
            if insufficient_evidence is not None
            else "answered"
        ),
        answer_text=answer_text,
        source=source,
        assumptions=safe_assumptions,
        validation_status=validation.status,
        validation_reason_codes=validation.reason_codes,
        insufficient_evidence_reason=(
            insufficient_evidence[0] if insufficient_evidence is not None else None
        ),
        next_action=(
            insufficient_evidence[1] if insufficient_evidence is not None else None
        ),
        truncation_status=truncation_status,
        redaction_status=redaction_status,
        rows_used=rows_used,
    )


def _insufficient_evidence_decision(
    validation: ResultValidationOutcome,
) -> tuple[MVPInsufficientEvidenceReason, MVPInsufficientEvidenceNextAction] | None:
    reasons = set(validation.reason_codes)
    if "no_rows" in reasons:
        return ("no_rows", "revise_query_filters_or_source")
    if "missing_expected_columns" in reasons or "missing_required_columns" in reasons:
        return ("missing_columns", "revise_query_or_semantic_contract_columns")
    if "result_truncated" in reasons:
        return ("unsafe_truncation", "rerun_with_trusted_top_n_or_higher_limit")
    if validation.status != "pass":
        return ("blocking_validation_warnings", "inspect_blocking_validation_warnings")
    return None


def _insufficient_evidence_answer_text(
    decision: tuple[MVPInsufficientEvidenceReason, MVPInsufficientEvidenceNextAction],
) -> str:
    reason, _next_action = decision
    if reason == "no_rows":
        return (
            "Insufficient evidence: no rows were returned. "
            "Next action: revise the query filters or source selection before requesting an answer."
        )
    if reason == "missing_columns":
        return (
            "Insufficient evidence: expected result columns were missing. "
            "Next action: revise the SQL projection or semantic contract columns before requesting an answer."
        )
    if reason == "unsafe_truncation":
        return (
            "Insufficient evidence: result was truncated before the top set could be trusted. "
            "Next action: rerun with an authoritative ORDER BY, tighter filters, or a higher trusted limit."
        )
    return (
        "Insufficient evidence: validation warnings block answer generation. "
        "Next action: inspect the validation warnings before requesting an answer."
    )


def _answer_text(
    *,
    rows: list[Mapping[str, Any]],
    total_row_count: int,
    source: MVPAnswerSource,
    assumptions: tuple[str, ...],
    validation: ResultValidationOutcome,
    truncation_status: MVPAnswerTruncationStatus,
    truncation_reason: str | None,
    redaction_status: ResultRedactionStatus,
) -> str:
    segments = [
        _row_summary(
            rows=rows,
            total_row_count=total_row_count,
            observed_columns=validation.evidence.observed_columns,
        ),
        _source_sentence(source),
        _assumptions_sentence(assumptions),
        _validation_sentence(validation),
        _truncation_sentence(truncation_status, truncation_reason),
        _redaction_sentence(redaction_status),
    ]
    return " ".join(segment for segment in segments if segment)


def _row_summary(
    *,
    rows: list[Mapping[str, Any]],
    total_row_count: int,
    observed_columns: tuple[str, ...],
) -> str:
    if not rows:
        return "No rows were returned, so no vendor spend ranking is available."

    if not _has_vendor_spend_shape(observed_columns):
        return _generic_row_summary(
            rows=rows,
            total_row_count=total_row_count,
            observed_columns=observed_columns,
        )

    row_entries = []
    for index, row in enumerate(rows, start=1):
        vendor = _row_text(row.get(_VENDOR_COLUMN), "unknown vendor")
        quarter = _row_text(row.get(_QUARTER_COLUMN), "unspecified period")
        spend = _spend_text(_spend_value(row))
        row_entries.append(f"{index}. {vendor} ({quarter}) - {spend}")
    return (
        _vendor_spend_intro(
            total_row_count=total_row_count,
            displayed_row_count=len(rows),
        )
        + "; ".join(row_entries)
        + "."
    )


def _generic_row_summary(
    *,
    rows: list[Mapping[str, Any]],
    total_row_count: int,
    observed_columns: tuple[str, ...],
) -> str:
    if not observed_columns:
        return (
            f"Returned {_display_row_count_text(total_row_count)}; "
            "no displayable columns are available."
        )

    row_entries = []
    for index, row in enumerate(rows, start=1):
        cells = [
            f"{_column_label(column)}={_row_text(row.get(column), 'unavailable')}"
            for column in observed_columns
        ]
        row_entries.append(f"{index}. " + ", ".join(cells))
    return (
        f"Returned {_display_row_count_text(total_row_count)}; "
        f"showing {_display_row_count_text(len(rows))}: "
        + "; ".join(row_entries)
        + "."
    )


def _has_vendor_spend_shape(observed_columns: tuple[str, ...]) -> bool:
    observed = set(observed_columns)
    return _VENDOR_COLUMN in observed and any(
        column in observed for column in _SPEND_COLUMNS
    )


def _spend_value(row: Mapping[str, Any]) -> object:
    for column in _SPEND_COLUMNS:
        if column in row:
            return row.get(column)
    return None


def _vendor_spend_intro(*, total_row_count: int, displayed_row_count: int) -> str:
    if displayed_row_count < total_row_count:
        return (
            "Approved vendor spend rows from "
            f"{_returned_row_count_text(total_row_count)}; "
            f"showing {_display_row_count_text(displayed_row_count)}: "
        )
    return (
        "Approved vendor spend rows from "
        f"{_returned_row_count_text(total_row_count)}: "
    )


def _returned_row_count_text(count: int) -> str:
    noun = "row" if count == 1 else "rows"
    return f"{count} returned {noun}"


def _display_row_count_text(count: int) -> str:
    noun = "row" if count == 1 else "rows"
    return f"{count} {noun}"


def _source_sentence(source: MVPAnswerSource) -> str:
    if source.source_family is None:
        return f"Source: {source.source_id}."
    return f"Source: {source.source_id} ({source.source_family})."


def _assumptions_sentence(assumptions: tuple[str, ...]) -> str:
    if not assumptions:
        return "Assumptions: none."
    return "Assumptions: " + "; ".join(
        _trim_terminal_period(assumption) for assumption in assumptions
    ) + "."


def _validation_sentence(validation: ResultValidationOutcome) -> str:
    if not validation.reason_codes:
        return f"Validation: {validation.status}."
    return (
        f"Validation: {validation.status} "
        f"({', '.join(validation.reason_codes)})."
    )


def _truncation_sentence(
    status: MVPAnswerTruncationStatus,
    reason: str | None,
) -> str:
    if status != "truncated":
        return "Truncation: not truncated."
    if reason == "row_limit":
        return "Truncation: truncated by returned-row limits."
    if reason == "payload_limit":
        return "Truncation: truncated by payload limits."
    return "Truncation: truncated."


def _redaction_sentence(status: ResultRedactionStatus) -> str:
    return "Redaction: " + status.replace("_", " ") + "."


def _row_text(value: object, fallback: str) -> str:
    if value is None:
        return fallback
    return _bounded_text(_safe_text(str(value))) or fallback


def _spend_text(value: object) -> str:
    if isinstance(value, bool):
        return "unavailable"
    if isinstance(value, (Decimal, int, float)):
        return _bounded_text(str(value))
    return _row_text(value, "unavailable")


def _safe_text_items(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        _bounded_text(value)
        for value in sanitize_review_llm_surface_text_items(values)
    )


def _safe_text(value: str) -> str:
    safe_values = sanitize_review_llm_surface_text_items((value,))
    return safe_values[0] if safe_values else ""


def _bounded_text(value: str) -> str:
    if len(value) <= _MAX_CELL_TEXT_CHARS:
        return value
    prefix_length = _MAX_CELL_TEXT_CHARS - len(_TRUNCATED_CELL_SUFFIX)
    return value[:prefix_length].rstrip() + _TRUNCATED_CELL_SUFFIX


def _column_label(value: str) -> str:
    return _bounded_text(_safe_text(value)) or _UNNAMED_COLUMN_LABEL


def _trim_terminal_period(value: str) -> str:
    return value.rstrip(".")
