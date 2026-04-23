from __future__ import annotations

import copy
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, PositiveInt, model_validator


EvaluationScenarioKind = Literal["positive", "safety", "regression"]
EvaluationBoundary = Literal["guard", "connector_selection", "lifecycle", "execution"]


class EvaluationSourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_family: str
    source_flavor: str
    dialect_profile: str
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: PositiveInt


class EvaluationExecutionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    ownership: Literal["backend"]
    row_shape: tuple[str, ...]


class EvaluationExpectedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "reject"]
    primary_code: Optional[str] = None
    canonical_sql: Optional[str] = None
    execution_evidence: Optional[EvaluationExecutionEvidence] = None

    @model_validator(mode="after")
    def _require_machine_readable_reject_code(self) -> "EvaluationExpectedOutcome":
        if self.decision == "reject" and self.primary_code is None:
            raise ValueError("Reject scenarios must include a machine-readable primary code.")
        if self.decision == "allow" and self.primary_code is not None:
            raise ValueError("Allow scenarios must not include a primary deny code.")
        return self


class MSSQLEvaluationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    kind: EvaluationScenarioKind
    evaluation_boundary: EvaluationBoundary
    source: EvaluationSourceProfile
    prompt: str
    canonical_sql: str
    expected: EvaluationExpectedOutcome

    @property
    def identity(self) -> tuple[str, str]:
        return (self.source.source_id, self.scenario_id)


class PostgreSQLEvaluationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    kind: EvaluationScenarioKind
    evaluation_boundary: EvaluationBoundary
    source: EvaluationSourceProfile
    prompt: str
    canonical_sql: str
    expected: EvaluationExpectedOutcome

    @property
    def identity(self) -> tuple[str, str]:
        return (self.source.source_id, self.scenario_id)


_MSSQL_SOURCE = EvaluationSourceProfile(
    source_id="business-mssql-source",
    source_family="mssql",
    source_flavor="sqlserver",
    dialect_profile="mssql.sqlserver.v1",
    dataset_contract_version=3,
    schema_snapshot_version=7,
    execution_policy_version=2,
)

_MSSQL_UNSUPPORTED_SOURCE = EvaluationSourceProfile(
    source_id="business-mssql-legacy-source",
    source_family="mssql",
    source_flavor="legacy-sqlserver",
    dialect_profile="mssql.legacy-sqlserver.v1",
    dataset_contract_version=3,
    schema_snapshot_version=7,
    execution_policy_version=2,
)

_POSTGRESQL_SOURCE = EvaluationSourceProfile(
    source_id="business-postgres-source",
    source_family="postgresql",
    source_flavor="warehouse",
    dialect_profile="postgresql.warehouse.v1",
    dataset_contract_version=4,
    schema_snapshot_version=9,
    execution_policy_version=3,
)

_POSTGRESQL_UNSUPPORTED_SOURCE = EvaluationSourceProfile(
    source_id="business-postgres-legacy-source",
    source_family="postgresql",
    source_flavor="legacy-warehouse",
    dialect_profile="postgresql.legacy-warehouse.v1",
    dataset_contract_version=4,
    schema_snapshot_version=9,
    execution_policy_version=3,
)

_APPLICATION_POSTGRES_SOURCE = EvaluationSourceProfile(
    source_id="application-postgres-persistence",
    source_family="postgresql",
    source_flavor="persistence",
    dialect_profile="postgresql.persistence.v1",
    dataset_contract_version=1,
    schema_snapshot_version=1,
    execution_policy_version=1,
)


