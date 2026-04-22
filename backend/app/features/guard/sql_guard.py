from __future__ import annotations

import re
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from typing_extensions import Annotated


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SQLGuardSourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None


class SQLGuardEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: NonEmptyTrimmedString
    source: SQLGuardSourceBinding


class SQLGuardRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: NonEmptyTrimmedString
    detail: NonEmptyTrimmedString
    path: NonEmptyTrimmedString


class SQLGuardEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "reject"]
    profile: Literal["common", "mssql", "postgresql"]
    canonical_sql: Optional[str]
    source: Optional[SQLGuardSourceBinding]
    rejections: list[SQLGuardRejection]


class MSSQLGuardSourceBinding(SQLGuardSourceBinding):
    source_family: Literal["mssql"]


class MSSQLGuardEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: NonEmptyTrimmedString
    source: MSSQLGuardSourceBinding


class PostgreSQLGuardSourceBinding(SQLGuardSourceBinding):
    source_family: Literal["postgresql"]


class PostgreSQLGuardEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_sql: NonEmptyTrimmedString
    source: PostgreSQLGuardSourceBinding


class MSSQLGuardRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: NonEmptyTrimmedString
    detail: NonEmptyTrimmedString
    pattern: str


_MSSQL_DENY_RULES: tuple[MSSQLGuardRule, ...] = (
    MSSQLGuardRule(
        code="DENY_RESOURCE_ABUSE",
        detail="WAITFOR is not allowed in the MSSQL guard profile.",
        pattern=r"\bWAITFOR\b",
    ),
    MSSQLGuardRule(
        code="DENY_EXTERNAL_DATA_ACCESS",
        detail="External data access is not allowed in the MSSQL guard profile.",
        pattern=r"\bOPENQUERY\b|\bOPENROWSET\b|\bOPENDATASOURCE\b",
    ),
    MSSQLGuardRule(
        code="DENY_LINKED_SERVER",
        detail="Linked-server references are not allowed in the MSSQL guard profile.",
        pattern=r"\[[^\]]+\]\.\[[^\]]+\]\.\[[^\]]+\]\.\[[^\]]+\]",
    ),
    MSSQLGuardRule(
        code="DENY_DYNAMIC_SQL",
        detail="Dynamic SQL execution is not allowed in the MSSQL guard profile.",
        pattern=r"\bsp_executesql\b|\bEXEC(?:UTE)?\s*\(",
    ),
    MSSQLGuardRule(
        code="DENY_PROCEDURE_EXECUTION",
        detail="Stored procedure execution is not allowed in the MSSQL guard profile.",
        pattern=r"^\s*EXEC(?:UTE)?\b",
    ),
    MSSQLGuardRule(
        code="DENY_WRITE_OPERATION",
        detail="Write operations are not allowed in the MSSQL guard profile.",
        pattern=(
            r"\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bMERGE\b|\bTRUNCATE\b|"
            r"\bCREATE\b|\bALTER\b|\bDROP\b"
        ),
    ),
    MSSQLGuardRule(
        code="DENY_TEMP_OBJECT",
        detail="Temporary object creation or mutation is not allowed in the MSSQL guard profile.",
        pattern=r"#\w+|\bINTO\s+#\w+",
    ),
    MSSQLGuardRule(
        code="DENY_DISALLOWED_HINT",
        detail="Query hints are not allowed in the MSSQL guard profile.",
        pattern=r"\bOPTION\s*\(",
    ),
)

