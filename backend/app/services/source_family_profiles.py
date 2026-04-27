from __future__ import annotations

from typing import Literal, Optional

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
    activation_required_coverage: tuple[str, ...]
    deny_corpus_requirements: tuple[str, ...]
    authoritative_release_gate_artifacts: tuple[str, ...]
    supplemental_only_artifacts: tuple[str, ...]


class ActiveSourceRuntimePostureRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_family: str
    rollout_status: Literal["active_baseline"]
    preview_timeout_seconds: int
    guard_timeout_seconds: int
    execute_timeout_seconds: int
    retryable_unavailable_states: tuple[str, ...]
    non_retryable_workflow_states: tuple[str, ...]
    retry_attempts: int
    retry_backoff: str
    pool_boundary: Literal["per_registered_source"]
    pool_sharing: Literal["no_cross_source_or_application_postgres_reuse"]
    pool_owner: Literal["backend"]


class SourceFamilyProfileRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_family: str
    rollout_status: RolloutStatus
    execution_enabled_by_default: bool
    backend_selected: bool
    adapter_inference_allowed: bool
    profile_classification: Literal["family_baseline", "mysql_delta"]
    shared_profile_basis: Optional[str]
    profile_deltas: tuple[str, ...]
    permitted_source_flavors: tuple[str, ...]
    required_profile_contract_fields: tuple[str, ...]
    required_version_fields: tuple[str, ...]
    connector: ConnectorProfileRequirements
    dialect: DialectProfileRequirements
    audit_and_evaluation: AuditAndEvaluationRequirements


class SourceFlavorProfileRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_family: str
    source_flavor: str
    rollout_status: Literal["planned_flavor"]
    execution_enabled_by_default: bool
    backend_selected: bool
    adapter_inference_allowed: bool
    shared_profile_basis: str
    inherited_behavior: tuple[str, ...]
    profile_deltas: tuple[str, ...]
    required_profile_contract_fields: tuple[str, ...]
    required_version_fields: tuple[str, ...]
    connector: ConnectorProfileRequirements
    dialect: DialectProfileRequirements
    audit_and_evaluation: AuditAndEvaluationRequirements


ACTIVE_SOURCE_FAMILIES: tuple[str, ...] = ("mssql", "postgresql")

ACTIVE_SOURCE_RETRYABLE_UNAVAILABLE_STATES: tuple[str, ...] = (
    "connection_timeout",
    "source_unreachable",
    "transient_driver_unavailable",
)

ACTIVE_SOURCE_NON_RETRYABLE_WORKFLOW_STATES: tuple[str, ...] = (
    "malformed_request",
    "policy_denied",
    "source_binding_mismatch",
    "unsupported_source_binding",
    "guard_denied",
)

MSSQL_ACTIVE_RUNTIME_POSTURE_REQUIREMENTS = ActiveSourceRuntimePostureRequirements(
    source_family="mssql",
    rollout_status="active_baseline",
    preview_timeout_seconds=30,
    guard_timeout_seconds=30,
    execute_timeout_seconds=30,
    retryable_unavailable_states=ACTIVE_SOURCE_RETRYABLE_UNAVAILABLE_STATES,
    non_retryable_workflow_states=ACTIVE_SOURCE_NON_RETRYABLE_WORKFLOW_STATES,
    retry_attempts=1,
    retry_backoff="none_inside_authoritative_execution_boundary",
    pool_boundary="per_registered_source",
    pool_sharing="no_cross_source_or_application_postgres_reuse",
    pool_owner="backend",
)

POSTGRESQL_ACTIVE_RUNTIME_POSTURE_REQUIREMENTS = ActiveSourceRuntimePostureRequirements(
    source_family="postgresql",
    rollout_status="active_baseline",
    preview_timeout_seconds=30,
    guard_timeout_seconds=30,
    execute_timeout_seconds=30,
    retryable_unavailable_states=ACTIVE_SOURCE_RETRYABLE_UNAVAILABLE_STATES,
    non_retryable_workflow_states=ACTIVE_SOURCE_NON_RETRYABLE_WORKFLOW_STATES,
    retry_attempts=1,
    retry_backoff="none_inside_authoritative_execution_boundary",
    pool_boundary="per_registered_source",
    pool_sharing="no_cross_source_or_application_postgres_reuse",
    pool_owner="backend",
)