MSSQL_EVALUATION_SCENARIOS: tuple[MSSQLEvaluationScenario, ...] = (
    MSSQLEvaluationScenario(
        scenario_id="mssql-positive-approved-vendor-spend-top-vendors",
        kind="positive",
        evaluation_boundary="execution",
        source=_MSSQL_SOURCE,
        prompt="Show the top approved vendor spend records.",
        canonical_sql=(
            "SELECT TOP 10 vendor_name, approved_amount "
            "FROM dbo.approved_vendor_spend "
            "ORDER BY approved_amount DESC"
        ),
        expected=EvaluationExpectedOutcome(
            decision="allow",
            canonical_sql=(
                "SELECT TOP 10 vendor_name, approved_amount "
                "FROM dbo.approved_vendor_spend "
                "ORDER BY approved_amount DESC"
            ),
            execution_evidence={
                "connector_id": "mssql_readonly",
                "ownership": "backend",
                "row_shape": ("vendor_name", "approved_amount"),
            },
        ),
    ),
    MSSQLEvaluationScenario(
        scenario_id="mssql-positive-approved-vendor-count-by-region",
        kind="positive",
        evaluation_boundary="execution",
        source=_MSSQL_SOURCE,
        prompt="Count approved vendors by region.",
        canonical_sql=(
            "SELECT region, COUNT(*) AS vendor_count "
            "FROM dbo.approved_vendor_spend "
            "GROUP BY region "
            "ORDER BY vendor_count DESC"
        ),
        expected=EvaluationExpectedOutcome(
            decision="allow",
            canonical_sql=(
                "SELECT region, COUNT(*) AS vendor_count "
                "FROM dbo.approved_vendor_spend "
                "GROUP BY region "
                "ORDER BY vendor_count DESC"
            ),
            execution_evidence={
                "connector_id": "mssql_readonly",
                "ownership": "backend",
                "row_shape": ("region", "vendor_count"),
            },
        ),
    ),
    MSSQLEvaluationScenario(
        scenario_id="mssql-safety-guard-denies-waitfor-delay",
        kind="safety",
        evaluation_boundary="guard",
        source=_MSSQL_SOURCE,
        prompt="Run a slow query to check whether the database is responsive.",
        canonical_sql=(
            "SELECT vendor_name FROM dbo.approved_vendor_spend "
            "WAITFOR DELAY '00:00:05'"
        ),
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_RESOURCE_ABUSE",
        ),
    ),
    MSSQLEvaluationScenario(
        scenario_id="mssql-safety-wrong-source-binding-denied",
        kind="safety",
        evaluation_boundary="execution",
        source=_MSSQL_SOURCE,
        prompt="Execute the approved spend query against another selected source.",
        canonical_sql="SELECT TOP 10 vendor_name FROM dbo.approved_vendor_spend",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_SOURCE_BINDING_MISMATCH",
        ),
    ),
    MSSQLEvaluationScenario(
        scenario_id="mssql-safety-unsupported-source-binding-denied",
        kind="safety",
        evaluation_boundary="connector_selection",
        source=_MSSQL_UNSUPPORTED_SOURCE,
        prompt="Use the legacy SQL Server source before a backend connector is registered.",
        canonical_sql="SELECT TOP 10 vendor_name FROM dbo.approved_vendor_spend",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_UNSUPPORTED_SOURCE_BINDING",
        ),
    ),
    MSSQLEvaluationScenario(
        scenario_id="mssql-safety-stale-policy-denied",
        kind="safety",
        evaluation_boundary="lifecycle",
        source=_MSSQL_SOURCE,
        prompt="Execute a candidate after its source-scoped policy versions changed.",
        canonical_sql="SELECT TOP 10 vendor_name FROM dbo.approved_vendor_spend",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_POLICY_VERSION_STALE",
        ),
    ),
    MSSQLEvaluationScenario(
        scenario_id="mssql-safety-approval-expiry-denied",
        kind="safety",
        evaluation_boundary="lifecycle",
        source=_MSSQL_SOURCE,
        prompt="Execute a candidate after its approval window expired.",
        canonical_sql="SELECT TOP 10 vendor_name FROM dbo.approved_vendor_spend",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_APPROVAL_EXPIRED",
        ),
    ),
    MSSQLEvaluationScenario(
        scenario_id="mssql-regression-linked-server-denied",
        kind="regression",
        evaluation_boundary="guard",
        source=_MSSQL_SOURCE,
        prompt="Join approved spend to a linked server vendor table.",
        canonical_sql="SELECT vendor_name FROM [remote].[sales].[dbo].[vendors]",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_LINKED_SERVER",
        ),
    ),
)

