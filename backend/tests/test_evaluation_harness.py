from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.features.evaluation import (
    MSSQLEvaluationScenario,
    PostgreSQLEvaluationScenario,
    list_mssql_evaluation_scenarios,
    list_postgresql_evaluation_scenarios,
)
from app.features.execution import (
    ExecutionConnectorExecutionError,
    ExecutionConnectorSelectionError,
    execute_candidate_sql,
    select_execution_connector,
)
from app.features.execution.connector_selection import ExecutionConnectorSelection
from app.features.execution.runtime import ExecutableCandidateRecord
from app.features.guard import evaluate_mssql_sql_guard
from app.features.guard.deny_taxonomy import (
    DENY_APPLICATION_POSTGRES_REUSE,
    DENY_APPROVAL_EXPIRED,
    DENY_POLICY_VERSION_STALE,
    DENY_SOURCE_BINDING_MISMATCH,
    DENY_UNSUPPORTED_SOURCE_BINDING,
)
from app.features.guard.sql_guard import evaluate_postgresql_sql_guard
from app.services.candidate_lifecycle import (
    CandidateLifecycleRecord,
    CandidateLifecycleRevalidationError,
    SourceBoundCandidateMetadata,
    revalidate_candidate_lifecycle,
)


MSSQL_TEST_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=tcp:business-mssql-source,1433;"
    "Database=business;"
    "Uid=svc_safequery_exec;"
    "Pwd=unused-test-password;"
    "Encrypt=yes;"
    "TrustServerCertificate=no"
)

POSTGRESQL_TEST_URL = (
    "postgresql://placeholder_user:placeholder_password@business-postgres-source:5432/business"
)
APPLICATION_POSTGRESQL_TEST_URL = (
    "postgresql://placeholder_user:placeholder_password@app-postgres:5432/safequery"
)


def _mssql_scenarios_by_id() -> dict[str, MSSQLEvaluationScenario]:
    return {
        scenario.scenario_id: scenario
        for scenario in list_mssql_evaluation_scenarios()
    }


def _postgresql_scenarios_by_id() -> dict[str, PostgreSQLEvaluationScenario]:
    return {
        scenario.scenario_id: scenario
        for scenario in list_postgresql_evaluation_scenarios()
    }


def _candidate_source(scenario: MSSQLEvaluationScenario) -> SourceBoundCandidateMetadata:
    return SourceBoundCandidateMetadata(
        source_id=scenario.source.source_id,
        source_family=scenario.source.source_family,
        source_flavor=scenario.source.source_flavor,
        dataset_contract_version=scenario.source.dataset_contract_version,
        schema_snapshot_version=scenario.source.schema_snapshot_version,
    )