ACTIVE_SOURCE_RUNTIME_POSTURE_REQUIREMENTS: tuple[
    ActiveSourceRuntimePostureRequirements, ...
] = (
    MSSQL_ACTIVE_RUNTIME_POSTURE_REQUIREMENTS,
    POSTGRESQL_ACTIVE_RUNTIME_POSTURE_REQUIREMENTS,
)

FUTURE_FAMILY_ACTIVATION_REQUIRED_COVERAGE: tuple[str, ...] = (
    "positive_scenarios",
    "safety_deny_scenarios",
    "connector_selection_scenarios",
    "candidate_lifecycle_scenarios",
    "runtime_control_scenarios",
    "audit_artifact_reconstruction",
    "release_gate_reconstruction",
    "operator_history_implications",
)

FUTURE_FAMILY_DENY_CORPUS_REQUIREMENTS: tuple[str, ...] = (
    "write_attempts",
    "multi_statement_behavior",
    "unsafe_functions",
    "unbounded_reads",
    "unsupported_syntax",
    "stale_policy",
    "entitlement_drift",
    "lifecycle_replay",
    "runtime_cancellation",
    "connector_profile_mismatch",
)

FUTURE_FAMILY_AUTH_RELEASE_GATE_ARTIFACTS: tuple[str, ...] = (
    "safequery_evaluation_outcomes",
    "safequery_source_aware_audit_events",
)

FUTURE_FAMILY_SUPPLEMENTAL_ONLY_ARTIFACTS: tuple[str, ...] = (
    "mlflow_exports",
    "search_or_analyst_outputs",
    "adapter_traces",
)

MYSQL_FAMILY_PROFILE_REQUIREMENTS = SourceFamilyProfileRequirements(
    source_family="mysql",
    rollout_status="planned",
    execution_enabled_by_default=False,
    backend_selected=True,
    adapter_inference_allowed=False,
    profile_classification="family_baseline",
    shared_profile_basis=None,
    profile_deltas=(),
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
        secret_reference_pattern="safequery/business/mysql/<source_id>/reader",  # noqa: S106 - reference template, not a credential
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
            "profile_version_drift_fail_closed",
        ),
        activation_required_coverage=FUTURE_FAMILY_ACTIVATION_REQUIRED_COVERAGE,
        deny_corpus_requirements=FUTURE_FAMILY_DENY_CORPUS_REQUIREMENTS,
        authoritative_release_gate_artifacts=FUTURE_FAMILY_AUTH_RELEASE_GATE_ARTIFACTS,
        supplemental_only_artifacts=FUTURE_FAMILY_SUPPLEMENTAL_ONLY_ARTIFACTS,
    ),
)

