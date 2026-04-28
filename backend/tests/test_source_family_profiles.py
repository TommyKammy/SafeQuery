import pytest

from app.features.execution.connector_selection import (
    ExecutionConnectorSelectionError,
    select_execution_connector,
)
from app.features.execution.runtime import (
    DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY,
    DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY,
)
from app.features.guard.deny_taxonomy import DENY_UNSUPPORTED_SOURCE_BINDING
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata
from app.services.source_family_profiles import (
    ACTIVE_SOURCE_FAMILIES,
    AURORA_MYSQL_FLAVOR_PROFILE_REQUIREMENTS,
    AURORA_POSTGRESQL_FLAVOR_PROFILE_REQUIREMENTS,
    MARIADB_FAMILY_PROFILE_REQUIREMENTS,
    MYSQL_FAMILY_PROFILE_REQUIREMENTS,
    ORACLE_FAMILY_PROFILE_REQUIREMENTS,
    get_active_source_runtime_posture_requirements,
    get_planned_source_flavor_profile_requirements,
    get_planned_source_family_profile_requirements,
)


def _future_family_requirements():
    return (
        MYSQL_FAMILY_PROFILE_REQUIREMENTS,
        MARIADB_FAMILY_PROFILE_REQUIREMENTS,
        ORACLE_FAMILY_PROFILE_REQUIREMENTS,
        AURORA_POSTGRESQL_FLAVOR_PROFILE_REQUIREMENTS,
        AURORA_MYSQL_FLAVOR_PROFILE_REQUIREMENTS,
    )


def test_future_family_activation_checklist_requires_authoritative_coverage() -> None:
    required_activation_coverage = {
        "positive_scenarios",
        "safety_deny_scenarios",
        "connector_selection_scenarios",
        "candidate_lifecycle_scenarios",
        "runtime_control_scenarios",
        "audit_artifact_reconstruction",
        "release_gate_reconstruction",
        "operator_history_implications",
    }
    required_deny_topics = {
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
    }
    supplemental_only = {
        "mlflow_exports",
        "search_or_analyst_outputs",
        "adapter_traces",
    }

    for requirements in _future_family_requirements():
        audit_and_evaluation = requirements.audit_and_evaluation

        assert required_activation_coverage.issubset(
            audit_and_evaluation.activation_required_coverage
        )
        assert required_deny_topics.issubset(
            audit_and_evaluation.deny_corpus_requirements
        )
        assert "profile_version_drift_fail_closed" in (
            audit_and_evaluation.evaluation_corpus_requirements
        )
        assert supplemental_only.issubset(
            audit_and_evaluation.supplemental_only_artifacts
        )
        assert not supplemental_only.intersection(
            audit_and_evaluation.authoritative_release_gate_artifacts
        )
        assert {
            "safequery_evaluation_outcomes",
            "safequery_source_aware_audit_events",
        }.issubset(audit_and_evaluation.authoritative_release_gate_artifacts)


def test_future_family_activation_gate_requires_runtime_driver_and_secret_readiness() -> None:
    required_secret_checks = {
        "backend_secret_indirection_required",
        "secret_reference_resolves_before_activation",
        "blank_secret_rejected",
        "placeholder_secret_rejected",
        "raw_connection_string_rejected",
        "connection_string_redaction_required",
        "client_supplied_connection_material_rejected",
    }
    required_activation_checks = {
        "driver_import_or_installation_check",
        "first_run_doctor_family_runtime_check",
        "support_bundle_redacted_readiness_snapshot",
        "application_postgres_separation_check",
    }

    expected_driver_dependencies = {
        "mysql": ("mysqlclient_or_pymysql",),
        "mariadb": ("mariadb_connector_or_pymysql",),
        "oracle": ("python-oracledb", "oracle_client_or_wallet_when_required"),
        "aurora-postgresql": ("psycopg",),
        "aurora-mysql": ("mysqlclient_or_pymysql",),
    }

    for requirements in _future_family_requirements():
        connector = requirements.connector
        profile_key = getattr(
            requirements,
            "source_flavor",
            requirements.source_family,
        )

        assert set(connector.runtime_driver_dependencies) == set(
            expected_driver_dependencies[profile_key]
        )
        assert required_secret_checks.issubset(set(connector.secret_readiness_checks))
        assert required_activation_checks.issubset(
            set(connector.activation_gate_checks)
        )
        assert connector.secret_loading_owner == "trusted_backend"
        assert (
            connector.connection_string_redaction
            == "required_before_logs_exports_or_support_bundles"
        )


