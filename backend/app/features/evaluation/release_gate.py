from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Iterable as TypingIterable, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.features.audit.event_model import SourceAwareAuditEvent
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
AuditEvidenceStatus = Literal["matched", "missing", "stale", "not_evaluated"]
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


class ReleaseGateAuditArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: Optional[str] = None
    event: SourceAwareAuditEvent

    @model_validator(mode="before")
    @classmethod
    def _hydrate_scenario_id_from_event_metadata(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value

        top_level_scenario_id = value.get("scenario_id")
        event = value.get("event")
        release_gate_scenario: Any = None
        if isinstance(event, SourceAwareAuditEvent):
            release_gate_scenario = event.release_gate_scenario
        elif isinstance(event, Mapping):
            release_gate_scenario = event.get("release_gate_scenario")

        if isinstance(release_gate_scenario, Mapping):
            embedded_scenario_id = release_gate_scenario.get("scenario_id")
        else:
            embedded_scenario_id = getattr(
                release_gate_scenario,
                "scenario_id",
                None,
            )

        if not isinstance(embedded_scenario_id, str) or not embedded_scenario_id.strip():
            return value

        if isinstance(top_level_scenario_id, str) and top_level_scenario_id.strip():
            if top_level_scenario_id != embedded_scenario_id:
                return value
            return value
        if top_level_scenario_id is not None and not isinstance(top_level_scenario_id, str):
            return value

        return {**value, "scenario_id": embedded_scenario_id}

    @model_validator(mode="after")
    def _require_scenario_id_except_raw_generation_failure(
        self,
    ) -> "ReleaseGateAuditArtifact":
        if self.scenario_id is not None:
            return self
        if (
            self.event.event_type == "generation_failed"
            and self.event.release_gate_scenario is None
        ):
            return self
        raise ValueError(
            "scenario_id is required unless a raw generation_failed audit event "
            "omits release_gate_scenario by design."
        )


class ReleaseGateDiffScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: Optional[str] = None
    source_id: Optional[str] = None
    source_family: Optional[str] = None
    scenario_category: Optional[str] = None
    expected_decision: Optional[Literal["allow", "reject"]] = None
    actual_decision: Optional[Literal["allow", "reject"]] = None
    audit_evidence_status: AuditEvidenceStatus
    changed_fields: tuple[str, ...] = ()
    deny_codes: tuple[str, ...]
    detail: str


class ReleaseGateDiffArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_version: Literal["release_gate_v2_evaluation_diff"] = (
        "release_gate_v2_evaluation_diff"
    )
    status: ReleaseGateStatus
    failure_count: int
    scenarios: tuple[ReleaseGateDiffScenario, ...]


class ReleaseGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReleaseGateStatus
    evaluated_scenario_count: int
    failure_count: int
    failures: tuple[ReleaseGateFailure, ...]
    diff_artifact: ReleaseGateDiffArtifact


def reconstruct_release_gate(
    *,
    observed_artifacts: TypingIterable[Union[EvaluationOutcomeRecord, Mapping[str, Any]]],
    audit_artifacts: TypingIterable[Union[ReleaseGateAuditArtifact, Mapping[str, Any]]] = (),
) -> ReleaseGateDecision:
    normalized_records: list[EvaluationOutcomeRecord] = []
    normalized_audit_artifacts: list[ReleaseGateAuditArtifact] = []
    failures: list[ReleaseGateFailure] = []

    for artifact in observed_artifacts:
        if isinstance(artifact, EvaluationOutcomeRecord):
            normalized_records.append(artifact)
            continue

        try:
            normalized_records.append(EvaluationOutcomeRecord.model_validate(artifact))
        except ValidationError as exc:
            failures.append(_validation_failure_for(artifact=artifact, error=exc))

    for artifact in audit_artifacts:
        if isinstance(artifact, ReleaseGateAuditArtifact):
            normalized_audit_artifacts.append(artifact)
            continue

        try:
            normalized_audit_artifacts.append(ReleaseGateAuditArtifact.model_validate(artifact))
        except ValidationError as exc:
            failures.append(_audit_validation_failure_for(artifact=artifact, error=exc))

    if failures:
        return _decision(
            status="fail",
            evaluated_scenario_count=len(normalized_records),
            failures=tuple(failures),
            diff_scenarios=_diff_scenarios_for_validation_failures(failures),
        )

    comparison = compare_evaluation_outcomes(
        baseline=_baseline_records_from_harness(),
        candidate=tuple(normalized_records),
    )
    row_failures = [
        failure for row in comparison for failure in _failures_for_row(row)
    ]
    audit_results = [
        (
            scenario,
            _audit_failures_for_scenario(
                scenario=scenario,
                audit_artifacts=tuple(normalized_audit_artifacts),
            ),
        )
        for scenario in (
            list_mssql_evaluation_scenarios() + list_postgresql_evaluation_scenarios()
        )
    ]
    audit_failures = [
        failure for _, failure in audit_results if failure is not None
    ]
    failures = [*row_failures, *audit_failures]
    audit_status_by_identity = {
        (scenario.source.source_id, scenario.scenario_id): _audit_status_for_failure(
            audit_failure
        )
        for scenario, audit_failure in audit_results
    }

    return _decision(
        status="pass" if not failures else "fail",
        evaluated_scenario_count=len(comparison),
        failures=tuple(failures),
        diff_scenarios=_diff_scenarios_from_comparison(
            comparison=comparison,
            failures=tuple(failures),
            audit_status_by_identity=audit_status_by_identity,
        ),
    )


def _decision(
    *,
    status: ReleaseGateStatus,
    evaluated_scenario_count: int,
    failures: tuple[ReleaseGateFailure, ...],
    diff_scenarios: tuple[ReleaseGateDiffScenario, ...],
) -> ReleaseGateDecision:
    return ReleaseGateDecision(
        status=status,
        evaluated_scenario_count=evaluated_scenario_count,
        failure_count=len(failures),
        failures=failures,
        diff_artifact=ReleaseGateDiffArtifact(
            status=status,
            failure_count=len(failures),
            scenarios=diff_scenarios,
        ),
    )


def _diff_scenarios_for_validation_failures(
    failures: list[ReleaseGateFailure],
) -> tuple[ReleaseGateDiffScenario, ...]:
    return tuple(
        ReleaseGateDiffScenario(
            scenario_id=failure.scenario_id,
            source_id=failure.source_id,
            source_family=failure.source_family,
            scenario_category=failure.scenario_category,
            audit_evidence_status="not_evaluated",
            deny_codes=(failure.deny_code,),
            detail=failure.detail,
        )
        for failure in sorted(
            failures,
            key=lambda failure: (
                failure.source_family or "",
                failure.source_id or "",
                failure.scenario_id or "",
                failure.deny_code,
            ),
        )
    )


def _diff_scenarios_from_comparison(
    *,
    comparison: tuple[EvaluationComparisonRow, ...],
    failures: tuple[ReleaseGateFailure, ...],
    audit_status_by_identity: dict[tuple[str, str], AuditEvidenceStatus],
) -> tuple[ReleaseGateDiffScenario, ...]:
    if not failures:
        return ()

    row_by_identity = {
        (row.key.source_id, row.key.scenario_id): row for row in comparison
    }
    grouped_failures: dict[tuple[str, str], list[ReleaseGateFailure]] = {}
    fallback_failures: list[ReleaseGateFailure] = []
    for failure in failures:
        if failure.source_id is None or failure.scenario_id is None:
            fallback_failures.append(failure)
            continue
        grouped_failures.setdefault(
            (failure.source_id, failure.scenario_id),
            [],
        ).append(failure)

    diff_scenarios = [
        _diff_scenario_from_group(
            identity=identity,
            row=row_by_identity.get(identity),
            failures=tuple(group),
            audit_status=audit_status_by_identity.get(identity, "not_evaluated"),
        )
        for identity, group in grouped_failures.items()
    ]
    diff_scenarios.extend(
        ReleaseGateDiffScenario(
            scenario_id=failure.scenario_id,
            source_id=failure.source_id,
            source_family=failure.source_family,
            scenario_category=failure.scenario_category,
            audit_evidence_status="not_evaluated",
            deny_codes=(failure.deny_code,),
            detail=failure.detail,
        )
        for failure in fallback_failures
    )
    return tuple(
        sorted(
            diff_scenarios,
            key=lambda scenario: (
                scenario.source_family or "",
                scenario.source_id or "",
                scenario.scenario_id or "",
                scenario.deny_codes,
            ),
        )
    )


def _diff_scenario_from_group(
    *,
    identity: tuple[str, str],
    row: EvaluationComparisonRow | None,
    failures: tuple[ReleaseGateFailure, ...],
    audit_status: AuditEvidenceStatus,
) -> ReleaseGateDiffScenario:
    first_failure = failures[0]
    baseline_outcome = row.baseline.outcome if row is not None and row.baseline else None
    candidate_outcome = row.candidate.outcome if row is not None and row.candidate else None
    changed_fields = row.regressions if row is not None and row.status == "regression" else ()

    return ReleaseGateDiffScenario(
        scenario_id=identity[1],
        source_id=identity[0],
        source_family=first_failure.source_family,
        scenario_category=first_failure.scenario_category,
        expected_decision=(
            baseline_outcome.decision if baseline_outcome is not None else None
        ),
        actual_decision=(
            candidate_outcome.decision if candidate_outcome is not None else None
        ),
        audit_evidence_status=audit_status,
        changed_fields=changed_fields,
        deny_codes=tuple(failure.deny_code for failure in failures),
        detail=" | ".join(failure.detail for failure in failures),
    )


def _audit_status_for_failure(
    failure: ReleaseGateFailure | None,
) -> AuditEvidenceStatus:
    if failure is None:
        return "matched"
    if failure.deny_code == "DENY_MISSING_AUDIT_COVERAGE":
        return "missing"
    return "stale"


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
            outcome_category=scenario.expected.outcome_category,
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


def _audit_validation_failure_for(
    *,
    artifact: Any,
    error: ValidationError,
) -> ReleaseGateFailure:
    errors = error.errors()
    artifact_map = artifact if isinstance(artifact, Mapping) else {}
    event = artifact_map.get("event")
    event_map = event if isinstance(event, Mapping) else {}
    source_id = event_map.get("source_id")
    source_family = event_map.get("source_family")

    return ReleaseGateFailure(
        deny_code="DENY_MALFORMED_AUDIT_ARTIFACT",
        source_id=source_id if isinstance(source_id, str) else None,
        source_family=source_family if isinstance(source_family, str) else None,
        scenario_id=_string_or_none(artifact_map.get("scenario_id")),
        scenario_category=None,
        detail="; ".join(
            f"{_error_location(validation_error['loc'])}: {validation_error['msg']}"
            for validation_error in errors
        ),
    )


def _audit_failures_for_scenario(
    *,
    scenario: ScenarioArtifact,
    audit_artifacts: tuple[ReleaseGateAuditArtifact, ...],
) -> ReleaseGateFailure | None:
    candidates = [
        artifact.event
        for artifact in audit_artifacts
        if _audit_artifact_can_cover_scenario(artifact=artifact, scenario=scenario)
    ]
    if not candidates:
        return ReleaseGateFailure(
            deny_code="DENY_MISSING_AUDIT_COVERAGE",
            source_id=scenario.source.source_id,
            source_family=scenario.source.source_family,
            scenario_id=scenario.scenario_id,
            scenario_category=scenario.kind,
            detail="Missing authoritative source-aware audit artifact for required scenario.",
        )

    expected_event_type = _expected_audit_event_type_for(scenario)
    expected_primary_code = scenario.expected.primary_code
    for event in candidates:
        mismatches = _audit_mismatches_for_scenario(
            scenario=scenario,
            event=event,
            expected_event_type=expected_event_type,
            expected_primary_code=expected_primary_code,
        )
        if not mismatches:
            return None

    return ReleaseGateFailure(
        deny_code="DENY_STALE_AUDIT_COVERAGE",
        source_id=scenario.source.source_id,
        source_family=scenario.source.source_family,
        scenario_id=scenario.scenario_id,
        scenario_category=scenario.kind,
        detail=(
            "No authoritative audit artifact matched the required source-aware "
            f"scenario evidence: {', '.join(mismatches)}."
        ),
    )


def _expected_audit_event_type_for(scenario: ScenarioArtifact) -> str:
    if scenario.evaluation_boundary == "generation":
        return "generation_failed"
    if scenario.evaluation_boundary == "guard":
        return "guard_evaluated"
    if scenario.evaluation_boundary == "runtime":
        return "execution_failed"
    if scenario.expected.decision == "allow":
        return "execution_completed"
    return "execution_denied"


def _audit_mismatches_for_scenario(
    *,
    scenario: ScenarioArtifact,
    event: SourceAwareAuditEvent,
    expected_event_type: str,
    expected_primary_code: str | None,
) -> tuple[str, ...]:
    mismatches: list[str] = []
    release_gate_scenario = event.release_gate_scenario
    if expected_event_type == "generation_failed":
        release_gate_scenario_required = False
    else:
        release_gate_scenario_required = True

    if release_gate_scenario is None and release_gate_scenario_required:
        mismatches.append("release_gate_scenario")
    elif release_gate_scenario is not None:
        expected_guard_decision = (
            scenario.expected.decision
            if scenario.evaluation_boundary == "guard"
            else "allow"
        )
        scenario_expected_values = {
            "release_gate_scenario.scenario_id": scenario.scenario_id,
            "release_gate_scenario.source_id": scenario.source.source_id,
            "release_gate_scenario.guard_decision": expected_guard_decision,
        }
        mismatches.extend(
            field
            for field, expected in scenario_expected_values.items()
            if getattr(
                release_gate_scenario,
                field.removeprefix("release_gate_scenario."),
            )
            != expected
        )
        if event.query_candidate_id is None:
            mismatches.append("query_candidate_id")
        elif release_gate_scenario.candidate_id != event.query_candidate_id:
            mismatches.append("release_gate_scenario.candidate_id")
        if (
            expected_event_type == "guard_evaluated"
            and release_gate_scenario.guard_audit_event_id != event.event_id
        ):
            mismatches.append("release_gate_scenario.guard_audit_event_id")
        if expected_event_type in {"execution_completed", "execution_denied"}:
            if release_gate_scenario.execution_audit_event_id != event.event_id:
                mismatches.append("release_gate_scenario.execution_audit_event_id")

    expected_values = {
        "event_type": expected_event_type,
        "source_id": scenario.source.source_id,
        "source_family": scenario.source.source_family,
        "source_flavor": scenario.source.source_flavor,
        "dialect_profile_version": scenario.source.dialect_profile_version,
        "dataset_contract_version": scenario.source.dataset_contract_version,
        "schema_snapshot_version": scenario.source.schema_snapshot_version,
        "execution_policy_version": scenario.source.execution_policy_version,
        "connector_profile_version": scenario.source.connector_profile_version,
        "primary_deny_code": expected_primary_code,
    }
    mismatches.extend(
        field
        for field, expected in expected_values.items()
        if getattr(event, field) != expected
    )
    return tuple(mismatches)


def _audit_artifact_can_cover_scenario(
    *,
    artifact: ReleaseGateAuditArtifact,
    scenario: ScenarioArtifact,
) -> bool:
    if artifact.scenario_id == scenario.scenario_id:
        return True
    if artifact.scenario_id is not None:
        return False
    event = artifact.event
    return (
        scenario.evaluation_boundary == "generation"
        and event.event_type == "generation_failed"
        and event.release_gate_scenario is None
        and _raw_generation_audit_identity_is_unique(scenario)
        and event.source_id == scenario.source.source_id
        and event.source_family == scenario.source.source_family
        and event.primary_deny_code == scenario.expected.primary_code
    )


def _raw_generation_audit_identity_is_unique(scenario: ScenarioArtifact) -> bool:
    identity = (
        scenario.source.source_id,
        scenario.source.source_family,
        scenario.expected.primary_code,
    )
    matching_scenario_count = sum(
        1
        for candidate in (
            list_mssql_evaluation_scenarios() + list_postgresql_evaluation_scenarios()
        )
        if candidate.evaluation_boundary == "generation"
        and (
            candidate.source.source_id,
            candidate.source.source_family,
            candidate.expected.primary_code,
        )
        == identity
    )
    return matching_scenario_count == 1


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
    if set(row.regressions) == {"outcome_category"}:
        baseline_outcome = row.baseline.outcome if row.baseline is not None else None
        candidate_outcome = row.candidate.outcome if row.candidate is not None else None
        expected_category = (
            baseline_outcome.outcome_category if baseline_outcome is not None else None
        )
        observed_category = (
            candidate_outcome.outcome_category if candidate_outcome is not None else None
        )
        return (
            "Observed outcome category does not match the authoritative scenario "
            "expectation while decision and deny code remained stable: "
            f"expected outcome category={expected_category!r}, "
            f"observed outcome category={observed_category!r}."
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