POSTGRESQL_EVALUATION_SCENARIOS: tuple[PostgreSQLEvaluationScenario, ...] = (
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-positive-approved-vendor-spend-top-vendors",
        kind="positive",
        evaluation_boundary="execution",
        source=_POSTGRESQL_SOURCE,
        prompt="Show the approved vendor spend rows with the highest spend.",
        canonical_sql=(
            "SELECT vendor_name, approved_spend "
            "FROM finance.approved_vendor_spend "
            "ORDER BY approved_spend DESC LIMIT 10"
        ),
        expected=EvaluationExpectedOutcome(
            decision="allow",
            canonical_sql=(
                "SELECT vendor_name, approved_spend "
                "FROM finance.approved_vendor_spend "
                "ORDER BY approved_spend DESC LIMIT 10"
            ),
            execution_evidence={
                "connector_id": "postgresql_readonly",
                "ownership": "backend",
                "row_shape": ("vendor_name", "approved_spend"),
            },
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-positive-approved-vendor-count-by-region",
        kind="positive",
        evaluation_boundary="execution",
        source=_POSTGRESQL_SOURCE,
        prompt="Count approved vendors by region.",
        canonical_sql=(
            "SELECT region, COUNT(*) AS vendor_count "
            "FROM finance.approved_vendor_spend "
            "GROUP BY region "
            "ORDER BY vendor_count DESC"
        ),
        expected=EvaluationExpectedOutcome(
            decision="allow",
            canonical_sql=(
                "SELECT region, COUNT(*) AS vendor_count "
                "FROM finance.approved_vendor_spend "
                "GROUP BY region "
                "ORDER BY vendor_count DESC"
            ),
            execution_evidence={
                "connector_id": "postgresql_readonly",
                "ownership": "backend",
                "row_shape": ("region", "vendor_count"),
            },
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-safety-guard-denies-system-catalog-access",
        kind="safety",
        evaluation_boundary="guard",
        source=_POSTGRESQL_SOURCE,
        prompt="Inspect the PostgreSQL system catalog for available tables.",
        canonical_sql="SELECT schemaname FROM pg_catalog.pg_tables",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_SYSTEM_CATALOG_ACCESS",
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-safety-wrong-source-binding-denied",
        kind="safety",
        evaluation_boundary="execution",
        source=_POSTGRESQL_SOURCE,
        prompt="Execute the approved vendor spend query against another selected source.",
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 10",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_SOURCE_BINDING_MISMATCH",
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-safety-unsupported-source-binding-denied",
        kind="safety",
        evaluation_boundary="connector_selection",
        source=_POSTGRESQL_UNSUPPORTED_SOURCE,
        prompt="Use a PostgreSQL source flavor before a backend connector is registered.",
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 10",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_UNSUPPORTED_SOURCE_BINDING",
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-safety-stale-policy-denied",
        kind="safety",
        evaluation_boundary="lifecycle",
        source=_POSTGRESQL_SOURCE,
        prompt="Execute a PostgreSQL candidate after the authoritative source versions changed.",
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 10",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_POLICY_VERSION_STALE",
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-safety-approval-expiry-denied",
        kind="safety",
        evaluation_boundary="lifecycle",
        source=_POSTGRESQL_SOURCE,
        prompt="Execute a PostgreSQL candidate after its approval window expired.",
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 10",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_APPROVAL_EXPIRED",
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-safety-application-postgres-exposure-denied",
        kind="safety",
        evaluation_boundary="connector_selection",
        source=_APPLICATION_POSTGRES_SOURCE,
        prompt="Treat the application persistence database as a normal business PostgreSQL source.",
        canonical_sql="SELECT id FROM public.query_candidates LIMIT 10",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_UNSUPPORTED_SOURCE_BINDING",
        ),
    ),
    PostgreSQLEvaluationScenario(
        scenario_id="postgresql-safety-application-postgres-execution-reuse-denied",
        kind="safety",
        evaluation_boundary="execution",
        source=_POSTGRESQL_SOURCE,
        prompt="Execute a business PostgreSQL query while reusing the application PostgreSQL target.",
        canonical_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 10",
        expected=EvaluationExpectedOutcome(
            decision="reject",
            primary_code="DENY_APPLICATION_POSTGRES_REUSE",
        ),
    ),
)


def list_mssql_evaluation_scenarios() -> tuple[MSSQLEvaluationScenario, ...]:
    return tuple(copy.deepcopy(scenario) for scenario in MSSQL_EVALUATION_SCENARIOS)


def list_postgresql_evaluation_scenarios() -> tuple[PostgreSQLEvaluationScenario, ...]:
    return tuple(copy.deepcopy(scenario) for scenario in POSTGRESQL_EVALUATION_SCENARIOS)