def test_active_source_runtime_posture_is_explicit_for_timeout_retry_and_pooling() -> None:
    for source_family in ACTIVE_SOURCE_FAMILIES:
        posture = get_active_source_runtime_posture_requirements(source_family)

        assert posture is not None
        assert posture.source_family == source_family
        assert posture.rollout_status == "active_baseline"
        assert posture.preview_timeout_seconds == DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY[
            source_family
        ]
        assert posture.guard_timeout_seconds == DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY[
            source_family
        ]
        assert posture.execute_timeout_seconds == DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY[
            source_family
        ]
        assert posture.retryable_unavailable_states == (
            "connection_timeout",
            "source_unreachable",
            "transient_driver_unavailable",
        )
        assert posture.non_retryable_workflow_states == (
            "malformed_request",
            "policy_denied",
            "source_binding_mismatch",
            "unsupported_source_binding",
            "guard_denied",
        )
        assert posture.pool_boundary == "per_registered_source"
        assert posture.pool_sharing == "no_cross_source_or_application_postgres_reuse"
        assert posture.pool_owner == "backend"
        assert posture.retry_attempts == 1
        assert posture.retry_backoff == "none_inside_authoritative_execution_boundary"


def test_mysql_family_requirements_are_planned_and_backend_selected() -> None:
    requirements = get_planned_source_family_profile_requirements(" MySQL ")

    assert requirements == MYSQL_FAMILY_PROFILE_REQUIREMENTS
    assert requirements.source_family == "mysql"
    assert requirements.rollout_status == "planned"
    assert requirements.execution_enabled_by_default is False
    assert requirements.backend_selected is True
    assert requirements.adapter_inference_allowed is False
    assert requirements.permitted_source_flavors == ("mysql-8", "aurora-mysql")
    assert set(requirements.required_profile_contract_fields) == {
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
    }
    assert set(requirements.required_version_fields) == {
        "dataset_contract_version",
        "schema_snapshot_version",
        "execution_policy_version",
        "connector_profile_version",
        "dialect_profile_version",
    }
    assert set(requirements.required_version_fields).issubset(
        requirements.required_profile_contract_fields
    )


def test_mariadb_profile_is_planned_mysql_delta_and_backend_selected() -> None:
    requirements = get_planned_source_family_profile_requirements(" MariaDB ")

    assert requirements == MARIADB_FAMILY_PROFILE_REQUIREMENTS
    assert requirements.source_family == "mariadb"
    assert requirements.rollout_status == "planned"
    assert requirements.execution_enabled_by_default is False
    assert requirements.backend_selected is True
    assert requirements.adapter_inference_allowed is False
    assert requirements.profile_classification == "mysql_delta"
    assert requirements.shared_profile_basis == "mysql.family.planned.v1"
    assert "mariadb-mode canonicalization must be explicit" in requirements.profile_deltas
    assert "sql_mode and version-specific parser drift" in requirements.profile_deltas


def test_oracle_family_requirements_are_long_range_planned_and_backend_selected() -> None:
    requirements = get_planned_source_family_profile_requirements(" Oracle ")

    assert requirements == ORACLE_FAMILY_PROFILE_REQUIREMENTS
    assert requirements.source_family == "oracle"
    assert requirements.rollout_status == "planned"
    assert requirements.execution_enabled_by_default is False
    assert requirements.backend_selected is True
    assert requirements.adapter_inference_allowed is False
    assert requirements.permitted_source_flavors == ("oracle-19c", "oracle-23ai")
    assert set(requirements.required_profile_contract_fields) == {
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
    }
    assert set(requirements.required_version_fields).issubset(
        requirements.required_profile_contract_fields
    )


