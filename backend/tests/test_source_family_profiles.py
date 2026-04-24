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
    MARIADB_FAMILY_PROFILE_REQUIREMENTS,
    MYSQL_FAMILY_PROFILE_REQUIREMENTS,
    get_planned_source_family_profile_requirements,
)


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


def test_mysql_family_requirements_cover_connector_dialect_guard_and_audit() -> None:
    requirements = MYSQL_FAMILY_PROFILE_REQUIREMENTS

    assert requirements.connector.model_dump() == {
        "profile_id": "mysql.readonly.planned.v1",
        "owner": "backend",
        "read_only_posture": "required",
        "secret_reference_pattern": "safequery/business/mysql/<source_id>/reader",
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
        "secret_reference_pattern": "safequery/business/mariadb/<source_id>/reader",
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
