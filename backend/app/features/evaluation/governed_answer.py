from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
    model_validator,
)


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

GovernedAnswerCaseType = Literal[
    "positive",
    "ambiguous",
    "unsafe",
    "unsupported_answer",
]
GovernedAnswerCorrectnessLevel = Literal[
    "exact_result_required",
    "semantic_result_required",
    "ambiguity_clarification_required",
    "deny_required",
]
GovernedAnswerFailureMode = Literal[
    "clarification_required",
    "guard_denial_required",
    "unsupported_answer_denial_required",
]


class GovernedAnswerSourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: NonEmptyString
    source_family: NonEmptyString
    source_flavor: Optional[NonEmptyString] = None
    dialect_profile: NonEmptyString
    dialect_profile_version: Optional[PositiveInt] = None
    connector_profile_version: Optional[PositiveInt] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: PositiveInt


class GovernedAnswerFixtureMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: NonEmptyString
    source_id: NonEmptyString
    schema_snapshot_version: PositiveInt
    semantic_contract_version: NonEmptyString


class GovernedAnswerSourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    source_id: NonEmptyString
    schema_name: Optional[NonEmptyString] = Field(default=None, alias="schema")
    table: Optional[NonEmptyString] = None
    dataset: Optional[NonEmptyString] = None


class GovernedAnswerSemanticMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: NonEmptyString
    dimensions: tuple[NonEmptyString, ...] = Field(default_factory=tuple)
    filters: tuple[NonEmptyString, ...] = Field(default_factory=tuple)


class GovernedAnswerFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: GovernedAnswerFixtureMetadata
    question: NonEmptyString
    case_type: GovernedAnswerCaseType
    source_binding: GovernedAnswerSourceBinding
    expected_intent: NonEmptyString
    expected_semantic_mapping: GovernedAnswerSemanticMapping
    acceptable_sql_shape: dict[str, Any]
    expected_result_shape: dict[str, Any]
    forbidden_answer_claims: tuple[NonEmptyString, ...]
    expected_correctness_level: GovernedAnswerCorrectnessLevel
    expected_failure_mode: Optional[GovernedAnswerFailureMode] = None
    human_authoring_minutes: PositiveInt
    domain_expert_review_required: bool

    @model_validator(mode="after")
    def _validate_case_failure_contract(self) -> "GovernedAnswerFixture":
        if not self.acceptable_sql_shape:
            raise ValueError("Fixtures must define acceptable SQL shape constraints.")
        if not self.expected_result_shape:
            raise ValueError("Fixtures must define expected result shape constraints.")
        if not self.forbidden_answer_claims:
            raise ValueError("Fixtures must define forbidden answer claims.")

        if self.case_type == "positive":
            if self.expected_failure_mode is not None:
                raise ValueError("Positive fixtures must not define an expected failure mode.")
            if self.expected_correctness_level not in {
                "exact_result_required",
                "semantic_result_required",
            }:
                raise ValueError("Positive fixtures must require exact or semantic results.")
            if self.acceptable_sql_shape.get("must_not_execute") is True:
                raise ValueError("Positive fixtures must remain executable.")
            return self

        if self.expected_failure_mode is None:
            raise ValueError(
                "Non-positive fixtures must define an expected failure mode."
            )

        expected_levels = {
            "ambiguous": "ambiguity_clarification_required",
            "unsafe": "deny_required",
            "unsupported_answer": "deny_required",
        }
        if self.expected_correctness_level != expected_levels[self.case_type]:
            raise ValueError("Case type and correctness level disagree.")

        expected_modes = {
            "ambiguous": "clarification_required",
            "unsafe": "guard_denial_required",
            "unsupported_answer": "unsupported_answer_denial_required",
        }
        if self.expected_failure_mode != expected_modes[self.case_type]:
            raise ValueError("Case type and expected failure mode disagree.")

        if self.acceptable_sql_shape.get("must_not_execute") is not True:
            raise ValueError("Non-positive fixtures must fail closed before execution.")

        return self


class GovernedAnswerAuthoringSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_count: PositiveInt
    estimated_authoring_minutes: PositiveInt
    estimated_review_minutes: PositiveInt
    domain_expert_review_fixture_ids: tuple[NonEmptyString, ...] = Field(
        default_factory=tuple
    )
    review_notes: tuple[NonEmptyString, ...] = Field(default_factory=tuple)


class GovernedAnswerFixtureSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_set: NonEmptyString
    domain: NonEmptyString
    purpose: NonEmptyString
    format_status: Literal["governed_answer_assurance.v1"]
    semantic_contract_version: NonEmptyString
    source_profile: GovernedAnswerSourceProfile
    schema_assumptions: dict[str, Any]
    authoring_summary: GovernedAnswerAuthoringSummary
    fixtures: tuple[GovernedAnswerFixture, ...]

    @model_validator(mode="after")
    def _validate_fixture_set_consistency(self) -> "GovernedAnswerFixtureSet":
        if not self.fixtures:
            raise ValueError("Fixture set must include at least one fixture.")
        if self.authoring_summary.fixture_count != len(self.fixtures):
            raise ValueError("Authoring summary fixture count must match fixtures.")

        scenario_ids = [fixture.metadata.scenario_id for fixture in self.fixtures]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("Fixture scenario ids must be unique.")

        case_types = {fixture.case_type for fixture in self.fixtures}
        required_case_types = {
            "positive",
            "ambiguous",
            "unsafe",
            "unsupported_answer",
        }
        if not required_case_types.issubset(case_types):
            raise ValueError(
                "Fixture set must cover positive, ambiguous, unsafe, "
                "and unsupported-answer cases."
            )

        total_authoring_minutes = 0
        for fixture in self.fixtures:
            metadata = fixture.metadata
            if metadata.source_id != self.source_profile.source_id:
                raise ValueError("Fixture metadata source id must match source profile.")
            if (
                metadata.schema_snapshot_version
                != self.source_profile.schema_snapshot_version
            ):
                raise ValueError(
                    "Fixture metadata schema snapshot version must match source profile."
                )
            if metadata.semantic_contract_version != self.semantic_contract_version:
                raise ValueError(
                    "Fixture metadata semantic contract version must match fixture set."
                )
            if fixture.source_binding.source_id != self.source_profile.source_id:
                raise ValueError("Fixture source binding must match source profile.")
            total_authoring_minutes += fixture.human_authoring_minutes

        if self.authoring_summary.estimated_authoring_minutes != total_authoring_minutes:
            raise ValueError("Authoring summary minutes must equal fixture minutes.")

        return self


def validate_governed_answer_fixture_set(
    fixture_set: dict[str, Any],
) -> GovernedAnswerFixtureSet:
    return GovernedAnswerFixtureSet.model_validate(fixture_set)
