from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal, Mapping, Optional, Sequence

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
GovernedAnswerSemanticContractVersion = Literal["governed_answer_assurance.v1"]
GovernedAnswerUnsupportedClaimCategory = Literal[
    "expected_columns_mismatch",
    "row_count_mismatch",
    "truncation_mismatch",
    "forbidden_answer_claim",
    "unsupported_result_value",
]

_RESULT_VALUE_PATTERN = re.compile(
    r"\bFY\d{4}-Q[1-4]\b|\b(?:\d{1,3}(?:,\d{3})+|\d+\.\d+)\b",
    re.IGNORECASE,
)
_FORBIDDEN_ACTION_PREFIXES = (
    "answer from ",
    "silently drop ",
    "silently expand ",
    "include ",
    "report ",
    "subtract ",
    "label ",
    "infer ",
    "fabricate ",
    "assume ",
    "ignore ",
    "choose ",
    "merge ",
    "collapse ",
    "claim ",
    "provide ",
    "execute ",
    "cite ",
    "say ",
    "produce ",
    "expose ",
    "return ",
)
_NEGATED_CLAIM_CONTEXTS = (
    "not ",
    "no ",
    "never ",
    "cannot ",
    "can't ",
    "didn't ",
    "doesn't ",
    "won't ",
    "did not ",
    "does not ",
    "do not ",
    "will not ",
    "was not ",
    "were not ",
    "is not ",
    "are not ",
)


class GovernedAnswerSourceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: NonEmptyString
    source_family: NonEmptyString
    source_flavor: Optional[NonEmptyString] = None
    dialect_profile: NonEmptyString
    dialect_profile_version: PositiveInt
    connector_profile_version: PositiveInt
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: PositiveInt


class GovernedAnswerFixtureMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: NonEmptyString
    source_id: NonEmptyString
    schema_snapshot_version: PositiveInt
    semantic_contract_version: GovernedAnswerSemanticContractVersion


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
    semantic_contract_version: GovernedAnswerSemanticContractVersion
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


class GovernedAnswerConsistencyScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    score: float
    unsupported_claim_categories: tuple[GovernedAnswerUnsupportedClaimCategory, ...]
    unsupported_claims: tuple[NonEmptyString, ...] = Field(default_factory=tuple)


def validate_governed_answer_fixture_set(
    fixture_set: dict[str, Any],
) -> GovernedAnswerFixtureSet:
    return GovernedAnswerFixtureSet.model_validate(fixture_set)


def score_governed_answer_consistency(
    *,
    fixture: GovernedAnswerFixture,
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
    result_metadata: Mapping[str, Any],
) -> GovernedAnswerConsistencyScore:
    """Score whether an answer only claims facts present in the result evidence."""

    categories: list[GovernedAnswerUnsupportedClaimCategory] = []
    unsupported_claims: list[str] = []
    expected_result_shape = fixture.expected_result_shape

    _check_expected_columns(
        expected_result_shape=expected_result_shape,
        result_rows=result_rows,
        result_metadata=result_metadata,
        categories=categories,
        unsupported_claims=unsupported_claims,
    )
    _check_row_count_and_truncation(
        expected_result_shape=expected_result_shape,
        result_rows=result_rows,
        result_metadata=result_metadata,
        categories=categories,
        unsupported_claims=unsupported_claims,
    )
    _check_forbidden_answer_claims(
        fixture=fixture,
        answer_text=answer_text,
        categories=categories,
        unsupported_claims=unsupported_claims,
    )
    _check_deterministic_result_values(
        answer_text=answer_text,
        result_rows=result_rows,
        categories=categories,
        unsupported_claims=unsupported_claims,
    )

    unsupported_claim_categories = tuple(dict.fromkeys(categories))
    passed = not unsupported_claim_categories
    return GovernedAnswerConsistencyScore(
        passed=passed,
        score=1.0 if passed else 0.0,
        unsupported_claim_categories=unsupported_claim_categories,
        unsupported_claims=tuple(dict.fromkeys(unsupported_claims)),
    )