MARIADB_FAMILY_PROFILE_REQUIREMENTS = SourceFamilyProfileRequirements(
    source_family="mariadb",
    rollout_status="planned",
    execution_enabled_by_default=False,
    backend_selected=True,
    adapter_inference_allowed=False,
    profile_classification="mysql_delta",
    shared_profile_basis="mysql.family.planned.v1",
    profile_deltas=(
        "mariadb-mode canonicalization must be explicit",
        "sql_mode and version-specific parser drift",
        "information_schema and system catalog deny fixtures",
        "optimizer hint and executable comment deny fixtures",
        "connector identity must remain a backend-owned mariadb profile",
        "release-gate corpus must remain separate from mysql until approved",
    ),
    permitted_source_flavors=("mariadb-approved",),
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
        profile_id="mariadb.readonly.planned.v1",
        owner="backend",
        read_only_posture="required",
        secret_reference_pattern="safequery/business/mariadb/<source_id>/reader",  # noqa: S106 - reference template, not a credential
        connection_identity_fields=(
            "host",
            "port",
            "database",
            "username",
            "tls_mode",
            "server_version",
        ),
        required_controls=(
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        application_postgres_separation=(
            "mariadb business source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    ),
    dialect=DialectProfileRequirements(
        profile_id="mariadb.mysql-delta.planned.v1",
        canonicalization_requirements=(
            "single_statement_select_shape",
            "mysql_keyword_normalization",
            "mariadb_mode_feature_detection",
            "literal_preservation_before_guard",
            "schema_qualified_identifier_normalization",
        ),
        identifier_quoting=(
            "backtick identifiers by default; reject unsafe sql_mode and "
            "version-specific parser assumptions"
        ),
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
            "optimizer_hint_or_executable_comment",
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
            "mariadb_delta_deny_fixtures",
            "connector_timeout_and_cancellation",
            "release_gate_reconstruction",
            "profile_version_drift_fail_closed",
        ),
        activation_required_coverage=FUTURE_FAMILY_ACTIVATION_REQUIRED_COVERAGE,
        deny_corpus_requirements=FUTURE_FAMILY_DENY_CORPUS_REQUIREMENTS,
        authoritative_release_gate_artifacts=FUTURE_FAMILY_AUTH_RELEASE_GATE_ARTIFACTS,
        supplemental_only_artifacts=FUTURE_FAMILY_SUPPLEMENTAL_ONLY_ARTIFACTS,
    ),
)


ORACLE_FAMILY_PROFILE_REQUIREMENTS = SourceFamilyProfileRequirements(
    source_family="oracle",
    rollout_status="planned",
    execution_enabled_by_default=False,
    backend_selected=True,
    adapter_inference_allowed=False,
    profile_classification="family_baseline",
    shared_profile_basis=None,
    profile_deltas=(
        "oracle connector identity and wallet references must be backend-owned",
        "Oracle identifier case and quoted-name behavior must be explicit",
        "ROWNUM, FETCH FIRST, and analytic pagination behavior must be reviewed",
        "database links, packages, PL/SQL blocks, and session mutation must deny closed",
        "release-gate corpus must remain separate until Oracle activation approval",
    ),
    permitted_source_flavors=("oracle-19c", "oracle-23ai"),
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
        profile_id="oracle.readonly.long-range.v1",
        owner="backend",
        read_only_posture="required",
        secret_reference_pattern="safequery/business/oracle/<source_id>/reader",  # noqa: S106 - reference template, not a credential
        connection_identity_fields=(
            "connect_descriptor",
            "service_name",
            "username",
            "wallet_reference",
            "tls_mode",
        ),
        required_controls=(
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        application_postgres_separation=(
            "oracle business source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    ),
    dialect=DialectProfileRequirements(
        profile_id="oracle.family.long-range.v1",
        canonicalization_requirements=(
            "single_statement_select_shape",
            "oracle_identifier_normalization",
            "quoted_identifier_case_preservation",
            "literal_preservation_before_guard",
            "schema_qualified_identifier_normalization",
            "database_link_reference_rejection",
        ),
        identifier_quoting=(
            "Oracle double-quoted identifiers only when required; preserve case-sensitive "
            "quoted names and reject ambiguous unquoted identifier assumptions"
        ),
        row_bounding_strategy=(
            "approve one canonical FETCH FIRST or ROWNUM-bounded shape before guard, "
            "preview, and execution"
        ),
        limit_behavior=(
            "canonical SQL must have one effective policy-bounded row limit; Oracle "
            "pagination rewrites must not change guard, preview, and execute SQL"
        ),
        read_only_statement_allowlist=("SELECT", "WITH_SELECT"),
        fail_closed_denies=(
            "multi_statement",
            "write_operation",
            "procedure_execution",
            "dynamic_sql",
            "external_data_access",
            "system_catalog_access",
            "database_link_access",
            "session_or_package_state_mutation",
            "unbounded_or_unsafe_fetch",
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
            "guard_deny_corpus",
            "oracle_identifier_and_quoting_regressions",
            "oracle_row_bounding_regressions",
            "connector_timeout_and_cancellation",
            "release_gate_reconstruction",
            "profile_version_drift_fail_closed",
        ),
        activation_required_coverage=FUTURE_FAMILY_ACTIVATION_REQUIRED_COVERAGE,
        deny_corpus_requirements=FUTURE_FAMILY_DENY_CORPUS_REQUIREMENTS,
        authoritative_release_gate_artifacts=FUTURE_FAMILY_AUTH_RELEASE_GATE_ARTIFACTS,
        supplemental_only_artifacts=FUTURE_FAMILY_SUPPLEMENTAL_ONLY_ARTIFACTS,
    ),
)


AURORA_POSTGRESQL_FLAVOR_PROFILE_REQUIREMENTS = SourceFlavorProfileRequirements(
    source_family="postgresql",
    source_flavor="aurora-postgresql",
    rollout_status="planned_flavor",
    execution_enabled_by_default=False,
    backend_selected=True,
    adapter_inference_allowed=False,
    shared_profile_basis="postgresql.family.active.v1",
    inherited_behavior=(
        "postgresql_generation_profile",
        "postgresql_canonicalization",
        "postgresql_fail_closed_guard_profile",
        "postgresql_row_bounding",
        "postgresql_deny_corpus",
    ),
    profile_deltas=(
        "aurora connector identity and secret reference must be explicit",
        "cluster and instance endpoint posture must be recorded by the backend registry",
        "timeout and cancellation expectations must be verified against Aurora PostgreSQL",
        (
            "audit metadata must preserve source_family=postgresql and "
            "source_flavor=aurora-postgresql"
        ),
        (
            "release-gate corpus must include Aurora PostgreSQL flavor "
            "regressions before activation"
        ),
    ),
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
        profile_id="postgresql.aurora-readonly.planned.v1",
        owner="backend",
        read_only_posture="required",
        secret_reference_pattern=(
            "safequery/business/postgresql/<source_id>/reader"
        ),  # noqa: S106 - reference template, not a credential
        connection_identity_fields=(
            "cluster_endpoint",
            "port",
            "database",
            "username",
            "tls_mode",
            "engine_version",
        ),
        required_controls=(
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        application_postgres_separation=(
            "aurora postgresql source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    ),
    dialect=DialectProfileRequirements(
        profile_id="postgresql.aurora-flavor.planned.v1",
        canonicalization_requirements=(
            "single_statement_select_shape",
            "postgresql_identifier_normalization",
            "literal_preservation_before_guard",
            "schema_qualified_identifier_normalization",
        ),
        identifier_quoting=(
            "PostgreSQL double-quoted identifiers when quoting is required"
        ),
        row_bounding_strategy="append_or_tighten_limit_before_guard_preview_and_execution",
        limit_behavior=(
            "canonical SQL must preserve the PostgreSQL family bounded LIMIT behavior"
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
            "postgresql_positive_readonly_selects",
            "postgresql_guard_deny_corpus",
            "row_bounding_regressions",
            "aurora_postgresql_flavor_regressions",
            "connector_timeout_and_cancellation",
            "release_gate_reconstruction",
            "profile_version_drift_fail_closed",
        ),
        activation_required_coverage=FUTURE_FAMILY_ACTIVATION_REQUIRED_COVERAGE,
        deny_corpus_requirements=FUTURE_FAMILY_DENY_CORPUS_REQUIREMENTS,
        authoritative_release_gate_artifacts=FUTURE_FAMILY_AUTH_RELEASE_GATE_ARTIFACTS,
        supplemental_only_artifacts=FUTURE_FAMILY_SUPPLEMENTAL_ONLY_ARTIFACTS,
    ),
)


AURORA_MYSQL_FLAVOR_PROFILE_REQUIREMENTS = SourceFlavorProfileRequirements(
    source_family="mysql",
    source_flavor="aurora-mysql",
    rollout_status="planned_flavor",
    execution_enabled_by_default=False,
    backend_selected=True,
    adapter_inference_allowed=False,
    shared_profile_basis="mysql.family.planned.v1",
    inherited_behavior=(
        "mysql_generation_profile",
        "mysql_canonicalization",
        "mysql_fail_closed_guard_profile",
        "mysql_row_bounding",
        "mysql_deny_corpus",
    ),
    profile_deltas=(
        "aurora connector identity and secret reference must be explicit",
        "cluster and instance endpoint posture must be recorded by the backend registry",
        "timeout and cancellation expectations must be verified against Aurora MySQL",
        "audit metadata must preserve source_family=mysql and source_flavor=aurora-mysql",
        "release-gate corpus must include Aurora MySQL flavor regressions before activation",
    ),
    required_profile_contract_fields=(
        MYSQL_FAMILY_PROFILE_REQUIREMENTS.required_profile_contract_fields
    ),
    required_version_fields=MYSQL_FAMILY_PROFILE_REQUIREMENTS.required_version_fields,
    connector=ConnectorProfileRequirements(
        profile_id="mysql.aurora-readonly.planned.v1",
        owner="backend",
        read_only_posture="required",
        secret_reference_pattern=(
            "safequery/business/mysql/<source_id>/reader"
        ),  # noqa: S106 - reference template, not a credential
        connection_identity_fields=(
            "cluster_endpoint",
            "port",
            "database",
            "username",
            "tls_mode",
            "engine_version",
        ),
        required_controls=(
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        application_postgres_separation=(
            "aurora mysql source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    ),
    dialect=DialectProfileRequirements(
        profile_id="mysql.aurora-flavor.planned.v1",
        canonicalization_requirements=(
            MYSQL_FAMILY_PROFILE_REQUIREMENTS.dialect.canonicalization_requirements
        ),
        identifier_quoting=MYSQL_FAMILY_PROFILE_REQUIREMENTS.dialect.identifier_quoting,
        row_bounding_strategy=(
            MYSQL_FAMILY_PROFILE_REQUIREMENTS.dialect.row_bounding_strategy
        ),
        limit_behavior=MYSQL_FAMILY_PROFILE_REQUIREMENTS.dialect.limit_behavior,
        read_only_statement_allowlist=(
            MYSQL_FAMILY_PROFILE_REQUIREMENTS.dialect.read_only_statement_allowlist
        ),
        fail_closed_denies=MYSQL_FAMILY_PROFILE_REQUIREMENTS.dialect.fail_closed_denies,
    ),
    audit_and_evaluation=AuditAndEvaluationRequirements(
        reconstruction_fields=(
            MYSQL_FAMILY_PROFILE_REQUIREMENTS.audit_and_evaluation.reconstruction_fields
        ),
        preview_events=MYSQL_FAMILY_PROFILE_REQUIREMENTS.audit_and_evaluation.preview_events,
        guard_events=MYSQL_FAMILY_PROFILE_REQUIREMENTS.audit_and_evaluation.guard_events,
        execution_events=(
            MYSQL_FAMILY_PROFILE_REQUIREMENTS.audit_and_evaluation.execution_events
        ),
        denial_events=MYSQL_FAMILY_PROFILE_REQUIREMENTS.audit_and_evaluation.denial_events,
        release_gate_fields=(
            MYSQL_FAMILY_PROFILE_REQUIREMENTS.audit_and_evaluation.release_gate_fields
        ),
        evaluation_corpus_requirements=(
            "positive_readonly_selects",
            "row_bounding_regressions",
            "guard_deny_corpus",
            "aurora_mysql_flavor_regressions",
            "connector_timeout_and_cancellation",
            "release_gate_reconstruction",
            "profile_version_drift_fail_closed",
        ),
        activation_required_coverage=FUTURE_FAMILY_ACTIVATION_REQUIRED_COVERAGE,
        deny_corpus_requirements=FUTURE_FAMILY_DENY_CORPUS_REQUIREMENTS,
        authoritative_release_gate_artifacts=FUTURE_FAMILY_AUTH_RELEASE_GATE_ARTIFACTS,
        supplemental_only_artifacts=FUTURE_FAMILY_SUPPLEMENTAL_ONLY_ARTIFACTS,
    ),
)


PLANNED_SOURCE_FAMILY_PROFILE_REQUIREMENTS: tuple[
    SourceFamilyProfileRequirements, ...
] = (
    MYSQL_FAMILY_PROFILE_REQUIREMENTS,
    MARIADB_FAMILY_PROFILE_REQUIREMENTS,
    ORACLE_FAMILY_PROFILE_REQUIREMENTS,
)

PLANNED_SOURCE_FLAVOR_PROFILE_REQUIREMENTS: tuple[
    SourceFlavorProfileRequirements, ...
] = (
    AURORA_POSTGRESQL_FLAVOR_PROFILE_REQUIREMENTS,
    AURORA_MYSQL_FLAVOR_PROFILE_REQUIREMENTS,
)


def get_active_source_runtime_posture_requirements(
    source_family: str,
) -> ActiveSourceRuntimePostureRequirements | None:
    normalized_source_family = source_family.strip().lower()
    for requirements in ACTIVE_SOURCE_RUNTIME_POSTURE_REQUIREMENTS:
        if requirements.source_family == normalized_source_family:
            return requirements
    return None


def get_planned_source_family_profile_requirements(
    source_family: str,
) -> SourceFamilyProfileRequirements | None:
    normalized_source_family = source_family.strip().lower()
    for requirements in PLANNED_SOURCE_FAMILY_PROFILE_REQUIREMENTS:
        if requirements.source_family == normalized_source_family:
            return requirements
    return None


def get_planned_source_flavor_profile_requirements(
    *,
    source_family: str,
    source_flavor: str,
) -> SourceFlavorProfileRequirements | None:
    normalized_source_family = source_family.strip().lower()
    normalized_source_flavor = source_flavor.strip().lower()
    for requirements in PLANNED_SOURCE_FLAVOR_PROFILE_REQUIREMENTS:
        if (
            requirements.source_family == normalized_source_family
            and requirements.source_flavor == normalized_source_flavor
        ):
            return requirements
    return None
