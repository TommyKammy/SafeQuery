from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
    model_validator,
)


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

ReviewLLMCalibrationCategory = Literal[
    "false_approval",
    "false_denial",
    "ambiguity",
    "source_confusion",
]
ReviewLLMCalibrationStatus = Literal["ready", "needs_clarification", "blocked"]
ReviewLLMCalibrationFormatStatus = Literal["review_llm_calibration.v1"]


class ReviewLLMCalibrationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operator_request: NonEmptyString
    source_context: NonEmptyString
    candidate_summary: NonEmptyString
    critique_output: dict[str, Any]


class ReviewLLMCalibrationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: NonEmptyString
    category: ReviewLLMCalibrationCategory
    title: NonEmptyString
    expected_review_status: ReviewLLMCalibrationStatus
    expected_failure_signal: NonEmptyString
    evidence: ReviewLLMCalibrationEvidence
    reviewer_rationale: NonEmptyString

    @model_validator(mode="after")
    def _validate_category_status_pair(self) -> "ReviewLLMCalibrationFixture":
        expected_status_by_category: dict[ReviewLLMCalibrationCategory, str] = {
            "false_approval": "blocked",
            "false_denial": "ready",
            "ambiguity": "needs_clarification",
            "source_confusion": "blocked",
        }
        expected_status = expected_status_by_category[self.category]
        if self.expected_review_status != expected_status:
            raise ValueError(
                "Calibration fixture category and expected review status disagree."
            )
        return self


class ReviewLLMCalibrationFixtureSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_set: NonEmptyString
    purpose: NonEmptyString
    format_status: ReviewLLMCalibrationFormatStatus
    release_gate_authority: bool
    authority_note: NonEmptyString
    malformed_output_handling: Literal["excluded_parser_contract"]
    fixtures: tuple[ReviewLLMCalibrationFixture, ...]

    @model_validator(mode="after")
    def _validate_fixture_set_contract(self) -> "ReviewLLMCalibrationFixtureSet":
        if self.release_gate_authority is not False:
            raise ValueError(
                "Review LLM calibration fixtures must not grant release-gate authority."
            )
        if "does not make Review LLM release-gate authority" not in self.authority_note:
            raise ValueError(
                "Authority note must state that calibration does not make Review LLM "
                "release-gate authority."
            )
        if not self.fixtures:
            raise ValueError("Calibration fixture set must include fixtures.")

        scenario_ids = [fixture.scenario_id for fixture in self.fixtures]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("Calibration fixture scenario ids must be unique.")

        categories = {fixture.category for fixture in self.fixtures}
        required_categories: set[ReviewLLMCalibrationCategory] = {
            "false_approval",
            "false_denial",
            "ambiguity",
            "source_confusion",
        }
        if not required_categories.issubset(categories):
            raise ValueError(
                "Calibration fixtures must include false approval, false denial, "
                "ambiguity, and source confusion cases."
            )

        return self


class ReviewLLMCalibrationCategoryReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_count: PositiveInt
    scenario_ids: tuple[NonEmptyString, ...]
    expected_review_statuses: tuple[ReviewLLMCalibrationStatus, ...]
    expected_failure_signals: tuple[NonEmptyString, ...]


class ReviewLLMCalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_set: NonEmptyString
    fixture_count: PositiveInt
    release_gate_authority: bool
    authority_statement: NonEmptyString
    malformed_output_handling: Literal["excluded_parser_contract"]
    failure_categories: dict[
        ReviewLLMCalibrationCategory,
        ReviewLLMCalibrationCategoryReport,
    ]


def validate_review_llm_calibration_fixture_set(
    fixture_set: dict[str, Any],
) -> ReviewLLMCalibrationFixtureSet:
    return ReviewLLMCalibrationFixtureSet.model_validate(fixture_set)


def build_review_llm_calibration_report(
    fixture_set: ReviewLLMCalibrationFixtureSet,
) -> ReviewLLMCalibrationReport:
    category_reports: dict[
        ReviewLLMCalibrationCategory,
        ReviewLLMCalibrationCategoryReport,
    ] = {}
    for category in (
        "false_approval",
        "false_denial",
        "ambiguity",
        "source_confusion",
    ):
        fixtures = [
            fixture
            for fixture in fixture_set.fixtures
            if fixture.category == category
        ]
        category_reports[category] = ReviewLLMCalibrationCategoryReport(
            fixture_count=len(fixtures),
            scenario_ids=tuple(fixture.scenario_id for fixture in fixtures),
            expected_review_statuses=tuple(
                dict.fromkeys(fixture.expected_review_status for fixture in fixtures)
            ),
            expected_failure_signals=tuple(
                dict.fromkeys(fixture.expected_failure_signal for fixture in fixtures)
            ),
        )

    return ReviewLLMCalibrationReport(
        fixture_set=fixture_set.fixture_set,
        fixture_count=len(fixture_set.fixtures),
        release_gate_authority=fixture_set.release_gate_authority,
        authority_statement=fixture_set.authority_note,
        malformed_output_handling=fixture_set.malformed_output_handling,
        failure_categories=category_reports,
    )
