from __future__ import annotations

from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.features.evaluation.harness import (
    MSSQLEvaluationScenario,
    PostgreSQLEvaluationScenario,
    list_mssql_evaluation_scenarios,
    list_postgresql_evaluation_scenarios,
)


ScenarioArtifact = Union[MSSQLEvaluationScenario, PostgreSQLEvaluationScenario]


class ReleaseGateScenarioMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    source_id: str
    candidate_id: str
    guard_decision: Literal["allow", "reject"]
    guard_audit_event_id: UUID
    execution_run_id: Optional[UUID] = None
    execution_audit_event_id: Optional[UUID] = None


def build_release_gate_scenario_metadata(
    *,
    source_id: str,
    source_family: str,
    source_flavor: str | None,
    dataset_contract_version: int | None,
    schema_snapshot_version: int | None,
    execution_policy_version: int | None,
    connector_profile_version: int | None,
    canonical_sql: str,
    candidate_id: str | None,
    guard_decision: Literal["allow", "reject"] | None,
    guard_audit_event_id: UUID | None,
    execution_run_id: UUID | None = None,
    execution_audit_event_id: UUID | None = None,
) -> ReleaseGateScenarioMetadata | None:
    if candidate_id is None or guard_decision is None or guard_audit_event_id is None:
        return None

    scenario = _find_authoritative_scenario(
        source_id=source_id,
        source_family=source_family,
        source_flavor=source_flavor,
        dataset_contract_version=dataset_contract_version,
        schema_snapshot_version=schema_snapshot_version,
        execution_policy_version=execution_policy_version,
        connector_profile_version=connector_profile_version,
        canonical_sql=canonical_sql,
        guard_decision=guard_decision,
    )
    if scenario is None:
        return None

    return ReleaseGateScenarioMetadata(
        scenario_id=scenario.scenario_id,
        source_id=scenario.source.source_id,
        candidate_id=candidate_id,
        guard_decision=guard_decision,
        guard_audit_event_id=guard_audit_event_id,
        execution_run_id=execution_run_id,
        execution_audit_event_id=execution_audit_event_id,
    )


def _find_authoritative_scenario(
    *,
    source_id: str,
    source_family: str,
    source_flavor: str | None,
    dataset_contract_version: int | None,
    schema_snapshot_version: int | None,
    execution_policy_version: int | None,
    connector_profile_version: int | None,
    canonical_sql: str,
    guard_decision: Literal["allow", "reject"],
) -> ScenarioArtifact | None:
    normalized_sql = " ".join(canonical_sql.split())
    for scenario in (
        list_mssql_evaluation_scenarios() + list_postgresql_evaluation_scenarios()
    ):
        source = scenario.source
        if (
            source.source_id == source_id
            and source.source_family == source_family
            and source.source_flavor == source_flavor
            and source.dataset_contract_version == dataset_contract_version
            and source.schema_snapshot_version == schema_snapshot_version
            and source.execution_policy_version == execution_policy_version
            and (
                connector_profile_version is None
                or source.connector_profile_version == connector_profile_version
            )
            and " ".join(scenario.canonical_sql.split()) == normalized_sql
            and scenario.expected.decision == guard_decision
        ):
            return scenario
    return None
