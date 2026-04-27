from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from uuid import uuid4

from app.features.evaluation import (
    EvaluationOutcomeRecord,
    reconstruct_release_gate,
)
from app.features.evaluation.harness import (
    MSSQLEvaluationScenario,
    PostgreSQLEvaluationScenario,
    list_mssql_evaluation_scenarios,
    list_postgresql_evaluation_scenarios,
)
from app.features.evaluation.scenario_metadata import (
    build_release_gate_scenario_metadata,
)
from app.features.mlflow_export import build_mlflow_export_from_evaluation_scenario


def _all_scenarios() -> tuple[Union[MSSQLEvaluationScenario, PostgreSQLEvaluationScenario], ...]:
    return list_mssql_evaluation_scenarios() + list_postgresql_evaluation_scenarios()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_backend_runtime_image_packages_mssql_odbc_runtime() -> None:
    dockerfile = (_repo_root() / "backend" / "Dockerfile").read_text()
    pyproject = (_repo_root() / "backend" / "pyproject.toml").read_text()

    assert "msodbcsql18" in dockerfile
    assert "ACCEPT_EULA=Y" in dockerfile
    assert "unixodbc" in dockerfile
    assert "pyodbc" in pyproject


def _observed_records_from_harness() -> tuple[EvaluationOutcomeRecord, ...]:
    return tuple(
        EvaluationOutcomeRecord(
            scenario_id=scenario.scenario_id,
            kind=scenario.kind,
            source=scenario.source.model_dump(),
            outcome={
                "decision": scenario.expected.decision,
                "primary_code": scenario.expected.primary_code,
            },
        )
        for scenario in _all_scenarios()
    )


def _audit_artifacts_from_harness() -> tuple[dict[str, object], ...]:
    artifacts: list[dict[str, object]] = []
    for scenario in _all_scenarios():
        if scenario.evaluation_boundary == "guard":
            event_type = "guard_evaluated"
        elif scenario.expected.decision == "allow":
            event_type = "execution_completed"
        else:
            event_type = "execution_denied"

        event_id = uuid4()
        guard_audit_event_id = event_id if event_type == "guard_evaluated" else uuid4()
        candidate_id = f"candidate-{scenario.scenario_id}"
        release_gate_scenario = {
            "scenario_id": scenario.scenario_id,
            "source_id": scenario.source.source_id,
            "candidate_id": candidate_id,
            "guard_decision": scenario.expected.decision,
            "guard_audit_event_id": guard_audit_event_id,
        }
        if event_type in {"execution_completed", "execution_denied"}:
            release_gate_scenario.update(
                {
                    "execution_run_id": event_id,
                    "execution_audit_event_id": event_id,
                }
            )

        artifacts.append(
            {
                "scenario_id": scenario.scenario_id,
                "event": {
                    "event_id": event_id,
                    "event_type": event_type,
                    "occurred_at": datetime.now(timezone.utc),
                    "request_id": f"request-{scenario.scenario_id}",
                    "correlation_id": f"correlation-{scenario.scenario_id}",
                    "user_subject": "user:release-gate",
                    "session_id": "session-release-gate",
                    "query_candidate_id": candidate_id,
                    "source_id": scenario.source.source_id,
                    "source_family": scenario.source.source_family,
                    "source_flavor": scenario.source.source_flavor,
                    "dialect_profile_version": scenario.source.dialect_profile_version,
                    "dataset_contract_version": scenario.source.dataset_contract_version,
                    "schema_snapshot_version": scenario.source.schema_snapshot_version,
                    "execution_policy_version": scenario.source.execution_policy_version,
                    "connector_profile_version": scenario.source.connector_profile_version,
                    "primary_deny_code": scenario.expected.primary_code,
                    "release_gate_scenario": release_gate_scenario,
                },
            }
        )
    return tuple(artifacts)


