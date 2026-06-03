from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.features.result_validation import (
    ResultValidationContract,
    ResultValidationError,
    ResultValidationMetadata,
    validate_execution_result,
)


def _metadata(*, row_count: int = 1, result_truncated: bool = False) -> ResultValidationMetadata:
    return ResultValidationMetadata(
        semantic_contract_version="approved_vendor_spend.v1",
        candidate_id="candidate-123",
        execution_run_id=uuid4(),
        row_count=row_count,
        row_limit=200,
        result_truncated=result_truncated,
    )


def test_result_validation_passes_with_required_columns_and_aggregate_shape() -> None:
    validation = validate_execution_result(
        rows=[
            {
                "vendor_name": "Acme",
                "fiscal_quarter": "FY26-Q1",
                "approved_spend": 1200,
            }
        ],
        metadata=_metadata(),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "fiscal_quarter", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            aggregate_columns=("approved_spend",),
        ),
    )

    assert validation.status == "pass"
    assert validation.reason_codes == ()
    assert validation.evidence.expected_columns == (
        "vendor_name",
        "fiscal_quarter",
        "approved_spend",
    )
    assert validation.evidence.observed_columns == (
        "approved_spend",
        "fiscal_quarter",
        "vendor_name",
    )
    assert validation.evidence.row_count == 1
    assert validation.evidence.result_truncated is False
    assert validation.semantic_contract_version == "approved_vendor_spend.v1"
    assert validation.candidate_id == "candidate-123"


def test_result_validation_warns_on_truncation_nulls_and_outliers() -> None:
    validation = validate_execution_result(
        rows=[
            {"vendor_name": "Acme", "approved_spend": None},
            {"vendor_name": "Beta", "approved_spend": 9_999_999},
        ],
        metadata=_metadata(row_count=2, result_truncated=True),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            warn_on_null_columns=("approved_spend",),
            outlier_columns=("approved_spend",),
            outlier_numeric_max=1_000_000,
        ),
    )

    assert validation.status == "warn"
    assert validation.reason_codes == (
        "result_truncated",
        "null_values_present",
        "outlier_values_present",
    )
    assert validation.evidence.null_columns == ("approved_spend",)
    assert validation.evidence.outlier_columns == ("approved_spend",)


def test_result_validation_warns_on_decimal_outliers() -> None:
    validation = validate_execution_result(
        rows=[
            {"vendor_name": "Acme", "approved_spend": Decimal("100.00")},
            {"vendor_name": "Beta", "approved_spend": Decimal("1000000.01")},
        ],
        metadata=_metadata(row_count=2),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            outlier_columns=("approved_spend",),
            outlier_numeric_max=1_000_000,
        ),
    )

    assert validation.status == "warn"
    assert validation.reason_codes == ("outlier_values_present",)
    assert validation.evidence.outlier_columns == ("approved_spend",)


def test_result_validation_preserves_expected_columns_for_allowed_empty_results() -> None:
    validation = validate_execution_result(
        rows=[],
        metadata=_metadata(row_count=0),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name",),
            minimum_row_count=0,
        ),
    )

    assert validation.status == "pass"
    assert validation.reason_codes == ()
    assert validation.evidence.observed_columns == ("vendor_name", "approved_spend")


@pytest.mark.parametrize(
    ("rows", "contract", "reason_code"),
    [
        (
            [{"vendor_name": "Acme"}],
            ResultValidationContract(
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
            ),
            "missing_required_columns",
        ),
        (
            [],
            ResultValidationContract(
                expected_columns=("vendor_name",),
                required_columns=("vendor_name",),
                minimum_row_count=1,
            ),
            "no_rows",
        ),
        (
            [
                {"fiscal_quarter": "FY26-Q1", "vendor_name": "Acme"},
                {"fiscal_quarter": "FY26-Q1", "vendor_name": "Beta"},
            ],
            ResultValidationContract(
                expected_columns=("fiscal_quarter", "vendor_name"),
                required_columns=("fiscal_quarter", "vendor_name"),
                aggregate_columns=("vendor_name",),
            ),
            "aggregation_shape_mismatch",
        ),
    ],
)
def test_result_validation_fails_machine_readably(
    rows: list[dict[str, object]],
    contract: ResultValidationContract,
    reason_code: str,
) -> None:
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=len(rows)),
        contract=contract,
    )

    assert validation.status == "fail"
    assert reason_code in validation.reason_codes
    with pytest.raises(ResultValidationError, match=reason_code):
        validation.require_answer_generation_allowed()
