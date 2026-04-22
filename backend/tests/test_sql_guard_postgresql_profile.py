from app.features.guard.sql_guard import (
    SQLGuardEvaluationInput,
    evaluate_postgresql_sql_guard,
)


def test_postgresql_sql_guard_allows_source_bound_select_query() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        SQLGuardEvaluationInput(
            canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend",
            source={
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        )
    )

    assert evaluation.model_dump() == {
        "decision": "allow",
        "profile": "postgresql",
        "canonical_sql": "SELECT vendor_name FROM finance.approved_vendor_spend",
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [],
    }


def test_postgresql_sql_guard_allows_schema_table_column_projection() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": (
                "SELECT finance.approved_vendor_spend.vendor_name "
                "FROM finance.approved_vendor_spend"
            ),
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "allow",
        "profile": "postgresql",
        "canonical_sql": (
            "SELECT finance.approved_vendor_spend.vendor_name "
            "FROM finance.approved_vendor_spend"
        ),
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [],
    }


def test_postgresql_sql_guard_allows_pg_prefixed_business_columns() -> None:
    source = {
        "source_id": "business-postgres-source",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
    }

    for canonical_sql in (
        "SELECT pg_vendor_name FROM finance.approved_vendor_spend",
        'SELECT "pg_vendor_name" FROM finance.approved_vendor_spend',
    ):
        evaluation = evaluate_postgresql_sql_guard(
            {
                "canonical_sql": canonical_sql,
                "source": source,
            }
        )

        assert evaluation.model_dump() == {
            "decision": "allow",
            "profile": "postgresql",
            "canonical_sql": canonical_sql,
            "source": source,
            "rejections": [],
        }


def test_postgresql_sql_guard_rejects_write_operation_fail_closed() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": (
                "WITH archived AS (DELETE FROM finance.approved_vendor_spend "
                "RETURNING vendor_name) "
                "SELECT vendor_name FROM archived"
            ),
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": (
            "WITH archived AS (DELETE FROM finance.approved_vendor_spend "
            "RETURNING vendor_name) "
            "SELECT vendor_name FROM archived"
        ),
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [
            {
                "code": "DENY_WRITE_OPERATION",
                "detail": "Write operations are not allowed in the PostgreSQL guard profile.",
                "path": "canonical_sql",
            }
        ],
    }


def test_postgresql_sql_guard_rejects_cross_database_relation_fail_closed() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": "SELECT vendor_name FROM business.finance.approved_vendor_spend",
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": "SELECT vendor_name FROM business.finance.approved_vendor_spend",
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [
            {
                "code": "DENY_CROSS_DATABASE",
                "detail": "Cross-database references are not allowed in the PostgreSQL guard profile.",
                "path": "canonical_sql",
            }
        ],
    }


def test_postgresql_sql_guard_rejects_cross_database_relation_in_later_from_item_fail_closed() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": (
                "SELECT 1 FROM finance.approved_vendor_spend, "
                "business.public.other_table"
            ),
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": (
            "SELECT 1 FROM finance.approved_vendor_spend, "
            "business.public.other_table"
        ),
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [
            {
                "code": "DENY_CROSS_DATABASE",
                "detail": "Cross-database references are not allowed in the PostgreSQL guard profile.",
                "path": "canonical_sql",
            }
        ],
    }


def test_postgresql_sql_guard_rejects_multi_statement_input_fail_closed() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": (
                "SELECT vendor_name FROM finance.approved_vendor_spend; "
                "SELECT current_database()"
            ),
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": (
            "SELECT vendor_name FROM finance.approved_vendor_spend; "
            "SELECT current_database()"
        ),
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [
            {
                "code": "DENY_MULTI_STATEMENT",
                "detail": "Canonical SQL must contain exactly one SELECT statement.",
                "path": "canonical_sql",
            }
        ],
    }


def test_postgresql_sql_guard_rejects_system_catalog_access_fail_closed() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": "SELECT schemaname FROM pg_catalog.pg_tables",
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": "SELECT schemaname FROM pg_catalog.pg_tables",
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [
            {
                "code": "DENY_SYSTEM_CATALOG_ACCESS",
                "detail": "System catalog access is not allowed in the PostgreSQL guard profile.",
                "path": "canonical_sql",
            }
        ],
    }


def test_postgresql_sql_guard_rejects_pg_prefixed_system_function_fail_closed() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": (
                "SELECT pg_relation_size('finance.approved_vendor_spend') "
                "FROM finance.approved_vendor_spend"
            ),
            "source": {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": (
            "SELECT pg_relation_size('finance.approved_vendor_spend') "
            "FROM finance.approved_vendor_spend"
        ),
        "source": {
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "rejections": [
            {
                "code": "DENY_SYSTEM_CATALOG_ACCESS",
                "detail": "System catalog access is not allowed in the PostgreSQL guard profile.",
                "path": "canonical_sql",
            }
        ],
    }


def test_postgresql_sql_guard_rejects_non_postgresql_source_binding_fail_closed() -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": "SELECT vendor_name FROM finance.approved_vendor_spend",
            "source": {
                "source_id": "business-mssql-source",
                "source_family": "mssql",
                "source_flavor": "sqlserver",
            },
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": None,
        "source": None,
        "rejections": [
            {
                "code": "invalid_contract",
                "detail": "Input should be 'postgresql'",
                "path": "source.source_family",
            }
        ],
    }