def test_release_gate_passes_when_authoritative_records_match_harness() -> None:
    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=_audit_artifacts_from_harness(),
    )

    assert decision.status == "pass"
    assert decision.failure_count == 0
    assert decision.failures == ()


def test_release_gate_accepts_scenario_id_from_shared_audit_metadata() -> None:
    scenario = next(
        (
            scenario
            for scenario in list_postgresql_evaluation_scenarios()
            if scenario.evaluation_boundary != "guard"
            and scenario.expected.decision == "allow"
        ),
        None,
    )
    assert scenario is not None
    event_id = uuid4()
    audit_artifact = {
        "event": {
            "event_id": event_id,
            "event_type": "execution_completed",
            "occurred_at": datetime.now(timezone.utc),
            "request_id": f"request-{scenario.scenario_id}",
            "correlation_id": f"correlation-{scenario.scenario_id}",
            "user_subject": "user:release-gate",
            "session_id": "session-release-gate",
            "query_candidate_id": "candidate-release-gate",
            "source_id": scenario.source.source_id,
            "source_family": scenario.source.source_family,
            "source_flavor": scenario.source.source_flavor,
            "dialect_profile_version": scenario.source.dialect_profile_version,
            "dataset_contract_version": scenario.source.dataset_contract_version,
            "schema_snapshot_version": scenario.source.schema_snapshot_version,
            "execution_policy_version": scenario.source.execution_policy_version,
            "connector_profile_version": scenario.source.connector_profile_version,
            "release_gate_scenario": {
                "scenario_id": scenario.scenario_id,
                "source_id": scenario.source.source_id,
                "candidate_id": "candidate-release-gate",
                "guard_decision": "allow",
                "guard_audit_event_id": str(uuid4()),
                "execution_run_id": str(event_id),
                "execution_audit_event_id": str(event_id),
            },
        },
    }

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=(
            audit_artifact,
            *(
                artifact
                for artifact in _audit_artifacts_from_harness()
                if artifact["scenario_id"] != scenario.scenario_id
            ),
        ),
    )

    assert decision.status == "pass"
    assert decision.failure_count == 0


def test_release_gate_fails_closed_for_scenario_id_metadata_mismatch() -> None:
    scenario = next(
        scenario
        for scenario in list_postgresql_evaluation_scenarios()
        if scenario.evaluation_boundary != "guard"
        and scenario.expected.decision == "allow"
    )
    event_id = uuid4()
    audit_artifact = {
        "scenario_id": "postgresql-safety-stale-policy-denied",
        "event": {
            "event_id": event_id,
            "event_type": "execution_completed",
            "occurred_at": datetime.now(timezone.utc),
            "request_id": f"request-{scenario.scenario_id}",
            "correlation_id": f"correlation-{scenario.scenario_id}",
            "user_subject": "user:release-gate",
            "session_id": "session-release-gate",
            "query_candidate_id": "candidate-release-gate",
            "source_id": scenario.source.source_id,
            "source_family": scenario.source.source_family,
            "source_flavor": scenario.source.source_flavor,
            "dialect_profile_version": scenario.source.dialect_profile_version,
            "dataset_contract_version": scenario.source.dataset_contract_version,
            "schema_snapshot_version": scenario.source.schema_snapshot_version,
            "execution_policy_version": scenario.source.execution_policy_version,
            "connector_profile_version": scenario.source.connector_profile_version,
            "release_gate_scenario": {
                "scenario_id": scenario.scenario_id,
                "source_id": scenario.source.source_id,
                "candidate_id": "candidate-release-gate",
                "guard_decision": "allow",
                "guard_audit_event_id": str(uuid4()),
                "execution_run_id": str(event_id),
                "execution_audit_event_id": str(event_id),
            },
        },
    }

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=(
            audit_artifact,
            *(
                artifact
                for artifact in _audit_artifacts_from_harness()
                if artifact["scenario_id"]
                not in {scenario.scenario_id, "postgresql-safety-stale-policy-denied"}
            ),
        ),
    )

    assert decision.status == "fail"
    assert {
        failure.deny_code
        for failure in decision.failures
        if failure.scenario_id
        in {scenario.scenario_id, "postgresql-safety-stale-policy-denied"}
    } == {"DENY_MISSING_AUDIT_COVERAGE", "DENY_STALE_AUDIT_COVERAGE"}


