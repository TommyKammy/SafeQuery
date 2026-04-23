from __future__ import annotations

from datetime import datetime, timezone
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


def _all_scenarios() -> tuple[Union[MSSQLEvaluationScenario, PostgreSQLEvaluationScenario], ...]:
    return list_mssql_evaluation_scenarios() + list_postgresql_evaluation_scenarios()


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

        artifacts.append(
            {
                "scenario_id": scenario.scenario_id,
                "event": {
                    "event_id": uuid4(),
                    "event_type": event_type,
                    "occurred_at": datetime.now(timezone.utc),
                    "request_id": f"request-{scenario.scenario_id}",
                    "correlation_id": f"correlation-{scenario.scenario_id}",
                    "user_subject": "user:release-gate",
                    "session_id": "session-release-gate",
                    "source_id": scenario.source.source_id,
                    "source_family": scenario.source.source_family,
                    "source_flavor": scenario.source.source_flavor,
                    "dialect_profile_version": scenario.source.dialect_profile_version,
                    "dataset_contract_version": scenario.source.dataset_contract_version,
                    "schema_snapshot_version": scenario.source.schema_snapshot_version,
                    "execution_policy_version": scenario.source.execution_policy_version,
                    "connector_profile_version": scenario.source.connector_profile_version,
                    "primary_deny_code": scenario.expected.primary_code,
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