@contextmanager
def _session_scope() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed_mssql_source(
    session: Session,
    *,
    scenario: MSSQLEvaluationScenario,
    contract_version: int | None = None,
    snapshot_version: int | None = None,
) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id=scenario.source.source_id,
        display_label=f"{scenario.source.source_id} display",
        source_family=scenario.source.source_family,
        source_flavor=scenario.source.source_flavor,
        activation_posture=SourceActivationPosture.ACTIVE,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference=f"vault:{scenario.source.source_id}",
    )
    session.add(source)
    session.flush()

    snapshot = SchemaSnapshot(
        id=uuid4(),
        registered_source_id=source.id,
        snapshot_version=snapshot_version or scenario.source.schema_snapshot_version,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=contract_version or scenario.source.dataset_contract_version,
        display_name=f"{scenario.source.source_id} contract",
        owner_binding="group:finance-analysts",
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()


def _lifecycle_candidate(
    *,
    scenario: MSSQLEvaluationScenario,
    approval_expires_at: datetime | None = None,
) -> CandidateLifecycleRecord:
    now = datetime.now(timezone.utc)
    return CandidateLifecycleRecord(
        owner_subject_id="user:alice",
        approved_at=now - timedelta(minutes=5),
        approval_expires_at=approval_expires_at or (now + timedelta(minutes=10)),
        invalidated_at=None,
        source=_candidate_source(scenario),
    )


def test_mssql_evaluation_fixtures_are_source_bound_and_reconstructable() -> None:
    scenarios = list_mssql_evaluation_scenarios()
    scenario_ids = {scenario.scenario_id for scenario in scenarios}
    scenario_identities = {scenario.identity for scenario in scenarios}

    assert len(scenarios) == len(scenario_ids)
    assert len(scenarios) == len(scenario_identities)
    assert {"positive", "safety", "regression"} <= {
        scenario.kind for scenario in scenarios
    }

    for scenario in scenarios:
        assert scenario.identity == (scenario.source.source_id, scenario.scenario_id)
        assert scenario.source.source_id
        assert scenario.source.source_family == "mssql"
        assert scenario.source.source_flavor
        assert scenario.source.dialect_profile
        assert scenario.source.dataset_contract_version > 0
        assert scenario.source.schema_snapshot_version > 0
        assert scenario.source.execution_policy_version > 0
        assert scenario.expected.decision in {"allow", "reject"}
        if scenario.expected.decision == "reject":
            assert scenario.expected.primary_code


def test_mssql_evaluation_fixture_listing_returns_defensive_copies() -> None:
    first_read = list_mssql_evaluation_scenarios()
    assert first_read, "Expected at least one MSSQL evaluation scenario"
    mutated_scenario = first_read[0]
    original_scenario_id = mutated_scenario.scenario_id
    original_source_id = mutated_scenario.source.source_id

    mutated_scenario.scenario_id = "mutated-scenario-id"
    mutated_scenario.source.source_id = "mutated-source-id"

    second_read = list_mssql_evaluation_scenarios()
    fresh_scenario = second_read[0]

    assert fresh_scenario is not mutated_scenario
    assert fresh_scenario.source is not mutated_scenario.source
    assert fresh_scenario.scenario_id == original_scenario_id
    assert fresh_scenario.source.source_id == original_source_id


def test_postgresql_evaluation_fixtures_are_source_bound_and_reconstructable() -> None:
    scenarios = list_postgresql_evaluation_scenarios()
    scenario_ids = {scenario.scenario_id for scenario in scenarios}
    scenario_identities = {scenario.identity for scenario in scenarios}

    assert len(scenarios) == len(scenario_ids)
    assert len(scenarios) == len(scenario_identities)
    assert {"positive", "safety"} <= {scenario.kind for scenario in scenarios}

    for scenario in scenarios:
        assert scenario.identity == (scenario.source.source_id, scenario.scenario_id)
        assert scenario.source.source_id
        assert scenario.source.source_family == "postgresql"
        assert scenario.source.source_flavor
        assert scenario.source.dialect_profile
        assert scenario.source.dataset_contract_version > 0
        assert scenario.source.schema_snapshot_version > 0
        assert scenario.source.execution_policy_version > 0
        assert scenario.expected.decision in {"allow", "reject"}
        if scenario.expected.decision == "reject":
            assert scenario.expected.primary_code


def test_postgresql_evaluation_fixture_listing_returns_defensive_copies() -> None:
    first_read = list_postgresql_evaluation_scenarios()
    assert first_read, "Expected at least one PostgreSQL evaluation scenario"
    mutated_scenario = first_read[0]
    original_scenario_id = mutated_scenario.scenario_id
    original_source_id = mutated_scenario.source.source_id

    mutated_scenario.scenario_id = "mutated-scenario-id"
    mutated_scenario.source.source_id = "mutated-source-id"

    second_read = list_postgresql_evaluation_scenarios()
    fresh_scenario = second_read[0]

    assert fresh_scenario is not mutated_scenario
    assert fresh_scenario.source is not mutated_scenario.source
    assert fresh_scenario.scenario_id == original_scenario_id
    assert fresh_scenario.source.source_id == original_source_id


@pytest.mark.parametrize(
    "scenario_id",
    (
        "mssql-positive-approved-vendor-spend-top-vendors",
        "mssql-positive-approved-vendor-count-by-region",
    ),
)
def test_mssql_positive_evaluation_scenarios_allow_and_shape_execution_evidence(
    scenario_id: str,
) -> None:
    scenario = _mssql_scenarios_by_id()[scenario_id]
    guard_result = evaluate_mssql_sql_guard(
        {
            "canonical_sql": scenario.canonical_sql,
            "source": {
                "source_id": scenario.source.source_id,
                "source_family": scenario.source.source_family,
                "source_flavor": scenario.source.source_flavor,
            },
        }
    )
    assert guard_result.decision == "allow"

    selection = select_execution_connector(candidate_source=_candidate_source(scenario))
    captured: dict[str, object] = {}

    def fake_query_runner(
        *,
        connection_string: str,
        canonical_sql: str,
    ) -> list[dict[str, object]]:
        del connection_string
        captured["canonical_sql"] = canonical_sql
        row_shape = scenario.expected.execution_evidence.row_shape
        return [{column_name: f"{column_name}-value" for column_name in row_shape}]

    result = execute_candidate_sql(
        candidate=ExecutableCandidateRecord(
            canonical_sql=scenario.canonical_sql,
            source=_candidate_source(scenario),
        ),
        selection=selection,
        business_mssql_connection_string=MSSQL_TEST_CONNECTION_STRING,
        query_runner=fake_query_runner,
    )

    evidence = scenario.expected.execution_evidence
    assert captured["canonical_sql"] == scenario.expected.canonical_sql
    assert result.source_id == scenario.source.source_id
    assert result.connector_id == evidence.connector_id
    assert result.ownership == evidence.ownership
    assert tuple(result.rows[0]) == evidence.row_shape


@pytest.mark.parametrize(
    "scenario_id",
    (
        "postgresql-positive-approved-vendor-spend-top-vendors",
        "postgresql-positive-approved-vendor-count-by-region",
    ),
)
def test_postgresql_positive_evaluation_scenarios_allow_and_shape_execution_evidence(
    scenario_id: str,
) -> None:
    scenario = _postgresql_scenarios_by_id()[scenario_id]
    guard_result = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": scenario.canonical_sql,
            "source": {
                "source_id": scenario.source.source_id,
                "source_family": scenario.source.source_family,
                "source_flavor": scenario.source.source_flavor,
            },
        }
    )
    assert guard_result.decision == "allow"

    selection = select_execution_connector(candidate_source=_candidate_source(scenario))
    captured: dict[str, object] = {}

    def fake_query_runner(
        *,
        database_url: str,
        canonical_sql: str,
    ) -> list[dict[str, object]]:
        captured["database_url"] = database_url
        captured["canonical_sql"] = canonical_sql
        row_shape = scenario.expected.execution_evidence.row_shape
        return [{column_name: f"{column_name}-value" for column_name in row_shape}]

    result = execute_candidate_sql(
        candidate=ExecutableCandidateRecord(
            canonical_sql=scenario.canonical_sql,
            source=_candidate_source(scenario),
        ),
        selection=selection,
        business_postgres_url=POSTGRESQL_TEST_URL,
        application_postgres_url=APPLICATION_POSTGRESQL_TEST_URL,
        query_runner=fake_query_runner,
    )

    evidence = scenario.expected.execution_evidence
    assert captured["database_url"] == POSTGRESQL_TEST_URL
    assert captured["canonical_sql"] == scenario.expected.canonical_sql
    assert result.source_id == scenario.source.source_id
    assert result.connector_id == evidence.connector_id
    assert result.ownership == evidence.ownership
    assert tuple(result.rows[0]) == evidence.row_shape