def test_release_gate_scenario_metadata_requires_connector_profile_version() -> None:
    scenario = next(
        scenario
        for scenario in list_postgresql_evaluation_scenarios()
        if scenario.source.connector_profile_version is not None
    )

    metadata = build_release_gate_scenario_metadata(
        source_id=scenario.source.source_id,
        source_family=scenario.source.source_family,
        source_flavor=scenario.source.source_flavor,
        dataset_contract_version=scenario.source.dataset_contract_version,
        schema_snapshot_version=scenario.source.schema_snapshot_version,
        execution_policy_version=scenario.source.execution_policy_version,
        connector_profile_version=None,
        canonical_sql=scenario.canonical_sql,
        candidate_id="candidate-release-gate",
        guard_decision=scenario.expected.decision,
        guard_audit_event_id=uuid4(),
    )

    assert metadata is None


def test_release_gate_fails_closed_when_evaluations_have_no_audit_artifacts() -> None:
    decision = reconstruct_release_gate(observed_artifacts=_observed_records_from_harness())

    assert decision.status == "fail"
    assert decision.failure_count == len(_all_scenarios())
    assert decision.failures[0].deny_code == "DENY_MISSING_AUDIT_COVERAGE"
    assert decision.failures[0].source_id is not None
    assert decision.failures[0].scenario_id is not None


def test_release_gate_reports_missing_audit_coverage_by_source_and_scenario() -> None:
    audit_artifacts = tuple(
        artifact
        for artifact in _audit_artifacts_from_harness()
        if artifact["scenario_id"] != "postgresql-safety-stale-policy-denied"
    )

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=audit_artifacts,
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_MISSING_AUDIT_COVERAGE"
    assert decision.failures[0].source_id == "business-postgres-source"
    assert decision.failures[0].source_family == "postgresql"
    assert decision.failures[0].scenario_id == "postgresql-safety-stale-policy-denied"
    assert decision.failures[0].scenario_category == "safety"


def test_release_gate_reports_stale_audit_coverage_by_source_and_scenario() -> None:
    audit_artifacts = list(_audit_artifacts_from_harness())
    target_index = next(
        index
        for index, artifact in enumerate(audit_artifacts)
        if artifact["scenario_id"] == "mssql-positive-approved-vendor-spend-top-vendors"
    )
    event = dict(audit_artifacts[target_index]["event"])
    event["source_id"] = "business-mssql-legacy-source"
    audit_artifacts[target_index] = {
        **audit_artifacts[target_index],
        "event": event,
    }

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=tuple(audit_artifacts),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_STALE_AUDIT_COVERAGE"
    assert decision.failures[0].source_id == "business-mssql-source"
    assert decision.failures[0].source_family == "mssql"
    assert decision.failures[0].scenario_id == "mssql-positive-approved-vendor-spend-top-vendors"
    assert "source_id" in decision.failures[0].detail


def test_release_gate_fails_closed_when_audit_event_lacks_scenario_metadata() -> None:
    audit_artifacts = list(_audit_artifacts_from_harness())
    target_index = next(
        index
        for index, artifact in enumerate(audit_artifacts)
        if artifact["scenario_id"] == "postgresql-positive-approved-vendor-count-by-region"
    )
    event = dict(audit_artifacts[target_index]["event"])
    event.pop("release_gate_scenario", None)
    audit_artifacts[target_index] = {
        **audit_artifacts[target_index],
        "event": event,
    }

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=tuple(audit_artifacts),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_STALE_AUDIT_COVERAGE"
    assert decision.failures[0].source_id == "business-postgres-source"
    assert decision.failures[0].source_family == "postgresql"
    assert decision.failures[0].scenario_id == "postgresql-positive-approved-vendor-count-by-region"
    assert "release_gate_scenario" in decision.failures[0].detail