def _check_expected_columns(
    *,
    expected_result_shape: Mapping[str, Any],
    result_rows: Sequence[Mapping[str, Any]],
    result_metadata: Mapping[str, Any],
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    expected_columns = tuple(expected_result_shape.get("columns") or ())
    if not expected_columns:
        return

    observed_columns = _observed_result_columns(
        result_metadata=result_metadata,
        result_rows=result_rows,
    )
    if observed_columns != expected_columns:
        categories.append("expected_columns_mismatch")
        unsupported_claims.append(
            f"expected columns {expected_columns}; observed columns {observed_columns}"
        )


def _check_row_count_and_truncation(
    *,
    expected_result_shape: Mapping[str, Any],
    result_rows: Sequence[Mapping[str, Any]],
    result_metadata: Mapping[str, Any],
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    known_rows = expected_result_shape.get("known_result_rows")
    expected_row_count = len(known_rows) if isinstance(known_rows, list) else None
    observed_row_count = result_metadata.get("row_count", len(result_rows))
    if expected_row_count is not None and observed_row_count != expected_row_count:
        categories.append("row_count_mismatch")
        unsupported_claims.append(
            f"expected row count {expected_row_count}; observed row count {observed_row_count}"
        )

    if (
        result_metadata.get("truncated") is True
        or result_metadata.get("is_truncated") is True
        or result_metadata.get("result_truncated") is True
    ):
        categories.append("truncation_mismatch")
        unsupported_claims.append("result metadata reports truncated output")


def _check_forbidden_answer_claims(
    *,
    fixture: GovernedAnswerFixture,
    answer_text: str,
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    normalized_answer = answer_text.casefold()
    for forbidden_claim in fixture.forbidden_answer_claims:
        for claim_subject in _forbidden_claim_subjects(forbidden_claim):
            if (
                claim_subject in normalized_answer
                and not _claim_subject_is_negated(normalized_answer, claim_subject)
            ):
                categories.append("forbidden_answer_claim")
                unsupported_claims.append(claim_subject)
                break


def _check_deterministic_result_values(
    *,
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    supported_values = _supported_result_values(result_rows)
    for claim_value in _claimed_result_values(answer_text):
        if _value_forms(claim_value).isdisjoint(supported_values):
            categories.append("unsupported_result_value")
            unsupported_claims.append(claim_value)


def _observed_result_columns(
    *,
    result_metadata: Mapping[str, Any],
    result_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    metadata_columns = result_metadata.get("columns")
    if isinstance(metadata_columns, Sequence) and not isinstance(
        metadata_columns, str
    ):
        observed_columns = tuple(str(column) for column in metadata_columns)
        if observed_columns:
            return observed_columns

    return tuple(
        dict.fromkeys(str(column) for row in result_rows for column in row.keys())
    )


def _forbidden_claim_subjects(forbidden_claim: str) -> tuple[str, ...]:
    normalized = _clean_claim_text(forbidden_claim.casefold())
    if not normalized.startswith("do not "):
        return ()

    action = _clean_claim_text(normalized.removeprefix("do not "))
    subjects: list[str] = [action]
    for prefix in _FORBIDDEN_ACTION_PREFIXES:
        if action.startswith(prefix):
            subjects.append(action.removeprefix(prefix))
            break

    expanded_subjects: list[str] = []
    for subject in subjects:
        expanded_subjects.extend(_split_forbidden_subject(subject))

    return tuple(
        dict.fromkeys(subject for subject in expanded_subjects if len(subject) >= 3)
    )


def _clean_claim_text(text: str) -> str:
    return text.strip().rstrip(".").strip()


def _split_forbidden_subject(subject: str) -> tuple[str, ...]:
    variants = [subject]
    for separator in (" unless ", " without ", " to keep ", " under "):
        if separator in subject:
            variants.append(subject.split(separator, 1)[0])

    split_variants: list[str] = []
    for variant in variants:
        split_variants.append(variant)
        if " as " in variant:
            split_variants.append(variant.split(" as ", 1)[0])
        if " or claim " in variant:
            before, after = variant.split(" or claim ", 1)
            split_variants.extend((before, after))

    return tuple(_clean_claim_text(variant) for variant in split_variants)


def _claim_subject_is_negated(normalized_answer: str, claim_subject: str) -> bool:
    start = normalized_answer.find(claim_subject)
    while start >= 0:
        context = normalized_answer[max(0, start - 48) : start]
        sentence_start = max(context.rfind("."), context.rfind("?"), context.rfind("!"))
        if sentence_start >= 0:
            context = context[sentence_start + 1 :]
        if not any(
            negated_context in context for negated_context in _NEGATED_CLAIM_CONTEXTS
        ):
            return False
        start = normalized_answer.find(claim_subject, start + len(claim_subject))
    return True


def _claimed_result_values(answer_text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _RESULT_VALUE_PATTERN.finditer(answer_text))


def _supported_result_values(result_rows: Sequence[Mapping[str, Any]]) -> set[str]:
    supported: set[str] = set()
    for row in result_rows:
        for value in row.values():
            supported.update(_value_forms(value))
    return supported


def _value_forms(value: Any) -> set[str]:
    text = str(value).strip()
    uncomma_text = text.replace(",", "")
    forms = {text, text.casefold(), uncomma_text, uncomma_text.casefold()}
    try:
        normalized_decimal = Decimal(uncomma_text).normalize()
    except (InvalidOperation, ValueError):
        return forms
    forms.add(format(normalized_decimal, "f"))
    if normalized_decimal == normalized_decimal.to_integral():
        forms.add(str(int(normalized_decimal)))
    return forms