def test_aurora_flavors_are_backend_selected_family_flavors() -> None:
    aurora_postgresql = get_planned_source_flavor_profile_requirements(
        source_family=" PostgreSQL ",
        source_flavor=" Aurora-PostgreSQL ",
    )
    aurora_mysql = get_planned_source_flavor_profile_requirements(
        source_family=" mysql ",
        source_flavor=" aurora-mysql ",
    )

    assert aurora_postgresql == AURORA_POSTGRESQL_FLAVOR_PROFILE_REQUIREMENTS
    assert aurora_postgresql.source_family == "postgresql"
    assert aurora_postgresql.source_flavor == "aurora-postgresql"
    assert aurora_postgresql.rollout_status == "planned_flavor"
    assert aurora_postgresql.backend_selected is True
    assert aurora_postgresql.adapter_inference_allowed is False
    assert aurora_postgresql.shared_profile_basis == "postgresql.family.active.v1"

    assert aurora_mysql == AURORA_MYSQL_FLAVOR_PROFILE_REQUIREMENTS
    assert aurora_mysql.source_family == "mysql"
    assert aurora_mysql.source_flavor == "aurora-mysql"
    assert aurora_mysql.rollout_status == "planned_flavor"
    assert aurora_mysql.backend_selected is True
    assert aurora_mysql.adapter_inference_allowed is False
    assert aurora_mysql.shared_profile_basis == "mysql.family.planned.v1"


def test_aurora_flavor_requirements_cover_inheritance_and_deltas() -> None:
    aurora_postgresql = AURORA_POSTGRESQL_FLAVOR_PROFILE_REQUIREMENTS
    aurora_mysql = AURORA_MYSQL_FLAVOR_PROFILE_REQUIREMENTS

    assert {
        "postgresql_generation_profile",
        "postgresql_canonicalization",
        "postgresql_fail_closed_guard_profile",
        "postgresql_row_bounding",
        "postgresql_deny_corpus",
    }.issubset(set(aurora_postgresql.inherited_behavior))
    assert (
        aurora_postgresql.connector.profile_id
        == "postgresql.aurora-readonly.planned.v1"
    )
    assert aurora_postgresql.dialect.profile_id == "postgresql.aurora-flavor.planned.v1"
    assert "cluster_endpoint" in aurora_postgresql.connector.connection_identity_fields
    assert "engine_version" in aurora_postgresql.connector.connection_identity_fields
    assert "connector_timeout_and_cancellation" in (
        aurora_postgresql.audit_and_evaluation.evaluation_corpus_requirements
    )
    assert "aurora_postgresql_flavor_regressions" in (
        aurora_postgresql.audit_and_evaluation.evaluation_corpus_requirements
    )

    assert {
        "mysql_generation_profile",
        "mysql_canonicalization",
        "mysql_fail_closed_guard_profile",
        "mysql_row_bounding",
        "mysql_deny_corpus",
    }.issubset(set(aurora_mysql.inherited_behavior))
    assert aurora_mysql.connector.profile_id == "mysql.aurora-readonly.planned.v1"
    assert aurora_mysql.dialect.profile_id == "mysql.aurora-flavor.planned.v1"
    assert aurora_mysql.dialect.fail_closed_denies == (
        MYSQL_FAMILY_PROFILE_REQUIREMENTS.dialect.fail_closed_denies
    )
    assert aurora_mysql.required_profile_contract_fields == (
        MYSQL_FAMILY_PROFILE_REQUIREMENTS.required_profile_contract_fields
    )
    assert "cluster_endpoint" in aurora_mysql.connector.connection_identity_fields
    assert "engine_version" in aurora_mysql.connector.connection_identity_fields
    assert "aurora_mysql_flavor_regressions" in (
        aurora_mysql.audit_and_evaluation.evaluation_corpus_requirements
    )


def test_aurora_flavor_lookup_rejects_family_mismatch_fail_closed() -> None:
    assert (
        get_planned_source_flavor_profile_requirements(
            source_family="aurora-postgresql",
            source_flavor="aurora-postgresql",
        )
        is None
    )
    assert (
        get_planned_source_flavor_profile_requirements(
            source_family="postgresql",
            source_flavor="aurora-mysql",
        )
        is None
    )