def test_release_gate_fails_closed_when_execute_audit_linkage_is_missing() -> None:
    audit_artifacts = list(_audit_artifacts_from_harness())
    target_index = next(
        index
        for index, artifact in enumerate(audit_artifacts)
        if artifact["scenario_id"] == "mssql-positive-approved-vendor-spend-top-vendors"
    )
    event = dict(audit_artifacts[target_index]["event"])
    release_gate_scenario = dict(event["release_gate_scenario"])
    release_gate_scenario.pop("execution_audit_event_id")
    event["release_gate_scenario"] = release_gate_scenario
    audit_artifacts[target_index] = {
        **audit_artifacts[target_index],
        "event": event,
    }

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=tuple(audit_artifacts),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_STALE_AUDIT_COVERAGE"
    assert decision.failures[0].source_id == "business-mssql-source"
    assert decision.failures[0].source_family == "mssql"
    assert decision.failures[0].scenario_id == "mssql-positive-approved-vendor-spend-top-vendors"
    assert "release_gate_scenario.execution_audit_event_id" in decision.failures[0].detail


def test_release_gate_fails_closed_when_query_candidate_linkage_is_missing() -> None:
    audit_artifacts = list(_audit_artifacts_from_harness())
    target_index = next(
        index
        for index, artifact in enumerate(audit_artifacts)
        if artifact["scenario_id"] == "postgresql-positive-approved-vendor-count-by-region"
    )
    event = dict(audit_artifacts[target_index]["event"])
    event.pop("query_candidate_id")
    audit_artifacts[target_index] = {
        **audit_artifacts[target_index],
        "event": event,
    }

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=tuple(audit_artifacts),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_STALE_AUDIT_COVERAGE"
    assert decision.failures[0].source_id == "business-postgres-source"
    assert decision.failures[0].source_family == "postgresql"
    assert decision.failures[0].scenario_id == "postgresql-positive-approved-vendor-count-by-region"
    assert "query_candidate_id" in decision.failures[0].detail


def test_release_gate_accepts_execution_run_id_distinct_from_audit_event_id() -> None:
    audit_artifacts = list(_audit_artifacts_from_harness())
    target_index = next(
        index
        for index, artifact in enumerate(audit_artifacts)
        if artifact["scenario_id"] == "mssql-positive-approved-vendor-spend-top-vendors"
    )
    event = dict(audit_artifacts[target_index]["event"])
    release_gate_scenario = dict(event["release_gate_scenario"])
    release_gate_scenario["execution_run_id"] = str(uuid4())
    event["release_gate_scenario"] = release_gate_scenario
    audit_artifacts[target_index] = {
        **audit_artifacts[target_index],
        "event": event,
    }

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=tuple(audit_artifacts),
    )

    assert decision.status == "pass"
    assert decision.failure_count == 0


