from __future__ import annotations

from typing import Any, Callable

import pytest

from app.features.guard.sql_guard import (
    SQLGuardEvaluation,
    evaluate_mssql_sql_guard,
    evaluate_postgresql_sql_guard,
)


GuardEvaluator = Callable[[dict[str, object]], SQLGuardEvaluation]


MSSQL_SOURCE = {
    "source_id": "business-mssql-source",
    "source_family": "mssql",
    "source_flavor": "sqlserver",
}

POSTGRESQL_SOURCE = {
    "source_id": "business-postgres-source",
    "source_family": "postgresql",
    "source_flavor": "warehouse",
}

COMMON_DENY_CORPUS = (
    {
        "id": "missing-source-binding",
        "payload": {
            "canonical_sql": "SELECT vendor_name FROM finance.approved_vendor_spend",
        },
        "expected": {
            "canonical_sql": None,
            "source": None,
            "rejections": [
                {
                    "code": "invalid_contract",
                    "detail": "Field required",
                    "path": "source",
                }
            ],
        },
    },
    {
        "id": "partial-source-binding",
        "payload": {
            "canonical_sql": "SELECT vendor_name FROM finance.approved_vendor_spend",
            "source": {
                "source_id": "source-without-family",
            },
        },
        "expected": {
            "canonical_sql": None,
            "source": None,
            "rejections": [
                {
                    "code": "invalid_contract",
                    "detail": "Field required",
                    "path": "source.source_family",
                }
            ],
        },
    },
    {
        "id": "unsupported-syntax",
        "payload_by_family": {
            "mssql": {
                "canonical_sql": "SHOW TABLES",
                "source": MSSQL_SOURCE,
            },
            "postgresql": {
                "canonical_sql": "SHOW TABLES",
                "source": POSTGRESQL_SOURCE,
            },
        },
        "expected": {
            "rejections": [
                {
                    "code": "DENY_UNSUPPORTED_SQL_SYNTAX",
                    "detail": (
                        "Canonical SQL must start with a supported SELECT query shape."
                    ),
                    "path": "canonical_sql",
                }
            ],
        },
    },
    {
        "id": "multi-statement-select",
        "payload_by_family": {
            "mssql": {
                "canonical_sql": (
                    "SELECT vendor_name FROM dbo.approved_vendor_spend; "
                    "SELECT @@VERSION"
                ),
                "source": MSSQL_SOURCE,
            },
            "postgresql": {
                "canonical_sql": (
                    "SELECT vendor_name FROM finance.approved_vendor_spend; "
                    "SELECT current_database()"
                ),
                "source": POSTGRESQL_SOURCE,
            },
        },
        "expected": {
            "rejections": [
                {
                    "code": "DENY_MULTI_STATEMENT",
                    "detail": "Canonical SQL must contain exactly one SELECT statement.",
                    "path": "canonical_sql",
                }
            ],
        },
    },
)

MSSQL_DENY_CORPUS = (
    {
        "id": "waitfor-delay",
        "canonical_sql": (
            "SELECT vendor_name FROM dbo.approved_vendor_spend "
            "WAITFOR DELAY '00:00:05'"
        ),
        "code": "DENY_RESOURCE_ABUSE",
        "detail": "WAITFOR is not allowed in the MSSQL guard profile.",
    },
    {
        "id": "external-data-access",
        "canonical_sql": "SELECT * FROM OPENQUERY(remote, 'SELECT vendor_name FROM dbo.vendors')",
        "code": "DENY_EXTERNAL_DATA_ACCESS",
        "detail": "External data access is not allowed in the MSSQL guard profile.",
    },
    {
        "id": "linked-server-reference",
        "canonical_sql": "SELECT vendor_name FROM [remote].[sales].[dbo].[vendors]",
        "code": "DENY_LINKED_SERVER",
        "detail": "Linked-server references are not allowed in the MSSQL guard profile.",
    },
    {
        "id": "dynamic-sql",
        "canonical_sql": (
            "SELECT vendor_name FROM dbo.approved_vendor_spend "
            "WHERE vendor_name IN (SELECT value FROM sp_executesql(@sql))"
        ),
        "code": "DENY_DYNAMIC_SQL",
        "detail": "Dynamic SQL execution is not allowed in the MSSQL guard profile.",
    },
    {
        "id": "stored-procedure-execution",
        "canonical_sql": "EXEC dbo.usp_vendor_report",
        "code": "DENY_PROCEDURE_EXECUTION",
        "detail": "Stored procedure execution is not allowed in the MSSQL guard profile.",
    },
    {
        "id": "write-operation",
        "canonical_sql": (
            "WITH mutated AS (DELETE FROM dbo.approved_vendor_spend OUTPUT deleted.vendor_name) "
            "SELECT vendor_name FROM mutated"
        ),
        "code": "DENY_WRITE_OPERATION",
        "detail": "Write operations are not allowed in the MSSQL guard profile.",
    },
    {
        "id": "temp-object",
        "canonical_sql": "SELECT vendor_name INTO #vendor_snapshot FROM dbo.approved_vendor_spend",
        "code": "DENY_TEMP_OBJECT",
        "detail": "Temporary object creation or mutation is not allowed in the MSSQL guard profile.",
    },
    {
        "id": "query-hint",
        "canonical_sql": (
            "SELECT vendor_name FROM dbo.approved_vendor_spend OPTION (RECOMPILE)"
        ),
        "code": "DENY_DISALLOWED_HINT",
        "detail": "Query hints are not allowed in the MSSQL guard profile.",
    },
    {
        "id": "cross-database-reference",
        "canonical_sql": "SELECT vendor_name FROM reporting.sales.vendors",
        "code": "DENY_CROSS_DATABASE",
        "detail": "Cross-database references are not allowed in the MSSQL guard profile.",
    },
)

