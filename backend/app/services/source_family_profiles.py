from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


RolloutStatus = Literal["active_baseline", "planned", "planned_flavor"]


class ConnectorProfileRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    owner: Literal["backend"]
    read_only_posture: Literal["required"]
    secret_reference_pattern: str
    connection_identity_fields: tuple[str, ...]
    required_controls: tuple[str, ...]
    application_postgres_separation: str


class DialectProfileRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str
    canonicalization_requirements: tuple[str, ...]
    identifier_quoting: str
    row_bounding_strategy: str
    limit_behavior: str
    read_only_statement_allowlist: tuple[str, ...]
    fail_closed_denies: tuple[str, ...]


class AuditAndEvaluationRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reconstruction_fields: tuple[str, ...]
    preview_events: tuple[str, ...]
    guard_events: tuple[str, ...]
    execution_events: tuple[str, ...]
    denial_events: tuple[str, ...]
    release_gate_fields: tuple[str, ...]
    evaluation_corpus_requirements: tuple[str, ...]


class SourceFamilyProfileRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_family: str
    rollout_status: RolloutStatus
    execution_enabled_by_default: bool
    backend_selected: bool
    adapter_inference_allowed: bool
    permitted_source_flavors: tuple[str, ...]
    required_profile_contract_fields: tuple[str, ...]
    required_version_fields: tuple[str, ...]
    connector: ConnectorProfileRequirements
    dialect: DialectProfileRequirements
    audit_and_evaluation: AuditAndEvaluationRequirements


ACTIVE_SOURCE_FAMILIES: tuple[str, ...] = ("mssql", "postgresql")

MYSQL_FAMILY_PROFILE_REQUIREMENTS = SourceFamilyProfileRequirements(
    source_family="mysql",
    rollout_status="planned",
    execution_enabled_by_default=False,
    backend_selected=True,
    adapter_inference_allowed=False,
    permitted_source_flavors=("mysql-8", "aurora-mysql"),
    required_profile_contract_fields=(
        "source_id",
        "source_family",
        "source_flavor",
        "dataset_contract_version",
        "schema_snapshot_version",
        "execution_policy_version",
        "connector_profile_version",
        "dialect_profile_version",
        "activation_posture",
        "connection_reference",
    ),
    required_version_fields=(
        "dataset_contract_version",
        "schema_snapshot_version",
        "execution_policy_version",
        "connector_profile_version",
        "dialect_profile_version",
    ),
    connector=ConnectorProfileRequirements(
        profile_id="mysql.readonly.planned.v1",
        owner="backend",
        read_only_posture="required",
        secret_reference_pattern="safequery/business/mysql/<source_id>/reader",
        connection_identity_fields=(
            "host",
            "port",
            "database",
            "username",
            "tls_mode",
        ),
        required_controls=(
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        application_postgres_separation=(
            "mysql business source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    ),
    dialect=DialectProfileRequirements(
        profile_id="mysql.family.planned.v1",
        canonicalization_requirements=(
            "single_statement_select_shape",
            "mysql_keyword_normalization",
            "literal_preservation_before_guard",
            "schema_qualified_identifier_normalization",
        ),
        identifier_quoting="backtick identifiers by default; reject unsafe sql_mode assumptions",
        row_bounding_strategy="append_or_tighten_limit_before_guard_preview_and_execution",
        limit_behavior=(
            "canonical SQL must have one effective LIMIT bounded by the execution policy; "
            "OFFSET is allowed only with an explicit bounded LIMIT"
        ),
        read_only_statement_allowlist=("SELECT", "WITH_SELECT"),
        fail_closed_denies=(
            "multi_statement",
            "write_operation",
            "procedure_execution",
            "dynamic_sql",
            "external_data_access",
            "system_catalog_access",
            "cross_database_reference",
            "temporary_object_mutation",
            "unbounded_or_unsafe_limit",
            "unsupported_sql_syntax",
        ),
    ),
    audit_and_evaluation=AuditAndEvaluationRequirements(
        reconstruction_fields=(
            "source_id",
            "source_family",
            "source_flavor",
            "dataset_contract_version",
            "schema_snapshot_version",
            "execution_policy_version",
            "connector_profile_version",
            "dialect_profile_version",
            "guard_version",
            "primary_deny_code",
        ),
        preview_events=("query_submitted", "generation_completed"),
        guard_events=("guard_evaluated",),
        execution_events=("execution_requested", "execution_started", "execution_completed"),
        denial_events=("execution_denied", "candidate_invalidated"),
        release_gate_fields=(
            "scenario_id",
            "source.source_id",
            "source.source_family",
            "source.source_flavor",
            "source.dialect_profile",
            "source.dialect_profile_version",
            "source.connector_profile_version",
            "source.dataset_contract_version",
            "source.schema_snapshot_version",
            "source.execution_policy_version",
            "expected.primary_code",
        ),
        evaluation_corpus_requirements=(
            "positive_readonly_selects",
            "row_bounding_regressions",
            "guard_deny_corpus",
            "connector_timeout_and_cancellation",
            "release_gate_reconstruction",
        ),
    ),
)


PLANNED_SOURCE_FAMILY_PROFILE_REQUIREMENTS: tuple[
    SourceFamilyProfileRequirements, ...
] = (MYSQL_FAMILY_PROFILE_REQUIREMENTS,)


def get_planned_source_family_profile_requirements(
    source_family: str,
) -> SourceFamilyProfileRequirements | None:
    normalized_source_family = source_family.strip().lower()
    for requirements in PLANNED_SOURCE_FAMILY_PROFILE_REQUIREMENTS:
        if requirements.source_family == normalized_source_family:
            return requirements
    return None
