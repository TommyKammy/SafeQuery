from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

from app.features.audit.event_model import NonEmptyTrimmedString

ResultValidationStatus = Literal["pass", "warn", "fail"]
ResultValidationReason = Literal[
    "missing_expected_columns",
    "missing_required_columns",
    "column_sensitivity_metadata_missing",
    "no_rows",
    "under_minimum_rows",
    "row_count_mismatch",
    "result_truncated",
    "null_values_present",
    "outlier_values_present",
    "aggregation_shape_mismatch",
]
ColumnSensitivity = Literal["public", "sensitive"]
ResultRedactionStatus = Literal["not_required", "applied", "fail"]


class ResultValidationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    semantic_contract_version: Optional[NonEmptyTrimmedString] = None
    expected_columns: tuple[NonEmptyTrimmedString, ...]
    required_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    minimum_row_count: NonNegativeInt = 0
    expected_row_count: Optional[NonNegativeInt] = None
    warn_on_null_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    outlier_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    outlier_numeric_min: Optional[float] = None
    outlier_numeric_max: Optional[float] = None
    aggregate_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    redaction_required: bool = False
    column_sensitivity: Optional[dict[NonEmptyTrimmedString, ColumnSensitivity]] = None


class ResultValidationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    semantic_contract_version: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString
    execution_run_id: UUID
    row_count: NonNegativeInt
    row_limit: PositiveInt
    result_truncated: bool


class ResultValidationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_columns: tuple[NonEmptyTrimmedString, ...]
    required_columns: tuple[NonEmptyTrimmedString, ...]
    observed_columns: tuple[NonEmptyTrimmedString, ...]
    missing_expected_columns: tuple[NonEmptyTrimmedString, ...] = Field(
        default_factory=tuple
    )
    missing_required_columns: tuple[NonEmptyTrimmedString, ...] = Field(
        default_factory=tuple
    )
    row_count: NonNegativeInt
    row_limit: PositiveInt
    result_truncated: bool
    aggregation_shape: Literal["not_applicable", "valid", "mismatch"] = (
        "not_applicable"
    )
    null_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    outlier_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    redaction_status: ResultRedactionStatus = "not_required"
    redacted_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    unclassified_columns: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)


class ResultValidationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ResultValidationStatus
    reason_codes: tuple[ResultValidationReason, ...] = Field(default_factory=tuple)
    semantic_contract_version: NonEmptyTrimmedString
    candidate_id: NonEmptyTrimmedString
    execution_run_id: UUID
    evidence: ResultValidationEvidence

    @property
    def answer_generation_allowed(self) -> bool:
        return self.status != "fail"

    def require_answer_generation_allowed(self) -> None:
        if not self.answer_generation_allowed:
            raise ResultValidationError(
                "Result validation failed before answer generation: "
                + ",".join(self.reason_codes)
            )


class ResultValidationError(RuntimeError):
    """Raised when a failed result validation must block answer generation."""


def validate_execution_result(
    *,
    rows: list[dict[str, Any]],
    metadata: ResultValidationMetadata,
    contract: ResultValidationContract,
    redaction_source_rows: list[dict[str, Any]] | None = None,
) -> ResultValidationOutcome:
    expected_columns = _unique_ordered(contract.expected_columns)
    required_columns = _unique_ordered(contract.required_columns)
    observed_columns = _observed_columns(rows)
    redaction_observed_columns = (
        _observed_columns(redaction_source_rows)
        if redaction_source_rows is not None
        else observed_columns
    )
    redaction_status, redacted_columns, unclassified_columns = _redaction_evidence(
        observed_columns=redaction_observed_columns,
        contract=contract,
    )
    contract_observed_columns = (
        observed_columns
        if redaction_source_rows is not None and contract.redaction_required
        else _contract_observed_columns_after_redaction(
            observed_columns=observed_columns,
            contract=contract,
        )
    )
    observed_set = set(contract_observed_columns)
    missing_expected_columns = tuple(
        column for column in expected_columns if column not in observed_set
    )
    missing_required_columns = tuple(
        column for column in required_columns if column not in observed_set
    )
    null_columns = _columns_with_nulls(
        rows=rows,
        columns=contract.warn_on_null_columns,
    )
    outlier_columns = _columns_with_outliers(
        rows=rows,
        columns=contract.outlier_columns,
        minimum=contract.outlier_numeric_min,
        maximum=contract.outlier_numeric_max,
    )
    aggregation_shape = _aggregation_shape(
        rows=rows,
        expected_columns=expected_columns,
        observed_columns=contract_observed_columns,
        aggregate_columns=contract.aggregate_columns,
    )

    reason_codes: list[ResultValidationReason] = []
    if unclassified_columns:
        reason_codes.append("column_sensitivity_metadata_missing")
    if missing_expected_columns:
        reason_codes.append("missing_expected_columns")
    if missing_required_columns:
        reason_codes.append("missing_required_columns")
    if metadata.row_count == 0 and metadata.row_count < contract.minimum_row_count:
        reason_codes.append("no_rows")
    elif metadata.row_count < contract.minimum_row_count:
        reason_codes.append("under_minimum_rows")
    if (
        contract.expected_row_count is not None
        and (
            metadata.row_count != contract.expected_row_count
            or metadata.result_truncated
        )
    ):
        reason_codes.append("row_count_mismatch")
    if metadata.result_truncated:
        reason_codes.append("result_truncated")
    if null_columns:
        reason_codes.append("null_values_present")
    if outlier_columns:
        reason_codes.append("outlier_values_present")
    if aggregation_shape == "mismatch":
        reason_codes.append("aggregation_shape_mismatch")

    fail_reasons = {
        "column_sensitivity_metadata_missing",
        "missing_expected_columns",
        "missing_required_columns",
        "no_rows",
        "under_minimum_rows",
        "row_count_mismatch",
        "aggregation_shape_mismatch",
    }
    status: ResultValidationStatus
    if any(reason in fail_reasons for reason in reason_codes):
        status = "fail"
    elif reason_codes:
        status = "warn"
    else:
        status = "pass"

    evidence = ResultValidationEvidence(
        expected_columns=expected_columns,
        required_columns=required_columns,
        observed_columns=observed_columns,
        missing_expected_columns=missing_expected_columns,
        missing_required_columns=missing_required_columns,
        row_count=metadata.row_count,
        row_limit=metadata.row_limit,
        result_truncated=metadata.result_truncated,
        aggregation_shape=aggregation_shape,
        null_columns=null_columns,
        outlier_columns=outlier_columns,
        redaction_status=redaction_status,
        redacted_columns=redacted_columns,
        unclassified_columns=unclassified_columns,
    )
    return ResultValidationOutcome(
        status=status,
        reason_codes=tuple(reason_codes),
        semantic_contract_version=metadata.semantic_contract_version,
        candidate_id=metadata.candidate_id,
        execution_run_id=metadata.execution_run_id,
        evidence=evidence,
    )


