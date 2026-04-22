from app.features.guard.sql_guard import (
    SQLGuardEvaluationInput,
    evaluate_mssql_sql_guard,
)


def test_mssql_sql_guard_allows_source_bound_select_query() -> None:
    evaluation = evaluate_mssql_sql_guard(
        SQLGuardEvaluationInput(
            canonical_sql="SELECT TOP 10 vendor_name FROM dbo.approved_vendor_spend",
            source={
                "source_id": "business-mssql-source",
                "source_family": "mssql",
                "source_flavor": "sqlserver",
            },
        )
    )

    assert evaluation.model_dump() == {
        "decision": "allow",
        "profile": "mssql",
        "canonical_sql": "SELECT TOP 10 vendor_name FROM dbo.approved_vendor_spend",
        "source": {
            "source_id": "business-mssql-source",
            "source_family": "mssql",
            "source_flavor": "sqlserver",
        },
        "rejections": [],
    }


def test_mssql_sql_guard_rejects_multi_statement_input_fail_closed() -> None:
    evaluation = evaluate_mssql_sql_guard(
        {
            "canonical_sql": (
                "SELECT vendor_name FROM dbo.approved_vendor_spend; SELECT @@VERSION"
            ),
            "source": {
                "source_id": "business-mssql-source",
                "source_family": "mssql",
                "source_flavor": "sqlserver",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "mssql",
        "canonical_sql": "SELECT vendor_name FROM dbo.approved_vendor_spend; SELECT @@VERSION",
        "source": {
            "source_id": "business-mssql-source",
            "source_family": "mssql",
            "source_flavor": "sqlserver",
        },
        "rejections": [
            {
                "code": "DENY_MULTI_STATEMENT",
                "detail": "Canonical SQL must contain exactly one SELECT statement.",
                "path": "canonical_sql",
            }
        ],
    }


def test_mssql_sql_guard_rejects_go_batch_separator_fail_closed() -> None:
    evaluation = evaluate_mssql_sql_guard(
        {
            "canonical_sql": (
                "SELECT vendor_name FROM dbo.approved_vendor_spend\n"
                "GO\n"
                "SELECT @@VERSION"
            ),
            "source": {
                "source_id": "business-mssql-source",
                "source_family": "mssql",
                "source_flavor": "sqlserver",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "mssql",
        "canonical_sql": (
            "SELECT vendor_name FROM dbo.approved_vendor_spend\n"
            "GO\n"
            "SELECT @@VERSION"
        ),
        "source": {
            "source_id": "business-mssql-source",
            "source_family": "mssql",
            "source_flavor": "sqlserver",
        },
        "rejections": [
            {
                "code": "DENY_MULTI_STATEMENT",
                "detail": "Canonical SQL must contain exactly one SELECT statement.",
                "path": "canonical_sql",
            }
        ],
    }


def test_mssql_sql_guard_rejects_non_mssql_source_binding_fail_closed() -> None:
    evaluation = evaluate_mssql_sql_guard(
        {
            "canonical_sql": "SELECT vendor_name FROM dbo.approved_vendor_spend",
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "mssql",
        "canonical_sql": None,
        "source": None,
        "rejections": [
            {
                "code": "invalid_contract",
                "detail": "Input should be 'mssql'",
                "path": "source.source_family",
            }
        ],
    }


def test_mssql_sql_guard_rejects_waitfor_delay_fail_closed() -> None:
    evaluation = evaluate_mssql_sql_guard(
        {
            "canonical_sql": (
                "SELECT vendor_name FROM dbo.approved_vendor_spend "
                "WAITFOR DELAY '00:00:05'"
            ),
            "source": {
                "source_id": "business-mssql-source",
                "source_family": "mssql",
                "source_flavor": "sqlserver",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "mssql",
        "canonical_sql": (
            "SELECT vendor_name FROM dbo.approved_vendor_spend "
            "WAITFOR DELAY '00:00:05'"
        ),
        "source": {
            "source_id": "business-mssql-source",
            "source_family": "mssql",
            "source_flavor": "sqlserver",
        },
        "rejections": [
            {
                "code": "DENY_RESOURCE_ABUSE",
                "detail": "WAITFOR is not allowed in the MSSQL guard profile.",
                "path": "canonical_sql",
            }
        ],
    }