@pytest.mark.parametrize(
    "scenario_id",
    (
        "mssql-safety-guard-denies-waitfor-delay",
        "mssql-regression-linked-server-denied",
    ),
)
def test_mssql_guard_safety_scenarios_deny_with_expected_codes(
    scenario_id: str,
) -> None:
    scenario = _mssql_scenarios_by_id()[scenario_id]

    result = evaluate_mssql_sql_guard(
        {
            "canonical_sql": scenario.canonical_sql,
            "source": {
                "source_id": scenario.source.source_id,
                "source_family": scenario.source.source_family,
                "source_flavor": scenario.source.source_flavor,
            },
        }
    )

    assert result.decision == "reject"
    assert result.rejections[0].code == scenario.expected.primary_code


def test_mssql_safety_wrong_source_binding_denies_at_execution_boundary() -> None:
    scenario = _mssql_scenarios_by_id()["mssql-safety-wrong-source-binding-denied"]

    with pytest.raises(ExecutionConnectorExecutionError) as exc_info:
        execute_candidate_sql(
            candidate=ExecutableCandidateRecord(
                canonical_sql=scenario.canonical_sql,
                source=_candidate_source(scenario),
            ),
            selection=ExecutionConnectorSelection(
                source_id="business-postgres-source",
                source_family="postgresql",
                source_flavor="warehouse",
                connector_id="postgresql_readonly",
                ownership="backend",
            ),
            business_mssql_connection_string=MSSQL_TEST_CONNECTION_STRING,
        )

    assert scenario.expected.primary_code == DENY_SOURCE_BINDING_MISMATCH
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_mssql_safety_unsupported_source_binding_denies_at_selection_boundary() -> None:
    scenario = _mssql_scenarios_by_id()["mssql-safety-unsupported-source-binding-denied"]

    with pytest.raises(ExecutionConnectorSelectionError) as exc_info:
        select_execution_connector(candidate_source=_candidate_source(scenario))

    assert scenario.expected.primary_code == DENY_UNSUPPORTED_SOURCE_BINDING
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_mssql_safety_stale_policy_denies_at_lifecycle_boundary() -> None:
    scenario = _mssql_scenarios_by_id()["mssql-safety-stale-policy-denied"]

    with _session_scope() as session:
        _seed_mssql_source(
            session,
            scenario=scenario,
            contract_version=scenario.source.dataset_contract_version + 1,
            snapshot_version=scenario.source.schema_snapshot_version,
        )

        with pytest.raises(CandidateLifecycleRevalidationError) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_lifecycle_candidate(scenario=scenario),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert scenario.expected.primary_code == DENY_POLICY_VERSION_STALE
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_mssql_safety_approval_expiry_denies_at_lifecycle_boundary() -> None:
    scenario = _mssql_scenarios_by_id()["mssql-safety-approval-expiry-denied"]

    with _session_scope() as session:
        _seed_mssql_source(session, scenario=scenario)

        with pytest.raises(CandidateLifecycleRevalidationError) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_lifecycle_candidate(
                    scenario=scenario,
                    approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert scenario.expected.primary_code == DENY_APPROVAL_EXPIRED
    assert exc_info.value.deny_code == scenario.expected.primary_code


@pytest.mark.parametrize(
    "scenario_id",
    (
        "postgresql-safety-guard-denies-system-catalog-access",
    ),
)
def test_postgresql_guard_safety_scenarios_deny_with_expected_codes(
    scenario_id: str,
) -> None:
    scenario = _postgresql_scenarios_by_id()[scenario_id]

    result = evaluate_postgresql_sql_guard(
        {
            "canonical_sql": scenario.canonical_sql,
            "source": {
                "source_id": scenario.source.source_id,
                "source_family": scenario.source.source_family,
                "source_flavor": scenario.source.source_flavor,
            },
        }
    )

    assert result.decision == "reject"
    assert result.rejections[0].code == scenario.expected.primary_code


def test_postgresql_safety_wrong_source_binding_denies_at_execution_boundary() -> None:
    scenario = _postgresql_scenarios_by_id()[
        "postgresql-safety-wrong-source-binding-denied"
    ]

    with pytest.raises(ExecutionConnectorExecutionError) as exc_info:
        execute_candidate_sql(
            candidate=ExecutableCandidateRecord(
                canonical_sql=scenario.canonical_sql,
                source=_candidate_source(scenario),
            ),
            selection=ExecutionConnectorSelection(
                source_id="business-mssql-source",
                source_family="mssql",
                source_flavor="sqlserver",
                connector_id="mssql_readonly",
                ownership="backend",
            ),
            business_postgres_url=POSTGRESQL_TEST_URL,
            application_postgres_url=APPLICATION_POSTGRESQL_TEST_URL,
        )

    assert scenario.expected.primary_code == DENY_SOURCE_BINDING_MISMATCH
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_postgresql_safety_unsupported_source_binding_denies_at_selection_boundary() -> None:
    scenario = _postgresql_scenarios_by_id()[
        "postgresql-safety-unsupported-source-binding-denied"
    ]

    with pytest.raises(ExecutionConnectorSelectionError) as exc_info:
        select_execution_connector(candidate_source=_candidate_source(scenario))

    assert scenario.expected.primary_code == DENY_UNSUPPORTED_SOURCE_BINDING
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_postgresql_safety_application_postgres_exposure_denies_at_selection_boundary() -> None:
    scenario = _postgresql_scenarios_by_id()[
        "postgresql-safety-application-postgres-exposure-denied"
    ]

    with pytest.raises(ExecutionConnectorSelectionError) as exc_info:
        select_execution_connector(candidate_source=_candidate_source(scenario))

    assert scenario.expected.primary_code == DENY_UNSUPPORTED_SOURCE_BINDING
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_postgresql_safety_stale_policy_denies_at_lifecycle_boundary() -> None:
    scenario = _postgresql_scenarios_by_id()["postgresql-safety-stale-policy-denied"]

    with _session_scope() as session:
        _seed_mssql_source(
            session,
            scenario=scenario,
            contract_version=scenario.source.dataset_contract_version + 1,
            snapshot_version=scenario.source.schema_snapshot_version,
        )

        with pytest.raises(CandidateLifecycleRevalidationError) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_lifecycle_candidate(scenario=scenario),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert scenario.expected.primary_code == DENY_POLICY_VERSION_STALE
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_postgresql_safety_approval_expiry_denies_at_lifecycle_boundary() -> None:
    scenario = _postgresql_scenarios_by_id()["postgresql-safety-approval-expiry-denied"]

    with _session_scope() as session:
        _seed_mssql_source(session, scenario=scenario)

        with pytest.raises(CandidateLifecycleRevalidationError) as exc_info:
            revalidate_candidate_lifecycle(
                candidate=_lifecycle_candidate(
                    scenario=scenario,
                    approval_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                ),
                authenticated_subject=AuthenticatedSubject(
                    subject_id="user:alice",
                    governance_bindings=frozenset({"group:finance-analysts"}),
                ),
                session=session,
                as_of=datetime.now(timezone.utc),
            )

    assert scenario.expected.primary_code == DENY_APPROVAL_EXPIRED
    assert exc_info.value.deny_code == scenario.expected.primary_code


def test_postgresql_safety_application_postgres_execution_reuse_denies_before_query() -> None:
    scenario = _postgresql_scenarios_by_id()[
        "postgresql-safety-application-postgres-execution-reuse-denied"
    ]

    def fake_query_runner(*, database_url: str, canonical_sql: str) -> list[dict[str, object]]:
        raise AssertionError("query runner must not run for application PostgreSQL reuse")

    with pytest.raises(ExecutionConnectorExecutionError) as exc_info:
        execute_candidate_sql(
            candidate=ExecutableCandidateRecord(
                canonical_sql=scenario.canonical_sql,
                source=_candidate_source(scenario),
            ),
            selection=select_execution_connector(candidate_source=_candidate_source(scenario)),
            business_postgres_url=APPLICATION_POSTGRESQL_TEST_URL,
            application_postgres_url=APPLICATION_POSTGRESQL_TEST_URL,
            query_runner=fake_query_runner,
        )

    assert scenario.expected.primary_code == DENY_APPLICATION_POSTGRES_REUSE
    assert exc_info.value.deny_code == scenario.expected.primary_code