def redact_execution_result_rows(
    *,
    rows: list[dict[str, Any]],
    contract: ResultValidationContract | None,
) -> list[dict[str, Any]]:
    if contract is None or not contract.redaction_required:
        return rows
    sensitivity = contract.column_sensitivity or {}
    redacted_columns = {
        column
        for column, classification in sensitivity.items()
        if classification == "sensitive"
    }
    if not redacted_columns:
        return rows
    return [
        {
            column: value
            for column, value in row.items()
            if column not in redacted_columns
        }
        for row in rows
    ]


def _unique_ordered(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _observed_columns(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    columns: set[str] = set()
    for row in rows:
        columns.update(str(column) for column in row)
    return tuple(sorted(columns))


def _redaction_evidence(
    *,
    observed_columns: tuple[str, ...],
    contract: ResultValidationContract,
) -> tuple[ResultRedactionStatus, tuple[str, ...], tuple[str, ...]]:
    if not contract.redaction_required:
        return "not_required", (), ()

    sensitivity = contract.column_sensitivity
    if sensitivity is None:
        return "fail", (), observed_columns

    unclassified_columns = tuple(
        column for column in observed_columns if column not in sensitivity
    )
    redacted_columns = tuple(
        column
        for column in observed_columns
        if sensitivity.get(column) == "sensitive"
    )
    if unclassified_columns:
        return "fail", redacted_columns, unclassified_columns
    return "applied", redacted_columns, ()


def _contract_observed_columns_after_redaction(
    *,
    observed_columns: tuple[str, ...],
    contract: ResultValidationContract,
) -> tuple[str, ...]:
    if not contract.redaction_required or contract.column_sensitivity is None:
        return observed_columns
    return tuple(
        column
        for column in observed_columns
        if contract.column_sensitivity.get(column) != "sensitive"
    )


def _columns_with_nulls(
    *,
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        column
        for column in _unique_ordered(columns)
        if any(row.get(column) is None for row in rows if column in row)
    )


def _columns_with_outliers(
    *,
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    minimum: float | None,
    maximum: float | None,
) -> tuple[str, ...]:
    if minimum is None and maximum is None:
        return ()

    decimal_minimum = _decimal_for_outlier_value(minimum)
    decimal_maximum = _decimal_for_outlier_value(maximum)
    outlier_columns: list[str] = []
    for column in _unique_ordered(columns):
        for row in rows:
            value = _decimal_for_outlier_value(row.get(column))
            if value is None:
                continue
            if (decimal_minimum is not None and value < decimal_minimum) or (
                decimal_maximum is not None and value > decimal_maximum
            ):
                outlier_columns.append(column)
                break
    return tuple(outlier_columns)


def _decimal_for_outlier_value(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (Decimal, float, int)):
        return None
    try:
        candidate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not candidate.is_finite():
        return None
    return candidate


def _aggregation_shape(
    *,
    rows: list[dict[str, Any]],
    expected_columns: tuple[str, ...],
    observed_columns: tuple[str, ...],
    aggregate_columns: tuple[str, ...],
) -> Literal["not_applicable", "valid", "mismatch"]:
    aggregate_column_set = set(aggregate_columns)
    if not aggregate_column_set:
        return "not_applicable"
    if not aggregate_column_set.issubset(set(observed_columns)):
        return "mismatch"

    grouping_columns = tuple(
        column for column in expected_columns if column not in aggregate_column_set
    )
    if not grouping_columns:
        return "mismatch" if len(rows) > 1 else "valid"

    seen_keys: set[tuple[object, ...]] = set()
    for row in rows:
        key = tuple(row.get(column) for column in grouping_columns)
        if key in seen_keys:
            return "mismatch"
        seen_keys.add(key)
    return "valid"