def test_release_gate_fails_closed_for_safety_regression() -> None:
    mutated_records = list(_observed_records_from_harness())
    target_index = next(
        index
        for index, record in enumerate(mutated_records)
        if record.scenario_id == "mssql-safety-guard-denies-waitfor-delay"
    )
    target = mutated_records[target_index]
    mutated_records[target_index] = target.model_copy(
        update={
            "outcome": target.outcome.model_copy(
                update={"decision": "allow", "primary_code": None}
            )
        }
    )

    decision = reconstruct_release_gate(
        observed_artifacts=tuple(mutated_records),
        audit_artifacts=_audit_artifacts_from_harness(),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_SAFETY_SCENARIO_REGRESSION"
    assert decision.failures[0].source_id == "business-mssql-source"
    assert decision.failures[0].source_family == "mssql"
    assert decision.failures[0].scenario_category == "safety"


def test_release_gate_fails_closed_for_missing_evaluation_coverage() -> None:
    observed_records = tuple(
        record
        for record in _observed_records_from_harness()
        if record.scenario_id != "postgresql-positive-approved-vendor-count-by-region"
    )

    decision = reconstruct_release_gate(
        observed_artifacts=observed_records,
        audit_artifacts=_audit_artifacts_from_harness(),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_MISSING_EVALUATION_COVERAGE"
    assert decision.failures[0].source_id == "business-postgres-source"
    assert decision.failures[0].source_family == "postgresql"
    assert decision.failures[0].scenario_category == "positive"


def test_release_gate_reports_missing_source_aware_audit_fields() -> None:
    observed_artifacts = (
        {
            "scenario_id": "mssql-positive-approved-vendor-spend-top-vendors",
            "kind": "positive",
            "source": {
                "source_id": "business-mssql-source",
                "source_flavor": "sqlserver",
                "dialect_profile": "mssql.sqlserver.v1",
                "dialect_profile_version": 1,
                "connector_profile_version": 1,
                "dataset_contract_version": 3,
                "schema_snapshot_version": 7,
                "execution_policy_version": 2,
            },
            "outcome": {"decision": "allow"},
        },
    )

    decision = reconstruct_release_gate(
        observed_artifacts=observed_artifacts,
        audit_artifacts=_audit_artifacts_from_harness(),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_MISSING_SOURCE_AWARE_AUDIT_FIELDS"
    assert decision.failures[0].source_id == "business-mssql-source"
    assert decision.failures[0].source_family is None
    assert decision.failures[0].scenario_category == "positive"
    assert "source.source_family" in decision.failures[0].detail


def test_release_gate_reports_structured_failure_for_non_mapping_artifact() -> None:
    decision = reconstruct_release_gate(observed_artifacts=("not-a-mapping",))

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_MALFORMED_EVALUATION_ARTIFACT"
    assert decision.failures[0].source_id is None
    assert decision.failures[0].source_family is None
    assert decision.failures[0].scenario_id is None
    assert decision.failures[0].scenario_category is None
    assert "<root>" in decision.failures[0].detail


def test_release_gate_rejects_mlflow_exports_as_authoritative_evaluation_records() -> None:
    scenario = list_mssql_evaluation_scenarios()[0]
    mlflow_payload = build_mlflow_export_from_evaluation_scenario(
        scenario,
        enabled=True,
        mlflow_run_id="mlflow-run-123",
        evaluation_run_id="evaluation-run-123",
        evaluation_outcome_id="evaluation-outcome-123",
        validation_status="passed",
    )
    assert mlflow_payload is not None

    decision = reconstruct_release_gate(
        observed_artifacts=(mlflow_payload.model_dump(exclude_none=True),),
        audit_artifacts=_audit_artifacts_from_harness(),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_MALFORMED_EVALUATION_ARTIFACT"
    assert decision.failures[0].source_id is None
    assert decision.failures[0].scenario_id is None
    assert "scenario_id" in decision.failures[0].detail
    assert "outcome" in decision.failures[0].detail


def test_release_gate_rejects_mlflow_exports_as_authoritative_audit_artifacts() -> None:
    scenario = list_postgresql_evaluation_scenarios()[0]
    mlflow_payload = build_mlflow_export_from_evaluation_scenario(
        scenario,
        enabled=True,
        mlflow_run_id="mlflow-run-456",
        evaluation_run_id="evaluation-run-123",
        evaluation_outcome_id="evaluation-outcome-456",
        validation_status="passed",
    )
    assert mlflow_payload is not None

    decision = reconstruct_release_gate(
        observed_artifacts=_observed_records_from_harness(),
        audit_artifacts=(mlflow_payload.model_dump(exclude_none=True),),
    )

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_MALFORMED_AUDIT_ARTIFACT"
    assert decision.failures[0].source_id is None
    assert decision.failures[0].scenario_id is None
    assert "scenario_id" in decision.failures[0].detail
    assert "event" in decision.failures[0].detail