POSTGRESQL_DENY_CORPUS = (
    {
        "id": "write-operation",
        "canonical_sql": (
            "WITH archived AS (DELETE FROM finance.approved_vendor_spend "
            "RETURNING vendor_name) SELECT vendor_name FROM archived"
        ),
        "code": "DENY_WRITE_OPERATION",
        "detail": "Write operations are not allowed in the PostgreSQL guard profile.",
    },
    {
        "id": "stored-procedure-execution",
        "canonical_sql": "CALL finance.refresh_vendor_spend()",
        "code": "DENY_PROCEDURE_EXECUTION",
        "detail": "Stored procedure execution is not allowed in the PostgreSQL guard profile.",
    },
    {
        "id": "dynamic-sql",
        "canonical_sql": (
            "SELECT vendor_name FROM finance.approved_vendor_spend "
            "WHERE EXISTS (SELECT 1 FROM EXECUTE('SELECT 1'))"
        ),
        "code": "DENY_DYNAMIC_SQL",
        "detail": "Dynamic SQL execution is not allowed in the PostgreSQL guard profile.",
    },
    {
        "id": "external-data-access",
        "canonical_sql": (
            "SELECT * FROM dblink('service=warehouse', 'SELECT vendor_name FROM finance.approved_vendor_spend') "
            "AS vendors(vendor_name text)"
        ),
        "code": "DENY_EXTERNAL_DATA_ACCESS",
        "detail": "External data access is not allowed in the PostgreSQL guard profile.",
    },
    {
        "id": "query-hint",
        "canonical_sql": "SELECT /*+ Parallel(4) */ vendor_name FROM finance.approved_vendor_spend",
        "code": "DENY_DISALLOWED_HINT",
        "detail": "Query hints are not allowed in the PostgreSQL guard profile.",
    },
    {
        "id": "system-catalog-relation",
        "canonical_sql": "SELECT schemaname FROM pg_catalog.pg_tables",
        "code": "DENY_SYSTEM_CATALOG_ACCESS",
        "detail": "System catalog access is not allowed in the PostgreSQL guard profile.",
    },
    {
        "id": "system-function",
        "canonical_sql": (
            "SELECT pg_relation_size('finance.approved_vendor_spend') "
            "FROM finance.approved_vendor_spend"
        ),
        "code": "DENY_SYSTEM_CATALOG_ACCESS",
        "detail": "System catalog access is not allowed in the PostgreSQL guard profile.",
    },
    {
        "id": "cross-database-relation",
        "canonical_sql": "SELECT vendor_name FROM business.finance.approved_vendor_spend",
        "code": "DENY_CROSS_DATABASE",
        "detail": "Cross-database references are not allowed in the PostgreSQL guard profile.",
    },
)
@pytest.mark.parametrize(
    ("family", "profile", "evaluator", "source"),
    (
        ("mssql", "mssql", evaluate_mssql_sql_guard, MSSQL_SOURCE),
        ("postgresql", "postgresql", evaluate_postgresql_sql_guard, POSTGRESQL_SOURCE),
    ),
)
@pytest.mark.parametrize(
    "case",
    COMMON_DENY_CORPUS,
    ids=[case["id"] for case in COMMON_DENY_CORPUS],
)
def test_sql_guard_common_deny_corpus(
    family: str,
    profile: str,
    evaluator: GuardEvaluator,
    source: dict[str, str],
    case: dict[str, Any],
) -> None:
    if "payload_by_family" in case:
        payload = case["payload_by_family"][family]
    else:
        payload = case["payload"]

    evaluation = evaluator(payload)

    expected = case["expected"]
    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": profile,
        "canonical_sql": expected.get("canonical_sql", payload.get("canonical_sql")),
        "source": expected.get("source", payload.get("source", source)),
        "rejections": expected["rejections"],
    }


@pytest.mark.parametrize(
    "case",
    MSSQL_DENY_CORPUS,
    ids=[case["id"] for case in MSSQL_DENY_CORPUS],
)
def test_mssql_sql_guard_family_specific_deny_corpus(case: dict[str, str]) -> None:
    evaluation = evaluate_mssql_sql_guard(
        {
            "canonical_sql": case["canonical_sql"],
            "source": MSSQL_SOURCE,
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "mssql",
        "canonical_sql": case["canonical_sql"],
        "source": MSSQL_SOURCE,
        "rejections": [
            {
                "code": case["code"],
                "detail": case["detail"],
                "path": "canonical_sql",
            }
        ],
    }


@pytest.mark.parametrize(
    "case",
    POSTGRESQL_DENY_CORPUS,
    ids=[case["id"] for case in POSTGRESQL_DENY_CORPUS],
)
def test_postgresql_sql_guard_family_specific_deny_corpus(case: dict[str, str]) -> None:
    evaluation = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": case["canonical_sql"],
            "source": POSTGRESQL_SOURCE,
        }
    )

    assert evaluation.model_dump() == {
        "decision": "reject",
        "profile": "postgresql",
        "canonical_sql": case["canonical_sql"],
        "source": POSTGRESQL_SOURCE,
        "rejections": [
            {
                "code": case["code"],
                "detail": case["detail"],
                "path": "canonical_sql",
            }
        ],
    }
