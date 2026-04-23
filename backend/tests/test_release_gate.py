from __future__ import annotations

from typing import Union

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


def test_release_gate_passes_when_authoritative_records_match_harness() -> None:
    decision = reconstruct_release_gate(observed_artifacts=_observed_records_from_harness())

    assert decision.status == "pass"
    assert decision.failure_count == 0
    assert decision.failures == ()


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

    decision = reconstruct_release_gate(observed_artifacts=tuple(mutated_records))

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

    decision = reconstruct_release_gate(observed_artifacts=observed_records)

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

    decision = reconstruct_release_gate(observed_artifacts=observed_artifacts)

    assert decision.status == "fail"
    assert decision.failure_count == 1
    assert decision.failures[0].deny_code == "DENY_MISSING_SOURCE_AWARE_AUDIT_FIELDS"
    assert decision.failures[0].source_id == "business-mssql-source"
    assert decision.failures[0].source_family is None
    assert decision.failures[0].scenario_category == "positive"
