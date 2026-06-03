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
_VENDOR_COLUMN = "vendor_name"
_QUARTER_COLUMN = "fiscal_quarter"
_SPEND_COLUMNS = ("approved_spend", "approved_amount")

MVPAnswerTruncationStatus = Literal["not_truncated", "truncated"]


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
    answer_text: NonEmptyTrimmedString
    source: MVPAnswerSource
    assumptions: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    validation_status: ResultValidationStatus
    validation_reason_codes: tuple[ResultValidationReason, ...] = Field(
        default_factory=tuple
    )
    truncation_status: MVPAnswerTruncationStatus
    redaction_status: ResultRedactionStatus
    rows_used: NonNegativeInt

    def to_wire_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)


def generate_mvp_answer_summary(
    *,
    rows: list[dict[str, Any]],
    validation: ResultValidationOutcome,
    source_id: str,
    source_family: str | None = None,
    assumptions: tuple[str, ...] = (),
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
    rows_used = min(len(rows), _MAX_SUMMARY_ROWS)
    truncation_status: MVPAnswerTruncationStatus = (
        "truncated" if validation.evidence.result_truncated else "not_truncated"
    )
    redaction_status = validation.evidence.redaction_status

    answer_text = _answer_text(
        rows=rows[:_MAX_SUMMARY_ROWS],
        total_row_count=validation.evidence.row_count,
        source=source,
        assumptions=safe_assumptions,
        validation=validation,
        truncation_status=truncation_status,
        redaction_status=redaction_status,
    )
    return MVPAnswerSummary(
        answer_text=answer_text,
        source=source,
        assumptions=safe_assumptions,
        validation_status=validation.status,
        validation_reason_codes=validation.reason_codes,
        truncation_status=truncation_status,
        redaction_status=redaction_status,
        rows_used=rows_used,
    )


def _answer_text(
    *,
    rows: list[Mapping[str, Any]],
    total_row_count: int,
    source: MVPAnswerSource,
    assumptions: tuple[str, ...],
    validation: ResultValidationOutcome,
    truncation_status: MVPAnswerTruncationStatus,
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
        _truncation_sentence(truncation_status),
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
        f"Top approved vendor spend from {_returned_row_count_text(total_row_count)}: "
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
            f"{column}={_row_text(row.get(column), 'unavailable')}"
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


def _truncation_sentence(status: MVPAnswerTruncationStatus) -> str:
    if status == "truncated":
        return "Truncation: truncated by returned-row limits."
    return "Truncation: not truncated."


def _redaction_sentence(status: ResultRedactionStatus) -> str:
    return "Redaction: " + status.replace("_", " ") + "."


def _row_text(value: object, fallback: str) -> str:
    if value is None:
        return fallback
    return _safe_text(str(value)) or fallback


def _spend_text(value: object) -> str:
    if isinstance(value, bool):
        return "unavailable"
    if isinstance(value, (Decimal, int, float)):
        return str(value)
    return _row_text(value, "unavailable")


def _safe_text_items(values: tuple[str, ...]) -> tuple[str, ...]:
    return sanitize_review_llm_surface_text_items(values)


def _safe_text(value: str) -> str:
    safe_values = sanitize_review_llm_surface_text_items((value,))
    return safe_values[0] if safe_values else ""


def _trim_terminal_period(value: str) -> str:
    return value.rstrip(".")
