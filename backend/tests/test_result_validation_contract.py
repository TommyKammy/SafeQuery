from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.features.result_validation import (
    ResultValidationContract,
    ResultValidationError,
    ResultValidationMetadata,
    redact_execution_result_rows,
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


def test_result_validation_reports_applied_redaction_policy() -> None:
    validation = validate_execution_result(
        rows=[
            {
                "vendor_name": "Acme",
                "vendor_email": "buyer@example.test",
                "approved_spend": 1200,
            }
        ],
        metadata=_metadata(),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            redaction_required=True,
            column_sensitivity={
                "vendor_name": "public",
                "vendor_email": "sensitive",
                "approved_spend": "public",
            },
        ),
    )

    assert validation.status == "pass"
    assert validation.evidence.redaction_status == "applied"
    assert validation.evidence.redacted_columns == ("vendor_email",)
    assert validation.evidence.unclassified_columns == ()


def test_result_validation_fails_closed_when_redaction_metadata_is_missing() -> None:
    validation = validate_execution_result(
        rows=[
            {
                "vendor_name": "Acme",
                "vendor_email": "buyer@example.test",
                "approved_spend": 1200,
            }
        ],
        metadata=_metadata(),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            redaction_required=True,
            column_sensitivity={
                "vendor_name": "public",
                "approved_spend": "public",
            },
        ),
    )

    assert validation.status == "fail"
    assert validation.reason_codes == ("column_sensitivity_metadata_missing",)
    assert validation.evidence.redaction_status == "fail"
    assert validation.evidence.redacted_columns == ()
    assert validation.evidence.unclassified_columns == ("vendor_email",)
    with pytest.raises(
        ResultValidationError,
        match="column_sensitivity_metadata_missing",
    ):
        validation.require_answer_generation_allowed()


def test_result_validation_fails_when_redaction_removes_required_columns() -> None:
    validation = validate_execution_result(
        rows=[
            {
                "vendor_name": "Acme",
                "vendor_email": "buyer@example.test",
                "approved_spend": 1200,
            }
        ],
        metadata=_metadata(),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "vendor_email", "approved_spend"),
            required_columns=("vendor_name", "vendor_email", "approved_spend"),
            redaction_required=True,
            column_sensitivity={
                "vendor_name": "public",
                "vendor_email": "sensitive",
                "approved_spend": "public",
            },
        ),
    )

    assert validation.status == "fail"
    assert validation.reason_codes == (
        "missing_expected_columns",
        "missing_required_columns",
    )
    assert validation.evidence.redaction_status == "applied"
    assert validation.evidence.redacted_columns == ("vendor_email",)
    assert validation.evidence.missing_expected_columns == ("vendor_email",)
    assert validation.evidence.missing_required_columns == ("vendor_email",)


def test_result_validation_fails_when_returned_rows_removed_required_sensitive_columns() -> None:
    raw_rows = [
        {
            "vendor_name": "Acme",
            "vendor_email": "buyer@example.test",
            "approved_spend": 1200,
        }
    ]
    contract = ResultValidationContract(
        expected_columns=("vendor_name", "vendor_email", "approved_spend"),
        required_columns=("vendor_name", "vendor_email", "approved_spend"),
        redaction_required=True,
        column_sensitivity={
            "vendor_name": "public",
            "vendor_email": "sensitive",
            "approved_spend": "public",
        },
    )
    returned_rows = redact_execution_result_rows(rows=raw_rows, contract=contract)

    validation = validate_execution_result(
        rows=returned_rows,
        metadata=_metadata(),
        contract=contract,
        redaction_source_rows=raw_rows,
    )

    assert validation.status == "fail"
    assert validation.reason_codes == (
        "missing_expected_columns",
        "missing_required_columns",
    )
    assert validation.evidence.observed_columns == ("approved_spend", "vendor_name")
    assert validation.evidence.redaction_status == "applied"
    assert validation.evidence.redacted_columns == ("vendor_email",)
    assert validation.evidence.unclassified_columns == ()
    assert validation.evidence.missing_expected_columns == ("vendor_email",)
    assert validation.evidence.missing_required_columns == ("vendor_email",)


def test_result_redaction_removes_sensitive_columns_without_mutating_source_rows() -> None:
    rows = [
        {
            "vendor_name": "Acme",
            "vendor_email": "buyer@example.test",
            "approved_spend": 1200,
        }
    ]

    redacted = redact_execution_result_rows(
        rows=rows,
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            redaction_required=True,
            column_sensitivity={
                "vendor_name": "public",
                "vendor_email": "sensitive",
                "approved_spend": "public",
            },
        ),
    )

    assert redacted == [{"vendor_name": "Acme", "approved_spend": 1200}]
    assert rows[0]["vendor_email"] == "buyer@example.test"


def test_result_validation_reports_under_minimum_rows_separately_from_no_rows() -> None:
    validation = validate_execution_result(
        rows=[
            {"vendor_name": "Acme", "approved_spend": 100},
            {"vendor_name": "Beta", "approved_spend": 200},
            {"vendor_name": "Cypher", "approved_spend": 300},
        ],
        metadata=_metadata(row_count=3),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            minimum_row_count=5,
        ),
    )

    assert validation.status == "fail"
    assert "under_minimum_rows" in validation.reason_codes
    assert "no_rows" not in validation.reason_codes
    assert validation.evidence.row_count == 3


def test_result_validation_fails_exact_count_when_result_is_truncated() -> None:
    validation = validate_execution_result(
        rows=[{"row_id": index} for index in range(200)],
        metadata=_metadata(row_count=200, result_truncated=True),
        contract=ResultValidationContract(
            expected_columns=("row_id",),
            required_columns=("row_id",),
            expected_row_count=200,
        ),
    )

    assert validation.status == "fail"
    assert "row_count_mismatch" in validation.reason_codes
    assert "result_truncated" in validation.reason_codes


def test_result_validation_rejects_multi_row_ungrouped_aggregate_shape() -> None:
    validation = validate_execution_result(
        rows=[
            {"approved_spend": 100},
            {"approved_spend": 200},
        ],
        metadata=_metadata(row_count=2),
        contract=ResultValidationContract(
            expected_columns=("approved_spend",),
            required_columns=("approved_spend",),
            aggregate_columns=("approved_spend",),
        ),
    )

    assert validation.status == "fail"
    assert "aggregation_shape_mismatch" in validation.reason_codes
    assert validation.evidence.aggregation_shape == "mismatch"


def test_result_validation_uses_expected_grouping_columns_for_aggregate_shape() -> None:
    validation = validate_execution_result(
        rows=[
            {
                "invoice_id": "invoice-1",
                "vendor_name": "Acme",
                "approved_spend": 100,
            },
            {
                "invoice_id": "invoice-2",
                "vendor_name": "Acme",
                "approved_spend": 200,
            },
        ],
        metadata=_metadata(row_count=2),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            aggregate_columns=("approved_spend",),
        ),
    )

    assert validation.status == "fail"
    assert "aggregation_shape_mismatch" in validation.reason_codes
    assert validation.evidence.aggregation_shape == "mismatch"


def test_result_validation_does_not_assume_expected_columns_for_empty_results() -> None:
    validation = validate_execution_result(
        rows=[],
        metadata=_metadata(row_count=0),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name",),
            minimum_row_count=0,
        ),
    )

    assert validation.status == "fail"
    assert validation.reason_codes == (
        "missing_expected_columns",
        "missing_required_columns",
    )
    assert validation.evidence.observed_columns == ()


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
