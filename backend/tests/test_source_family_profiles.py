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
    assert set(requirements.required_version_fields) == {
        "dataset_contract_version",
        "schema_snapshot_version",
        "execution_policy_version",
        "connector_profile_version",
        "dialect_profile_version",
    }


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
        "primary_deny_code",
    }.issubset(set(requirements.audit_and_evaluation.reconstruction_fields))
    assert {
        "positive_readonly_selects",
        "row_bounding_regressions",
        "guard_deny_corpus",
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
