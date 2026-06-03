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
        "answerState": "answered",
        "answerText": (
            "Approved vendor spend rows from 2 returned rows: "
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


def test_mvp_answer_summary_uses_mssql_approved_amount_spend_column() -> None:
    rows = [
        {"vendor_name": "Acme", "approved_amount": 1200},
        {"vendor_name": "Beta", "approved_amount": 900},
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=2),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_amount"),
            required_columns=("vendor_name", "approved_amount"),
            aggregate_columns=("approved_amount",),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-mssql-source",
        source_family="mssql",
    )

    assert summary.answer_text.startswith(
        "Approved vendor spend rows from 2 returned rows: "
        "1. Acme (unspecified period) - 1200; "
        "2. Beta (unspecified period) - 900."
    )
    assert "unavailable" not in summary.answer_text


def test_mvp_answer_summary_preserves_total_row_count_when_display_is_capped() -> None:
    rows = [
        {"vendor_name": f"Vendor {index}", "approved_spend": index}
        for index in range(1, 7)
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=6),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
            aggregate_columns=("approved_spend",),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert summary.rows_used == 5
    assert (
        "Approved vendor spend rows from 6 returned rows; showing 5 rows:"
        in summary.answer_text
    )
    assert "from 5 returned rows" not in summary.answer_text
    assert "Vendor 5" in summary.answer_text
    assert "Vendor 6" not in summary.answer_text


def test_mvp_answer_summary_uses_neutral_template_for_aggregate_rows() -> None:
    rows = [
        {"region": "East", "vendor_count": 3},
        {"region": "West", "vendor_count": 2},
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=2),
        contract=ResultValidationContract(
            expected_columns=("region", "vendor_count"),
            required_columns=("region", "vendor_count"),
            aggregate_columns=("vendor_count",),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert summary.answer_text.startswith(
        "Returned 2 rows; showing 2 rows: "
        "1. region=East, vendor_count=3; "
        "2. region=West, vendor_count=2."
    )
    assert "Top approved vendor spend" not in summary.answer_text
    assert "unknown vendor" not in summary.answer_text
    assert "unavailable" not in summary.answer_text


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
        "Insufficient evidence: no rows were returned. "
        "Next action: revise the query filters or source selection before requesting an answer."
    )
    assert summary.answer_state == "insufficient_evidence"
    assert summary.insufficient_evidence_reason == "no_rows"
    assert summary.next_action == "revise_query_filters_or_source"
    assert summary.rows_used == 0
    assert summary.validation_status == "fail"
    assert summary.validation_reason_codes == ("missing_expected_columns", "no_rows")


def test_mvp_answer_summary_does_not_claim_vendor_rows_are_top_ranked() -> None:
    rows = [
        {"vendor_name": "Acme", "approved_spend": 900},
        {"vendor_name": "Beta", "approved_spend": 1200},
    ]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=2),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert summary.answer_text.startswith(
        "Approved vendor spend rows from 2 returned rows: "
        "1. Acme (unspecified period) - 900; "
        "2. Beta (unspecified period) - 1200."
    )
    assert "Top approved vendor spend" not in summary.answer_text
    assert "ranking" not in summary.answer_text


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
        truncation_reason="row_limit",
    )

    assert summary.answer_state == "insufficient_evidence"
    assert summary.insufficient_evidence_reason == "unsafe_truncation"
    assert summary.next_action == "rerun_with_trusted_top_n_or_higher_limit"
    assert summary.validation_status == "warn"
    assert summary.validation_reason_codes == (
        "result_truncated",
        "null_values_present",
        "outlier_values_present",
    )
    assert summary.truncation_status == "truncated"
    assert summary.answer_text == (
        "Insufficient evidence: result was truncated before the top set could be trusted. "
        "Next action: rerun with an authoritative ORDER BY, tighter filters, or a higher trusted limit."
    )
    assert "Acme" not in summary.answer_text
    assert "Beta" not in summary.answer_text


def test_mvp_answer_summary_uses_payload_truncation_reason_when_available() -> None:
    rows = [{"vendor_name": "Acme", "approved_spend": 1200}]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1, result_truncated=True),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
        truncation_reason="payload_limit",
    )

    assert summary.answer_state == "insufficient_evidence"
    assert summary.insufficient_evidence_reason == "unsafe_truncation"
    assert summary.next_action == "rerun_with_trusted_top_n_or_higher_limit"
    assert "result was truncated before the top set could be trusted" in summary.answer_text
    assert "Acme" not in summary.answer_text


def test_mvp_answer_summary_uses_neutral_truncation_when_reason_is_unknown() -> None:
    rows = [{"vendor_name": "Acme", "approved_spend": 1200}]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1, result_truncated=True),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert summary.answer_state == "insufficient_evidence"
    assert summary.insufficient_evidence_reason == "unsafe_truncation"
    assert "returned-row limits" not in summary.answer_text
    assert "payload limits" not in summary.answer_text


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


def test_mvp_answer_summary_bounds_large_row_values() -> None:
    long_note = "A" * 400
    rows = [{"vendor_name": long_note, "approved_spend": 1200}]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert long_note not in summary.answer_text
    displayed_vendor = summary.answer_text.split("1. ", maxsplit=1)[1].split(
        " (unspecified period) - ",
        maxsplit=1,
    )[0]
    assert displayed_vendor.endswith("... [truncated]")
    assert len(displayed_vendor) == 160


def test_mvp_answer_summary_bounds_large_numeric_spend_values() -> None:
    long_amount = int("9" * 400)
    rows = [{"vendor_name": "Acme", "approved_spend": long_amount}]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert str(long_amount) not in summary.answer_text
    displayed_amount = summary.answer_text.split(
        " (unspecified period) - ",
        maxsplit=1,
    )[1].split(". Source:", maxsplit=1)[0]
    assert displayed_amount.endswith("... [truncated]")
    assert len(displayed_amount) == 160


def test_mvp_answer_summary_bounds_large_assumptions() -> None:
    long_assumption = "Rows are ordered by " + ("approved spend " * 40)
    rows = [{"vendor_name": "Acme", "approved_spend": 1200}]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1),
        contract=ResultValidationContract(
            expected_columns=("vendor_name", "approved_spend"),
            required_columns=("vendor_name", "approved_spend"),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
        assumptions=(long_assumption,),
    )

    assert long_assumption not in summary.answer_text
    displayed_assumption = summary.assumptions[0]
    assert displayed_assumption.endswith("... [truncated]")
    assert len(displayed_assumption) == 160
    assert f"Assumptions: {displayed_assumption}." in summary.answer_text


def test_mvp_answer_summary_bounds_generic_column_names() -> None:
    long_column = "column_" + ("alias_" * 80)
    rows = [{long_column: "East", "vendor_count": 3}]
    validation = validate_execution_result(
        rows=rows,
        metadata=_metadata(row_count=1),
        contract=ResultValidationContract(
            expected_columns=(long_column, "vendor_count"),
            required_columns=(long_column, "vendor_count"),
            aggregate_columns=("vendor_count",),
        ),
    )

    summary = generate_mvp_answer_summary(
        rows=rows,
        validation=validation,
        source_id="business-postgres-source",
        source_family="postgresql",
    )

    assert long_column not in summary.answer_text
    displayed_column = summary.answer_text.split("1. ", maxsplit=1)[1].split(
        "=East",
        maxsplit=1,
    )[0]
    assert displayed_column.endswith("... [truncated]")
    assert len(displayed_column) == 160
