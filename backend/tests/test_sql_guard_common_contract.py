from app.features.guard.sql_guard import (
    SQLGuardEvaluationInput,
    evaluate_common_sql_guard,
)


def test_common_sql_guard_allows_source_bound_canonical_sql() -> None:
    evaluation = evaluate_common_sql_guard(
        SQLGuardEvaluationInput(
            canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend",
            source={
                "source_id": "sap-approved-spend",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        )
    )

    assert evaluation.model_dump() == {
        "decision": "allow",
        "profile": "common",
        "canonical_sql": "SELECT vendor_name FROM finance.approved_vendor_spend",
        "source": {
            "source_id": "sap-approved-spend",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [],
    }


def test_common_sql_guard_rejects_missing_source_binding_fail_closed() -> None:
    evaluation = evaluate_common_sql_guard(
        {
            "canonical_sql": "SELECT vendor_name FROM finance.approved_vendor_spend",
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "common",
        "canonical_sql": None,
        "source": None,
        "rejections": [
            {
                "code": "invalid_contract",
                "detail": "Field required",
                "path": "source",
            }
        ],
    }


def test_common_sql_guard_rejects_partial_source_binding_fail_closed() -> None:
    evaluation = evaluate_common_sql_guard(
        {
            "canonical_sql": "SELECT vendor_name FROM finance.approved_vendor_spend",
            "source": {
                "source_id": "sap-approved-spend",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "common",
        "canonical_sql": None,
        "source": None,
        "rejections": [
            {
                "code": "invalid_contract",
                "detail": "Field required",
                "path": "source.source_family",
            }
        ],
    }
