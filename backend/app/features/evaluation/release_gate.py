from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Iterable as TypingIterable, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, ValidationError

from app.features.evaluation.comparison import (
    EvaluationComparisonRow,
    EvaluationObservedOutcome,
    EvaluationOutcomeRecord,
    EvaluationOutcomeSnapshot,
    compare_evaluation_outcomes,
)
from app.features.evaluation.harness import (
    MSSQLEvaluationScenario,
    PostgreSQLEvaluationScenario,
    list_mssql_evaluation_scenarios,
    list_postgresql_evaluation_scenarios,
)


ReleaseGateStatus = Literal["pass", "fail"]
ScenarioArtifact = Union[MSSQLEvaluationScenario, PostgreSQLEvaluationScenario]

_SOURCE_REQUIRED_FIELDS = {
    "source.source_id",
    "source.source_family",
    "source.source_flavor",
    "source.dialect_profile",
    "source.dataset_contract_version",
    "source.schema_snapshot_version",
    "source.execution_policy_version",
}


class ReleaseGateFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deny_code: str
    source_id: Optional[str] = None
    source_family: Optional[str] = None
    scenario_id: Optional[str] = None
    scenario_category: Optional[str] = None
    detail: str


class ReleaseGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReleaseGateStatus
    evaluated_scenario_count: int
    failure_count: int
    failures: tuple[ReleaseGateFailure, ...]


def reconstruct_release_gate(
    *,
    observed_artifacts: TypingIterable[Union[EvaluationOutcomeRecord, Mapping[str, Any]]],
) -> ReleaseGateDecision:
    normalized_records: list[EvaluationOutcomeRecord] = []
    failures: list[ReleaseGateFailure] = []

    for artifact in observed_artifacts:
        if isinstance(artifact, EvaluationOutcomeRecord):
            normalized_records.append(artifact)
            continue

        try:
            normalized_records.append(EvaluationOutcomeRecord.model_validate(artifact))
        except ValidationError as exc:
            failures.append(_validation_failure_for(artifact=artifact, error=exc))

    if failures:
        return ReleaseGateDecision(
            status="fail",
            evaluated_scenario_count=len(normalized_records),
            failure_count=len(failures),
            failures=tuple(failures),
        )

    comparison = compare_evaluation_outcomes(
        baseline=_baseline_records_from_harness(),
        candidate=tuple(normalized_records),
    )
    failures = [failure for row in comparison for failure in _failures_for_row(row)]

    return ReleaseGateDecision(
        status="pass" if not failures else "fail",
        evaluated_scenario_count=len(comparison),
        failure_count=len(failures),
        failures=tuple(failures),
    )


def _baseline_records_from_harness() -> tuple[EvaluationOutcomeRecord, ...]:
    return tuple(
        _record_from_scenario(scenario)
        for scenario in (
            list_mssql_evaluation_scenarios() + list_postgresql_evaluation_scenarios()
        )
    )


def _record_from_scenario(scenario: ScenarioArtifact) -> EvaluationOutcomeRecord:
    return EvaluationOutcomeRecord(
        scenario_id=scenario.scenario_id,
        kind=scenario.kind,
        source=EvaluationOutcomeSnapshot.model_validate(scenario.source.model_dump()),
        outcome=EvaluationObservedOutcome(
            decision=scenario.expected.decision,
            primary_code=scenario.expected.primary_code,
        ),
    )


def _validation_failure_for(
    *,
    artifact: Any,
    error: ValidationError,
) -> ReleaseGateFailure:
    errors = error.errors()
    error_paths = {
        ".".join(str(part) for part in validation_error["loc"])
        for validation_error in errors
    }
    artifact_map = artifact if isinstance(artifact, Mapping) else {}
    source = artifact_map.get("source")
    source_id = source.get("source_id") if isinstance(source, Mapping) else None
    source_family = source.get("source_family") if isinstance(source, Mapping) else None
    deny_code = (
        "DENY_MISSING_SOURCE_AWARE_AUDIT_FIELDS"
        if error_paths & _SOURCE_REQUIRED_FIELDS
        else "DENY_MALFORMED_EVALUATION_ARTIFACT"
    )

    return ReleaseGateFailure(
        deny_code=deny_code,
        source_id=source_id if isinstance(source_id, str) else None,
        source_family=source_family if isinstance(source_family, str) else None,
        scenario_id=_string_or_none(artifact_map.get("scenario_id")),
        scenario_category=_string_or_none(artifact_map.get("kind")),
        detail="; ".join(
            f"{_error_location(validation_error['loc'])}: {validation_error['msg']}"
            for validation_error in errors
        ),
    )


def _failures_for_row(row: EvaluationComparisonRow) -> tuple[ReleaseGateFailure, ...]:
    if row.status == "pass":
        return ()

    if "missing_candidate" in row.regressions:
        return (
            ReleaseGateFailure(
                deny_code="DENY_MISSING_EVALUATION_COVERAGE",
                source_id=row.key.source_id,
                source_family=row.key.source_family,
                scenario_id=row.key.scenario_id,
                scenario_category=row.kind,
                detail="Missing authoritative evaluation outcome for required scenario.",
            ),
        )

    if row.status == "regression":
        deny_code = (
            "DENY_SAFETY_SCENARIO_REGRESSION"
            if row.kind in {"safety", "regression"}
            else "DENY_EVALUATION_REGRESSION"
        )
        detail = _regression_detail(row)
        return (
            ReleaseGateFailure(
                deny_code=deny_code,
                source_id=row.key.source_id,
                source_family=row.key.source_family,
                scenario_id=row.key.scenario_id,
                scenario_category=row.kind,
                detail=detail,
            ),
        )

    return (
        ReleaseGateFailure(
            deny_code="DENY_BASELINE_RECONSTRUCTION_GAP",
            source_id=row.key.source_id,
            source_family=row.key.source_family,
            scenario_id=row.key.scenario_id,
            scenario_category=row.kind,
            detail="Baseline reconstruction was incomplete for a required scenario.",
        ),
    )


def _regression_detail(row: EvaluationComparisonRow) -> str:
    if "decision" in row.regressions or "primary_code" in row.regressions:
        baseline_outcome = row.baseline.outcome if row.baseline is not None else None
        candidate_outcome = row.candidate.outcome if row.candidate is not None else None
        expected_decision = baseline_outcome.decision if baseline_outcome is not None else None
        observed_decision = candidate_outcome.decision if candidate_outcome is not None else None
        expected_code = baseline_outcome.primary_code if baseline_outcome is not None else None
        observed_code = candidate_outcome.primary_code if candidate_outcome is not None else None
        return (
            "Observed decision does not match the authoritative scenario expectation: "
            f"expected decision={expected_decision!r}, observed decision={observed_decision!r}, "
            f"expected deny code={expected_code!r}, observed deny code={observed_code!r}."
        )

    return (
        "Observed source profile does not match the authoritative scenario metadata: "
        f"{', '.join(row.regressions)}."
    )


def _string_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _error_location(location: tuple[Any, ...]) -> str:
    if not location:
        return "<root>"
    return ".".join(str(part) for part in location)
