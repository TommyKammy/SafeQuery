from __future__ import annotations

from uuid import uuid4

from app.features.mvp_answer_summary import generate_mvp_answer_summary
from app.features.result_validation import (
    ResultValidationContract,
    ResultValidationMetadata,
    validate_execution_result,
)


def _metadata(
    *,
    row_count: int,
    row_limit: int = 200,
    result_truncated: bool = False,
) -> ResultValidationMetadata:
    return ResultValidationMetadata(
        semantic_contract_version="approved_vendor_spend.v1",
        candidate_id="candidate-123",
        execution_run_id=uuid4(),
        row_count=row_count,
        row_limit=row_limit,
        result_truncated=result_truncated,
    )


def test_mvp_answer_summary_uses_only_returned_rows_and_metadata() -> None:
    rows = [
        {"vendor_name": "Acme", "fiscal_quarter": "FY26-Q1", "approved_spend": 1200},
        {"vendor_name": "Beta", "fiscal_quarter": "FY26-Q1", "approved_spend": 900},
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=2),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "fiscal_quarter", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            aggregate_columns=("approved_spend",),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
        assumptions=("Rows are sorted by approved spend descending.",),
        freeform_llm_answer=(
            "Gamma was the fastest-growing vendor and should be prioritized."
        ),
    )

    assert summary.to_wire_payload() == {
        "contractVersion": "mvp_answer_summary.v1",
        "answerText": (
            "Top approved vendor spend from 2 returned rows: "
            "1. Acme (FY26-Q1) - 1200; 2. Beta (FY26-Q1) - 900. "
            "Source: business-postgres-source (postgresql). "
            "Assumptions: Rows are sorted by approved spend descending. "
            "Validation: pass. Truncation: not truncated. "
            "Redaction: not required."
        ),
        "source": {
            "sourceId": "business-postgres-source",
            "sourceFamily": "postgresql",
            "semanticContractVersion": "approved_vendor_spend.v1",
            "candidateId": "candidate-123",
        },
        "assumptions": ["Rows are sorted by approved spend descending."],
        "validationStatus": "pass",
        "validationReasonCodes": [],
        "truncationStatus": "not_truncated",
        "redactionStatus": "not_required",
        "rowsUsed": 2,
    }
    assert "Gamma" not in summary.answer_text
    assert "fastest-growing" not in summary.answer_text


def test_mvp_answer_summary_reports_no_rows_without_claiming_a_ranking() -> None:
    rows: list[dict[str, object]] = []
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=0),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            minimum_row_count=0,
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert summary.answer_text == (
        "No rows were returned, so no vendor spend ranking is available. "
        "Source: business-postgres-source (postgresql). "
        "Assumptions: none. Validation: fail (missing_expected_columns). "
        "Truncation: not truncated. Redaction: not required."
    )
    assert summary.rows_used == 0
    assert summary.validation_status == "fail"
    assert summary.validation_reason_codes == ("missing_expected_columns",)


def test_mvp_answer_summary_surfaces_truncation_and_validation_warnings() -> None:
    rows = [
        {"vendor_name": "Acme", "approved_spend": None},
        {"vendor_name": "Beta", "approved_spend": 9_999_999},
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=2, row_limit=2, result_truncated=True),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            warn_on_null_columns=("approved_spend",),
            outlier_columns=("approved_spend",),
            outlier_numeric_max=1_000_000,
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert summary.validation_status == "warn"
    assert summary.validation_reason_codes == (
        "result_truncated",
        "null_values_present",
        "outlier_values_present",
    )
    assert summary.truncation_status == "truncated"
    assert "Validation: warn (result_truncated, null_values_present, outlier_values_present)." in (
        summary.answer_text
    )
    assert "Truncation: truncated by returned-row limits." in summary.answer_text


def test_mvp_answer_summary_reports_redaction_without_exposing_redacted_inputs() -> None:
    raw_rows = [
        {
            "vendor_name": "Acme",
            "vendor_email": "buyer@example.test",
            "approved_spend": 1200,
        }
    ]
    contract = ResultValidationContract(
        expected_columns=("vendor_name", "approved_spend"),
        required_columns=("vendor_name", "approved_spend"),
        redaction_required=True,
        column_sensitivity={
            "vendor_name": "public",
            "vendor_email": "sensitive",
            "approved_spend": "public",
        },
    )
    rows = [
        {
            column: value
            for column, value in row.items()
            if column != "vendor_email"
        }
        for row in raw_rows
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1),
        contract=contract,
        redaction_source_rows=raw_rows,
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert summary.redaction_status == "applied"
    assert "Redaction: applied." in summary.answer_text
    assert "buyer@example.test" not in summary.answer_text
    assert "vendor_email" not in summary.answer_text


def test_mvp_answer_summary_redacts_secret_and_path_like_row_values() -> None:
    unsafe_home_path = "~" + "/workspace/private"
    rows = [
        {
            "vendor_name": "token=raw-secret-token",
            "fiscal_quarter": unsafe_home_path,
            "approved_spend": 1200,
        }
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "fiscal_quarter", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
        assumptions=("Use credential=hidden value from the run note.",),
    )

    serialized = str(summary.to_wire_payload()).lower()
    assert "raw-secret-token" not in serialized
    assert "hidden value" not in serialized
    assert unsafe_home_path not in serialized
    assert "[redacted]" in serialized
