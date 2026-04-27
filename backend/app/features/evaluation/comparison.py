from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, PositiveInt, model_validator

from app.features.evaluation.harness import (
    EvaluationOutcomeCategory,
    EvaluationScenarioKind,
    EvaluationSourceProfile,
)


ComparisonStatus = Literal["pass", "fail", "regression"]


class EvaluationOutcomeSnapshot(EvaluationSourceProfile):
    model_config = ConfigDict(extra="forbid")


class EvaluationObservedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "reject"]
    outcome_category: EvaluationOutcomeCategory
    primary_code: Optional[str] = None

    @model_validator(mode="after")
    def _validate_primary_code(self) -> "EvaluationObservedOutcome":
        if self.decision == "reject" and (
            self.primary_code is None or not self.primary_code.strip()
        ):
            raise ValueError("Reject outcomes must include a machine-readable primary code.")
        if self.decision == "allow" and self.primary_code is not None:
            raise ValueError("Allow outcomes must not include a primary deny code.")
        return self


class EvaluationOutcomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    kind: EvaluationScenarioKind
    source: EvaluationOutcomeSnapshot
    outcome: EvaluationObservedOutcome

    @property
    def comparison_identity(self) -> tuple[str, str]:
        return (self.source.source_id, self.scenario_id)


class EvaluationComparisonKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    source_id: str
    source_family: str
    source_flavor: str
    dialect_profile: str
    dialect_profile_version: Optional[PositiveInt] = None
    connector_profile_version: Optional[PositiveInt] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: PositiveInt


class EvaluationComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: EvaluationComparisonKey
    kind: EvaluationScenarioKind
    status: ComparisonStatus
    baseline: Optional[EvaluationOutcomeRecord] = None
    candidate: Optional[EvaluationOutcomeRecord] = None
    regressions: tuple[str, ...] = ()


def compare_evaluation_outcomes(
    *,
    baseline: tuple[EvaluationOutcomeRecord, ...],
    candidate: tuple[EvaluationOutcomeRecord, ...],
) -> tuple[EvaluationComparisonRow, ...]:
    baseline_index = _index_outcomes_by_identity(baseline, side="baseline")
    candidate_index = _index_outcomes_by_identity(candidate, side="candidate")
    identities = sorted(set(baseline_index) | set(candidate_index))

    return tuple(
        _build_comparison_row(
            baseline=baseline_index.get(identity),
            candidate=candidate_index.get(identity),
        )
        for identity in identities
    )


def _index_outcomes_by_identity(
    records: tuple[EvaluationOutcomeRecord, ...],
    *,
    side: str,
) -> dict[tuple[str, str], EvaluationOutcomeRecord]:
    index: dict[tuple[str, str], EvaluationOutcomeRecord] = {}
    for record in records:
        identity = record.comparison_identity
        if identity in index:
            raise ValueError(f"Duplicate {side} evaluation outcome identity: {identity!r}")
        index[identity] = record
    return index


def _build_comparison_row(
    *,
    baseline: Optional[EvaluationOutcomeRecord],
    candidate: Optional[EvaluationOutcomeRecord],
) -> EvaluationComparisonRow:
    anchor = candidate or baseline
    assert anchor is not None

    if baseline is None or candidate is None:
        return EvaluationComparisonRow(
            key=_comparison_key_for(anchor),
            kind=anchor.kind,
            status="fail",
            baseline=baseline,
            candidate=candidate,
            regressions=("missing_candidate" if candidate is None else "missing_baseline",),
        )

    regressions = _collect_regressions(baseline=baseline, candidate=candidate)
    status: ComparisonStatus = "pass" if not regressions else "regression"
    return EvaluationComparisonRow(
        key=_comparison_key_for(candidate),
        kind=candidate.kind,
        status=status,
        baseline=baseline,
        candidate=candidate,
        regressions=tuple(regressions),
    )


def _comparison_key_for(record: EvaluationOutcomeRecord) -> EvaluationComparisonKey:
    source = record.source
    return EvaluationComparisonKey(
        scenario_id=record.scenario_id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dialect_profile=source.dialect_profile,
        dialect_profile_version=source.dialect_profile_version,
        connector_profile_version=source.connector_profile_version,
        dataset_contract_version=source.dataset_contract_version,
        schema_snapshot_version=source.schema_snapshot_version,
        execution_policy_version=source.execution_policy_version,
    )


def _collect_regressions(
    *,
    baseline: EvaluationOutcomeRecord,
    candidate: EvaluationOutcomeRecord,
) -> list[str]:
    regressions: list[str] = []
    source_fields = (
        "source_family",
        "source_flavor",
        "dialect_profile",
        "dialect_profile_version",
        "connector_profile_version",
        "dataset_contract_version",
        "schema_snapshot_version",
        "execution_policy_version",
    )

    if baseline.kind != candidate.kind:
        regressions.append("kind")
    for field_name in source_fields:
        if getattr(baseline.source, field_name) != getattr(candidate.source, field_name):
            regressions.append(field_name)
    if baseline.outcome.decision != candidate.outcome.decision:
        regressions.append("decision")
    if baseline.outcome.outcome_category != candidate.outcome.outcome_category:
        regressions.append("outcome_category")
    if baseline.outcome.primary_code != candidate.outcome.primary_code:
        regressions.append("primary_code")

    return regressions