_MSSQL_QUERY_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_MSSQL_CROSS_DATABASE = re.compile(
    r"(?:\[[^\]]+\]|\w+)\.(?:\[[^\]]+\]|\w+)\.(?:\[[^\]]+\]|\w+)",
    re.IGNORECASE,
)
_MSSQL_MULTI_STATEMENT_SEPARATOR = re.compile(
    r";\s*\S|^\s*GO\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_POSTGRESQL_DENY_RULES: tuple[MSSQLGuardRule, ...] = (
    MSSQLGuardRule(
        code="DENY_WRITE_OPERATION",
        detail="Write operations are not allowed in the PostgreSQL guard profile.",
        pattern=(
            r"\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bMERGE\b|\bTRUNCATE\b|"
            r"\bCREATE\b|\bALTER\b|\bDROP\b|\bREINDEX\b|\bVACUUM\b|\bANALYZE\b"
        ),
    ),
    MSSQLGuardRule(
        code="DENY_PROCEDURE_EXECUTION",
        detail="Stored procedure execution is not allowed in the PostgreSQL guard profile.",
        pattern=r"^\s*CALL\b|\bDO\s+\$\$",
    ),
    MSSQLGuardRule(
        code="DENY_DYNAMIC_SQL",
        detail="Dynamic SQL execution is not allowed in the PostgreSQL guard profile.",
        pattern=r"\bEXECUTE\b",
    ),
    MSSQLGuardRule(
        code="DENY_EXTERNAL_DATA_ACCESS",
        detail="External data access is not allowed in the PostgreSQL guard profile.",
        pattern=r"\bCOPY\s+.+\b(?:FROM|TO)\b|\bdblink\s*\(|\bpostgres_fdw\b|\bfile_fdw\b",
    ),
    MSSQLGuardRule(
        code="DENY_DISALLOWED_HINT",
        detail="Query hints are not allowed in the PostgreSQL guard profile.",
        pattern=r"/\*\+",
    ),
)

_POSTGRESQL_QUERY_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_POSTGRESQL_MULTI_STATEMENT_SEPARATOR = re.compile(r";\s*\S", re.IGNORECASE)
_POSTGRESQL_IDENTIFIER = r"(?:\"(?:[^\"]|\"\")+\"|[A-Za-z_][\w$]*)"
_POSTGRESQL_FROM_CLAUSE = re.compile(
    r"\bFROM\b(?P<body>.*?)(?=\bWHERE\b|\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b|"
    r"\bLIMIT\b|\bOFFSET\b|\bFETCH\b|\bFOR\b|\bUNION\b|\bINTERSECT\b|\bEXCEPT\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_POSTGRESQL_RELATION_REFERENCE = re.compile(
    rf"^\s*(?:ONLY\s+)?(?:LATERAL\s+)?(?P<relation>"
    rf"{_POSTGRESQL_IDENTIFIER}(?:\s*\.\s*{_POSTGRESQL_IDENTIFIER}){{0,2}}"
    rf")",
    re.IGNORECASE,
)
_POSTGRESQL_JOIN_RELATION = re.compile(
    rf"\bJOIN\s+(?:ONLY\s+)?(?:LATERAL\s+)?(?P<relation>"
    rf"{_POSTGRESQL_IDENTIFIER}(?:\s*\.\s*{_POSTGRESQL_IDENTIFIER}){{0,2}}"
    rf")",
    re.IGNORECASE,
)
_POSTGRESQL_SYSTEM_NAMESPACE_ACCESS = re.compile(
    rf"\b(?:pg_catalog|information_schema)\b\s*\.\s*{_POSTGRESQL_IDENTIFIER}",
    re.IGNORECASE,
)
_POSTGRESQL_SYSTEM_FUNCTION_CALL = re.compile(
    r"\b(?:pg_catalog\s*\.\s*)?pg_[A-Za-z_][\w$]*\s*\(",
    re.IGNORECASE,
)
_POSTGRESQL_CROSS_DATABASE_RELATION = re.compile(
    rf"^{_POSTGRESQL_IDENTIFIER}\s*\.\s*"
    rf"{_POSTGRESQL_IDENTIFIER}\s*\.\s*"
    rf"{_POSTGRESQL_IDENTIFIER}$",
    re.IGNORECASE,
)