def test_mysql_family_requirements_cover_connector_dialect_guard_and_audit() -> None:
    requirements = MYSQL_FAMILY_PROFILE_REQUIREMENTS

    assert requirements.connector.model_dump() == {
        "profile_id": "mysql.readonly.planned.v1",
        "owner": "backend",
        "read_only_posture": "required",
        "runtime_driver_dependencies": ("mysqlclient_or_pymysql",),
        "secret_reference_pattern": "safequery/business/mysql/<source_id>/reader",
        "secret_loading_owner": "trusted_backend",
        "secret_readiness_checks": (
            "backend_secret_indirection_required",
            "secret_reference_resolves_before_activation",
            "blank_secret_rejected",
            "placeholder_secret_rejected",
            "raw_connection_string_rejected",
            "connection_string_redaction_required",
            "client_supplied_connection_material_rejected",
        ),
        "connection_string_redaction": "required_before_logs_exports_or_support_bundles",
        "connection_identity_fields": (
            "host",
            "port",
            "database",
            "username",
            "tls_mode",
        ),
        "required_controls": (
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        "activation_gate_checks": (
            "driver_import_or_installation_check",
            "first_run_doctor_family_runtime_check",
            "support_bundle_redacted_readiness_snapshot",
            "application_postgres_separation_check",
        ),
        "application_postgres_separation": (
            "mysql business source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    }
    assert requirements.dialect.identifier_quoting.startswith("backtick identifiers")
    assert requirements.dialect.read_only_statement_allowlist == ("SELECT", "WITH_SELECT")
    assert {
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
    }.issubset(set(requirements.dialect.fail_closed_denies))
    assert {
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
    }.issubset(set(requirements.audit_and_evaluation.reconstruction_fields))
    assert {
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
    }.issubset(set(requirements.audit_and_evaluation.release_gate_fields))
    assert {
        "positive_readonly_selects",
        "row_bounding_regressions",
        "guard_deny_corpus",
        "connector_timeout_and_cancellation",
        "release_gate_reconstruction",
    }.issubset(set(requirements.audit_and_evaluation.evaluation_corpus_requirements))


def test_mariadb_delta_requirements_cover_shared_and_specific_boundaries() -> None:
    requirements = MARIADB_FAMILY_PROFILE_REQUIREMENTS

    assert requirements.connector.model_dump() == {
        "profile_id": "mariadb.readonly.planned.v1",
        "owner": "backend",
        "read_only_posture": "required",
        "runtime_driver_dependencies": ("mariadb_connector_or_pymysql",),
        "secret_reference_pattern": "safequery/business/mariadb/<source_id>/reader",
        "secret_loading_owner": "trusted_backend",
        "secret_readiness_checks": (
            "backend_secret_indirection_required",
            "secret_reference_resolves_before_activation",
            "blank_secret_rejected",
            "placeholder_secret_rejected",
            "raw_connection_string_rejected",
            "connection_string_redaction_required",
            "client_supplied_connection_material_rejected",
        ),
        "connection_string_redaction": "required_before_logs_exports_or_support_bundles",
        "connection_identity_fields": (
            "host",
            "port",
            "database",
            "username",
            "tls_mode",
            "server_version",
        ),
        "required_controls": (
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        "activation_gate_checks": (
            "driver_import_or_installation_check",
            "first_run_doctor_family_runtime_check",
            "support_bundle_redacted_readiness_snapshot",
            "application_postgres_separation_check",
        ),
        "application_postgres_separation": (
            "mariadb business source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    }
    assert requirements.dialect.profile_id == "mariadb.mysql-delta.planned.v1"
    assert "mysql_keyword_normalization" in requirements.dialect.canonicalization_requirements
    assert "mariadb_mode_feature_detection" in requirements.dialect.canonicalization_requirements
    assert requirements.dialect.row_bounding_strategy == (
        "append_or_tighten_limit_before_guard_preview_and_execution"
    )
    assert requirements.dialect.read_only_statement_allowlist == ("SELECT", "WITH_SELECT")
    assert {
        "system_catalog_access",
        "optimizer_hint_or_executable_comment",
        "unsupported_sql_syntax",
    }.issubset(set(requirements.dialect.fail_closed_denies))
    assert {
        "source_family",
        "source_flavor",
        "connector_profile_version",
        "dialect_profile_version",
        "guard_version",
        "primary_deny_code",
    }.issubset(set(requirements.audit_and_evaluation.reconstruction_fields))
    assert {
        "guard_deny_corpus",
        "mariadb_delta_deny_fixtures",
        "connector_timeout_and_cancellation",
        "release_gate_reconstruction",
    }.issubset(set(requirements.audit_and_evaluation.evaluation_corpus_requirements))


def test_oracle_requirements_cover_connector_dialect_guard_and_audit() -> None:
    requirements = ORACLE_FAMILY_PROFILE_REQUIREMENTS

    assert requirements.connector.model_dump() == {
        "profile_id": "oracle.readonly.long-range.v1",
        "owner": "backend",
        "read_only_posture": "required",
        "runtime_driver_dependencies": (
            "python-oracledb",
            "oracle_client_or_wallet_when_required",
        ),
        "secret_reference_pattern": "safequery/business/oracle/<source_id>/reader",
        "secret_loading_owner": "trusted_backend",
        "secret_readiness_checks": (
            "backend_secret_indirection_required",
            "secret_reference_resolves_before_activation",
            "blank_secret_rejected",
            "placeholder_secret_rejected",
            "raw_connection_string_rejected",
            "connection_string_redaction_required",
            "client_supplied_connection_material_rejected",
        ),
        "connection_string_redaction": "required_before_logs_exports_or_support_bundles",
        "connection_identity_fields": (
            "connect_descriptor",
            "service_name",
            "username",
            "wallet_reference",
            "tls_mode",
        ),
        "required_controls": (
            "connect_timeout_seconds",
            "statement_timeout_seconds",
            "cancellation_probe",
        ),
        "activation_gate_checks": (
            "driver_import_or_installation_check",
            "first_run_doctor_family_runtime_check",
            "support_bundle_redacted_readiness_snapshot",
            "application_postgres_separation_check",
        ),
        "application_postgres_separation": (
            "oracle business source credentials and endpoints must be distinct from "
            "the application PostgreSQL system of record"
        ),
    }
    assert requirements.dialect.profile_id == "oracle.family.long-range.v1"
    assert "oracle_identifier_normalization" in (
        requirements.dialect.canonicalization_requirements
    )
    assert "quoted_identifier_case_preservation" in (
        requirements.dialect.canonicalization_requirements
    )
    assert requirements.dialect.read_only_statement_allowlist == ("SELECT", "WITH_SELECT")
    assert {
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
    }.issubset(set(requirements.dialect.fail_closed_denies))
    assert {
        "source_family",
        "source_flavor",
        "connector_profile_version",
        "dialect_profile_version",
        "guard_version",
        "primary_deny_code",
    }.issubset(set(requirements.audit_and_evaluation.reconstruction_fields))
    assert {
        "guard_deny_corpus",
        "oracle_identifier_and_quoting_regressions",
        "oracle_row_bounding_regressions",
        "connector_timeout_and_cancellation",
        "release_gate_reconstruction",
    }.issubset(set(requirements.audit_and_evaluation.evaluation_corpus_requirements))


def test_planned_mysql_profile_does_not_enable_active_execution_paths() -> None:
    assert ACTIVE_SOURCE_FAMILIES == ("mssql", "postgresql")
    assert "mysql" not in DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY
    assert "mysql" not in DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY

    with pytest.raises(
        ExecutionConnectorSelectionError,
        match="No backend-owned execution connector is registered",
    ) as exc_info:
        select_execution_connector(
            candidate_source=SourceBoundCandidateMetadata(
                source_id="future-mysql-source",
                source_family="mysql",
                source_flavor="mysql-8",
                dataset_contract_version=1,
                schema_snapshot_version=1,
            )
        )

    assert exc_info.value.deny_code == DENY_UNSUPPORTED_SOURCE_BINDING


def test_planned_mariadb_profile_does_not_enable_active_execution_paths() -> None:
    assert ACTIVE_SOURCE_FAMILIES == ("mssql", "postgresql")
    assert "mariadb" not in DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY
    assert "mariadb" not in DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY

    with pytest.raises(
        ExecutionConnectorSelectionError,
        match="No backend-owned execution connector is registered",
    ) as exc_info:
        select_execution_connector(
            candidate_source=SourceBoundCandidateMetadata(
                source_id="future-mariadb-source",
                source_family="mariadb",
                source_flavor="mariadb-approved",
                dataset_contract_version=1,
                schema_snapshot_version=1,
            )
        )

    assert exc_info.value.deny_code == DENY_UNSUPPORTED_SOURCE_BINDING


def test_long_range_oracle_profile_does_not_enable_active_execution_paths() -> None:
    assert ACTIVE_SOURCE_FAMILIES == ("mssql", "postgresql")
    assert "oracle" not in DEFAULT_TIMEOUT_SECONDS_BY_SOURCE_FAMILY
    assert "oracle" not in DEFAULT_MAX_ROWS_BY_SOURCE_FAMILY

    with pytest.raises(
        ExecutionConnectorSelectionError,
        match="No backend-owned execution connector is registered",
    ) as exc_info:
        select_execution_connector(
            candidate_source=SourceBoundCandidateMetadata(
                source_id="future-oracle-source",
                source_family="oracle",
                source_flavor="oracle-19c",
                dataset_contract_version=1,
                schema_snapshot_version=1,
            )
        )

    assert exc_info.value.deny_code == DENY_UNSUPPORTED_SOURCE_BINDING