def _split_sql_top_level_commas(fragment: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(fragment):
        char = fragment[index]
        if quote == "'":
            if char == "'" and index + 1 < len(fragment) and fragment[index + 1] == "'":
                index += 2
                continue
            if char == "'":
                quote = None
        elif quote == '"':
            if char == '"' and index + 1 < len(fragment) and fragment[index + 1] == '"':
                index += 2
                continue
            if char == '"':
                quote = None
        else:
            if char == "'":
                quote = "'"
            elif char == '"':
                quote = '"'
            elif char == "(":
                depth += 1
            elif char == ")" and depth > 0:
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(fragment[start:index])
                start = index + 1
        index += 1

    parts.append(fragment[start:])
    return parts


def _iter_postgresql_relation_references(canonical_sql: str):
    for from_match in _POSTGRESQL_FROM_CLAUSE.finditer(canonical_sql):
        for item in _split_sql_top_level_commas(from_match.group("body")):
            relation_match = _POSTGRESQL_RELATION_REFERENCE.match(item)
            if relation_match:
                yield relation_match.group("relation")

    for join_match in _POSTGRESQL_JOIN_RELATION.finditer(canonical_sql):
        yield join_match.group("relation")


def _reject_sql_guard(
    *,
    profile: Literal["common", "mssql"],
    canonical_sql: Optional[str],
    source: Optional[SQLGuardSourceBinding],
    code: str,
    detail: str,
    path: str = "canonical_sql",
) -> SQLGuardEvaluation:
    return SQLGuardEvaluation(
        decision="reject",
        profile=profile,
        canonical_sql=canonical_sql,
        source=source,
        rejections=[
            SQLGuardRejection(
                code=code,
                detail=detail,
                path=path,
            )
        ],
    )


def _contract_rejections(exc: ValidationError) -> list[SQLGuardRejection]:
    return [
        SQLGuardRejection(
            code="invalid_contract",
            detail=error["msg"],
            path=".".join(str(segment) for segment in error["loc"]),
        )
        for error in exc.errors()
    ]


def evaluate_common_sql_guard(
    payload: Union[SQLGuardEvaluationInput, dict[str, Any]],
) -> SQLGuardEvaluation:
    try:
        request = (
            payload
            if isinstance(payload, SQLGuardEvaluationInput)
            else SQLGuardEvaluationInput.model_validate(payload)
        )
    except ValidationError as exc:
        return SQLGuardEvaluation(
            decision="reject",
            profile="common",
            canonical_sql=None,
            source=None,
            rejections=_contract_rejections(exc),
        )

    return SQLGuardEvaluation(
        decision="allow",
        profile="common",
        canonical_sql=request.canonical_sql,
        source=request.source,
        rejections=[],
    )


def evaluate_mssql_sql_guard(
    payload: Union[MSSQLGuardEvaluationInput, SQLGuardEvaluationInput, dict[str, Any]],
) -> SQLGuardEvaluation:
    try:
        request = (
            payload
            if isinstance(payload, MSSQLGuardEvaluationInput)
            else MSSQLGuardEvaluationInput.model_validate(
                payload.model_dump()
                if isinstance(payload, SQLGuardEvaluationInput)
                else payload
            )
        )
    except ValidationError as exc:
        return SQLGuardEvaluation(
            decision="reject",
            profile="mssql",
            canonical_sql=None,
            source=None,
            rejections=_contract_rejections(exc),
        )

    canonical_sql = request.canonical_sql
    if _MSSQL_MULTI_STATEMENT_SEPARATOR.search(canonical_sql):
        return _reject_sql_guard(
            profile="mssql",
            canonical_sql=canonical_sql,
            source=request.source,
            code="DENY_MULTI_STATEMENT",
            detail="Canonical SQL must contain exactly one SELECT statement.",
        )

    for rule in _MSSQL_DENY_RULES:
        if re.search(rule.pattern, canonical_sql, re.IGNORECASE):
            return _reject_sql_guard(
                profile="mssql",
                canonical_sql=canonical_sql,
                source=request.source,
                code=rule.code,
                detail=rule.detail,
            )

    if _MSSQL_CROSS_DATABASE.search(canonical_sql):
        return _reject_sql_guard(
            profile="mssql",
            canonical_sql=canonical_sql,
            source=request.source,
            code="DENY_CROSS_DATABASE",
            detail="Cross-database references are not allowed in the MSSQL guard profile.",
        )

    if not _MSSQL_QUERY_START.search(canonical_sql):
        return _reject_sql_guard(
            profile="mssql",
            canonical_sql=canonical_sql,
            source=request.source,
            code="DENY_UNSUPPORTED_SQL_SYNTAX",
            detail="Canonical SQL must start with a supported SELECT query shape.",
        )

    return SQLGuardEvaluation(
        decision="allow",
        profile="mssql",
        canonical_sql=canonical_sql,
        source=request.source,
        rejections=[],
    )


def evaluate_postgresql_sql_guard(
    payload: Union[
        PostgreSQLGuardEvaluationInput,
        SQLGuardEvaluationInput,
        dict[str, Any],
    ],
) -> SQLGuardEvaluation:
    try:
        request = (
            payload
            if isinstance(payload, PostgreSQLGuardEvaluationInput)
            else PostgreSQLGuardEvaluationInput.model_validate(
                payload.model_dump()
                if isinstance(payload, SQLGuardEvaluationInput)
                else payload
            )
        )
    except ValidationError as exc:
        return SQLGuardEvaluation(
            decision="reject",
            profile="postgresql",
            canonical_sql=None,
            source=None,
            rejections=_contract_rejections(exc),
        )

    canonical_sql = request.canonical_sql
    if _POSTGRESQL_MULTI_STATEMENT_SEPARATOR.search(canonical_sql):
        return _reject_sql_guard(
            profile="postgresql",
            canonical_sql=canonical_sql,
            source=request.source,
            code="DENY_MULTI_STATEMENT",
            detail="Canonical SQL must contain exactly one SELECT statement.",
        )

    for rule in _POSTGRESQL_DENY_RULES:
        if re.search(rule.pattern, canonical_sql, re.IGNORECASE | re.DOTALL):
            return _reject_sql_guard(
                profile="postgresql",
                canonical_sql=canonical_sql,
                source=request.source,
                code=rule.code,
                detail=rule.detail,
            )

    if _POSTGRESQL_SYSTEM_NAMESPACE_ACCESS.search(canonical_sql) or _POSTGRESQL_SYSTEM_FUNCTION_CALL.search(
        canonical_sql
    ):
        return _reject_sql_guard(
            profile="postgresql",
            canonical_sql=canonical_sql,
            source=request.source,
            code="DENY_SYSTEM_CATALOG_ACCESS",
            detail="System catalog access is not allowed in the PostgreSQL guard profile.",
        )

    if any(
        _POSTGRESQL_CROSS_DATABASE_RELATION.search(relation)
        for relation in _iter_postgresql_relation_references(canonical_sql)
    ):
        return _reject_sql_guard(
            profile="postgresql",
            canonical_sql=canonical_sql,
            source=request.source,
            code="DENY_CROSS_DATABASE",
            detail="Cross-database references are not allowed in the PostgreSQL guard profile.",
        )

    if not _POSTGRESQL_QUERY_START.search(canonical_sql):
        return _reject_sql_guard(
            profile="postgresql",
            canonical_sql=canonical_sql,
            source=request.source,
            code="DENY_UNSUPPORTED_SQL_SYNTAX",
            detail="Canonical SQL must start with a supported SELECT query shape.",
        )

    return SQLGuardEvaluation(
        decision="allow",
        profile="postgresql",
        canonical_sql=canonical_sql,
        source=request.source,
        rejections=[],
    )
