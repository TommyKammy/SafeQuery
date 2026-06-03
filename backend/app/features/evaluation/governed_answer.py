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
ResultValueClaim = tuple[str, int, int]
RowCitationClaim = tuple[str, tuple[ResultValueClaim, ...]]

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
    "missing_citation",
    "row_reference_mismatch",
]

_RESULT_VALUE_PATTERN = re.compile(
    r"\bFY\d{4}-Q[1-4]\b|"
    r"(?<![\w.-])\([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:e[+-]?\d+)?\)(?![\w-])|"
    r"(?<![\w.-])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:e[+-]?\d+)?(?![\w-])",
    re.IGNORECASE,
)
_INCIDENTAL_INTEGER_PREFIX_PATTERN = re.compile(
    r"(?:^|\b)(?:top|rank|first|last)\s+$",
    re.IGNORECASE,
)
_INCIDENTAL_PARENTHESES_YEAR_PREFIX_PATTERN = re.compile(
    r"(?:^|\b)(?:next|last|this|current|prior|previous)\s+year\s*\(?$",
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
    "reveal ",
    "say ",
    "produce ",
    "expose ",
    "return ",
)
_FORBIDDEN_DIRECTIVE_PREFIXES = (
    "do not ",
    "don't ",
    "never ",
    "must not ",
    "must never ",
    "should not ",
    "should never ",
)
_FORBIDDEN_ACTIONLESS_CLAIM_PREFIXES = ("claim ", "label ", "report ", "say ")
_FORBIDDEN_PASSIVE_ACTIONS = {
    "cite ": "cited",
    "execute ": "executed",
    "expose ": "exposed",
    "include ": "included",
    "produce ": "produced",
    "return ": "returned",
    "reveal ": "revealed",
}
_FORBIDDEN_CLAIM_FRAGMENT_PATTERN = re.compile(
    r"\b(?:"
    r"is|are|was|were|be|been|being|has|have|had|"
    r"will|would|can|could|should|must|may|might|"
    r"claim|claims|claimed|report|reports|reported|"
    r"return|returns|returned|reveal|reveals|revealed|"
    r"ignore|ignores|ignored|assume|assumes|assumed|"
    r"expose|exposes|exposed|include|includes|included"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_CLAIM_PATTERN = re.compile(
    r"(?:^|\b)(?:"
    r"not|no|never|cannot|can't|don't|didn't|doesn't|won't|"
    r"unable\s+to|"
    r"did\s+not|does\s+not|do\s+not|will\s+not|"
    r"was\s+not|were\s+not|is\s+not|are\s+not"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_CLAIM_CONTRAST_PATTERN = re.compile(
    r"\b(?:but|however|though|although|except)\b",
    re.IGNORECASE,
)
_FORBIDDEN_SUBJECT_MODIFIER_PATTERN = (
    r"(?:(?:actually|certainly|clearly|definitely|indeed|really|in\s+fact)\s+)?"
)
_CLAIM_VALUE_ROW_LINK_PATTERN = re.compile(
    r"(?:=|:|\b(?:"
    r"is|are|was|were|had|has|at|of|for|"
    r"totaled|totals?|equals?|corresponds?\s+to"
    r")\b)",
    re.IGNORECASE,
)
_CLAIM_VALUE_NEGATED_COPULA_PATTERN = re.compile(
    r"\b(?:is|are|was|were)\s+not\b|\b(?:isn't|aren't|wasn't|weren't)\b",
    re.IGNORECASE,
)
_CLAIM_VALUE_NON_ROW_COMPARISON_PATTERN = re.compile(
    r"\b(?:compared|than|versus|vs\.?)\b|"
    r"\b(?:is|are|was|were)?\s*(?:after|before|follows?|precedes?)\s*$",
    re.IGNORECASE,
)
_ROW_REFERENCE_CITATION_PATTERN = re.compile(r"\[row:(\d+)\]", re.IGNORECASE)
_CLAIM_VALUE_ABBREVIATION_PERIOD_PATTERN = re.compile(
    r"\b(?:approx|est|e\.g|i\.e|etc|vs)\.",
    re.IGNORECASE,
)
_FORBIDDEN_SUBJECT_SEPARATOR_PATTERN = re.compile(r"[\s\-\u2010-\u2015]+")
_FORBIDDEN_SUBJECT_PLURAL_EXACT_TOKENS = {
    "as",
    "does",
    "has",
    "his",
    "is",
    "this",
    "was",
}
_NEGATED_CLAIM_MAX_GAP_WORDS = 8
_TRUNCATION_METADATA_FLAGS = ("truncated", "is_truncated", "result_truncated")
_APOSTROPHE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201b": "'",
        "\uff07": "'",
    }
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
    value_evidence_rows = _deterministic_value_evidence_rows(
        expected_result_shape=expected_result_shape,
        result_rows=result_rows,
    )
    _check_deterministic_result_values(
        answer_text=answer_text,
        result_rows=value_evidence_rows,
        result_metadata=result_metadata,
        categories=categories,
        unsupported_claims=unsupported_claims,
    )
    _check_required_row_citations(
        expected_result_shape=expected_result_shape,
        answer_text=answer_text,
        result_rows=result_rows,
        result_metadata=result_metadata,
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
    observed_row_count = result_metadata.get("row_count")
    if type(observed_row_count) is not int:
        observed_row_count = len(result_rows)
    if expected_row_count is not None and observed_row_count != expected_row_count:
        categories.append("row_count_mismatch")
        unsupported_claims.append(
            f"expected row count {expected_row_count}; observed row count {observed_row_count}"
        )

    if _result_metadata_reports_truncation(result_metadata):
        categories.append("truncation_mismatch")
        unsupported_claims.append("result metadata reports truncated output")


def _check_forbidden_answer_claims(
    *,
    fixture: GovernedAnswerFixture,
    answer_text: str,
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    normalized_answer = _normalize_forbidden_claim_text(answer_text).casefold()
    for forbidden_claim in fixture.forbidden_answer_claims:
        for claim_subject in _forbidden_claim_subjects(forbidden_claim):
            if (
                _claim_subject_appears(normalized_answer, claim_subject)
                and not _claim_subject_is_negated(normalized_answer, claim_subject)
            ):
                categories.append("forbidden_answer_claim")
                unsupported_claims.append(claim_subject)
                break


def _check_deterministic_result_values(
    *,
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
    result_metadata: Mapping[str, Any],
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    if not result_rows:
        for claim_value in _unsupported_no_evidence_result_value_claims(
            answer_text,
            result_metadata,
        ):
            categories.append("unsupported_result_value")
            unsupported_claims.append(claim_value)
        return

    for claim_value in _unsupported_claimed_result_values(
        answer_text,
        result_rows,
        result_metadata,
    ):
        categories.append("unsupported_result_value")
        unsupported_claims.append(claim_value)
    for claim_value in _unsupported_claimed_result_row_combinations(
        answer_text,
        result_rows,
    ):
        categories.append("unsupported_result_value")
        unsupported_claims.append(claim_value)


def _check_required_row_citations(
    *,
    expected_result_shape: Mapping[str, Any],
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
    result_metadata: Mapping[str, Any],
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    citation_requirement = expected_result_shape.get("citation_requirement")
    if not (
        isinstance(citation_requirement, Mapping)
        and citation_requirement.get("required") is True
        and citation_requirement.get("style") == "row_reference"
    ):
        return
    if not (
        result_metadata.get("answer_surface") == "future_llm_summary"
        or result_metadata.get("enforce_citations") is True
    ):
        return
    for claim, claim_values in _required_row_citation_claims(
        answer_text=answer_text,
        result_rows=result_rows,
        result_metadata=result_metadata,
    ):
        _check_required_row_citation_for_claim_values(
            answer_text=answer_text,
            claim_values=claim_values,
            claim=claim,
            result_rows=result_rows,
            categories=categories,
            unsupported_claims=unsupported_claims,
        )


def _required_row_citation_claims(
    *,
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
    result_metadata: Mapping[str, Any],
) -> tuple[RowCitationClaim, ...]:
    claimed_values = _claimed_result_value_matches(answer_text)
    citation_claims: list[RowCitationClaim] = []
    paired_claim_spans: set[tuple[int, int]] = set()
    for left, right in _claimed_result_row_value_pairs(answer_text):
        paired_claim_spans.add((left[1], left[2]))
        paired_claim_spans.add((right[1], right[2]))
        citation_claims.append((f"{left[0]} with {right[0]}", (left, right)))

    for claim_value, start, end in claimed_values:
        if (start, end) in paired_claim_spans:
            continue
        if _metadata_row_count_claim_is_supported(
            answer_text=answer_text,
            claim_value=claim_value,
            start=start,
            end=end,
            result_metadata=result_metadata,
        ):
            continue
        if result_rows and _value_forms(claim_value).isdisjoint(
            _supported_result_values(result_rows)
        ):
            continue
        citation_claims.append((claim_value, ((claim_value, start, end),)))

    return tuple(citation_claims)


def _check_required_row_citation_for_claim_values(
    *,
    answer_text: str,
    claim_values: Sequence[ResultValueClaim],
    claim: str,
    result_rows: Sequence[Mapping[str, Any]],
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    claim_start = min(value[1] for value in claim_values)
    claim_end = max(value[2] for value in claim_values)
    row_citation = _row_reference_citation_for_claim(
        answer_text=answer_text,
        claim_start=claim_start,
        claim_end=claim_end,
    )
    if row_citation is None:
        categories.append("missing_citation")
        unsupported_claims.append(claim)
        return
    row_index = row_citation - 1
    if row_index < 0 or row_index >= len(result_rows):
        categories.append("row_reference_mismatch")
        unsupported_claims.append(f"{claim} cited as row:{row_citation}")
        return
    row_forms = _row_value_forms(result_rows[row_index])
    if any(_value_forms(value[0]).isdisjoint(row_forms) for value in claim_values):
        categories.append("row_reference_mismatch")
        unsupported_claims.append(f"{claim} cited as row:{row_citation}")


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


def _result_metadata_reports_truncation(result_metadata: Mapping[str, Any]) -> bool:
    return any(result_metadata.get(flag) is True for flag in _TRUNCATION_METADATA_FLAGS)


def _deterministic_value_evidence_rows(
    *,
    expected_result_shape: Mapping[str, Any],
    result_rows: Sequence[Mapping[str, Any]],
) -> Sequence[Mapping[str, Any]]:
    if result_rows:
        return result_rows
    known_rows = expected_result_shape.get("known_result_rows")
    if isinstance(known_rows, list) and all(
        isinstance(row, Mapping) for row in known_rows
    ):
        return known_rows
    return ()


def _forbidden_claim_subjects(forbidden_claim: str) -> tuple[str, ...]:
    normalized = _clean_claim_text(
        _normalize_forbidden_claim_text(forbidden_claim).casefold()
    )
    action = _forbidden_claim_action(normalized)
    prefix_subjects: list[str] = []
    passive_subjects: list[str] = []
    action_subjects = _split_forbidden_subject(
        action,
        allow_clause_prefixes=True,
    )
    matched_action_subject = ""
    for prefix in _FORBIDDEN_ACTION_PREFIXES:
        if action.startswith(prefix):
            matched_action_subject = action.removeprefix(prefix)
            prefix_subjects.extend(
                _split_forbidden_subject(
                    matched_action_subject,
                    allow_clause_prefixes=False,
                )
            )
            passive_subjects.extend(
                _passive_forbidden_subjects(
                    action_prefix=prefix,
                    subject=matched_action_subject,
                )
            )
            break

    subjects: list[str] = []
    if matched_action_subject and _has_subject_disjunction(matched_action_subject):
        subjects.extend(prefix_subjects)
        subjects.extend(action_subjects)
    else:
        subjects.extend(action_subjects)
        if matched_action_subject and action.startswith(
            _FORBIDDEN_ACTIONLESS_CLAIM_PREFIXES
        ):
            subjects.extend(prefix_subjects)
    subjects.extend(passive_subjects)

    return tuple(
        dict.fromkeys(subject for subject in subjects if len(subject) >= 3)
    )


def _forbidden_claim_action(normalized_claim: str) -> str:
    for prefix in _FORBIDDEN_DIRECTIVE_PREFIXES:
        if normalized_claim.startswith(prefix):
            return _clean_claim_text(normalized_claim.removeprefix(prefix))
    return normalized_claim


def _clean_claim_text(text: str) -> str:
    return text.strip().rstrip(".").strip()


def _normalize_forbidden_claim_text(text: str) -> str:
    return text.translate(_APOSTROPHE_TRANSLATION)


def _split_forbidden_subject(
    subject: str,
    *,
    allow_clause_prefixes: bool,
) -> tuple[str, ...]:
    variants = [subject]
    if allow_clause_prefixes:
        for separator in (" without ", " to keep ", " under "):
            if separator in subject:
                variants.append(subject.split(separator, 1)[0])

    split_variants: list[str] = []
    for variant in variants:
        split_variants.append(variant)
        if " or claim " in variant:
            before, after = variant.split(" or claim ", 1)
            split_variants.append(before)
            split_variants.append(f"claim {after}")
            split_variants.append(after)
        split_variants.extend(_coordinated_forbidden_action_parts(variant))
        split_variants.extend(_disjunctive_subject_parts(variant))

    return tuple(_clean_claim_text(variant) for variant in split_variants)


def _passive_forbidden_subjects(
    *,
    action_prefix: str,
    subject: str,
) -> tuple[str, ...]:
    passive_action = _FORBIDDEN_PASSIVE_ACTIONS.get(action_prefix)
    if passive_action is None:
        return ()
    return tuple(
        _clean_claim_text(f"{subject} {auxiliary} {passive_action}")
        for auxiliary in ("is", "are", "was", "were", "be", "been", "being")
    )


def _coordinated_forbidden_action_parts(subject: str) -> tuple[str, ...]:
    parts: list[str] = []
    for prefix in _FORBIDDEN_ACTION_PREFIXES:
        marker = f" and {prefix}"
        if marker not in subject:
            continue
        before, after = subject.split(marker, 1)
        if _looks_like_forbidden_claim_fragment(before):
            parts.append(before)
        parts.append(f"{prefix}{after}")
        break
    return tuple(_clean_claim_text(part) for part in parts if _clean_claim_text(part))


def _looks_like_forbidden_claim_fragment(fragment: str) -> bool:
    cleaned = _clean_claim_text(fragment)
    return any(cleaned.startswith(prefix) for prefix in _FORBIDDEN_ACTION_PREFIXES) or (
        len(cleaned.split()) >= 2
        and _FORBIDDEN_CLAIM_FRAGMENT_PATTERN.search(cleaned) is not None
    )


def _disjunctive_subject_parts(subject: str) -> tuple[str, ...]:
    normalized = re.sub(r",\s*or\s+", ", ", subject)
    parts = [
        _clean_claim_text(part)
        for part in re.split(r"\s*,\s*|\s+or\s+", normalized)
        if _clean_claim_text(part)
    ]
    if len(parts) < 2:
        return ()

    suffix = _shared_disjunction_suffix(parts)
    expanded_parts: list[str] = []
    for part in parts:
        if suffix and " " not in part and part != suffix:
            expanded_parts.append(f"{part} {suffix}")
        elif " " in part and not _is_partial_disjunctive_action_part(part, parts):
            expanded_parts.append(part)
    return tuple(expanded_parts)


def _is_partial_disjunctive_action_part(part: str, parts: Sequence[str]) -> bool:
    final_words = parts[-1].split()
    if len(final_words) < 2:
        return False
    suffix = final_words[-1]
    return any(
        part.startswith(prefix)
        and not part.endswith(f" {suffix}")
        for prefix in _FORBIDDEN_ACTION_PREFIXES
    )


def _has_subject_disjunction(subject: str) -> bool:
    return "," in subject or bool(re.search(r"\bor\b", subject))


def _shared_disjunction_suffix(parts: Sequence[str]) -> str | None:
    final_words = parts[-1].split()
    if len(final_words) < 2:
        return None
    suffix = final_words[-1]
    if any(" " in part for part in parts[:-1]):
        return None
    return suffix


def _claim_subject_appears(normalized_answer: str, claim_subject: str) -> bool:
    return _claim_subject_pattern(claim_subject).search(normalized_answer) is not None


def _claim_subject_pattern(claim_subject: str) -> re.Pattern[str]:
    tokens = [
        token
        for token in _FORBIDDEN_SUBJECT_SEPARATOR_PATTERN.split(claim_subject.strip())
        if token
    ]
    if not tokens:
        return re.compile(r"(?!x)x")
    separator = rf"[\s\-\u2010-\u2015]+{_FORBIDDEN_SUBJECT_MODIFIER_PATTERN}"
    subject_pattern = separator.join(
        _forbidden_subject_token_pattern(token) for token in tokens
    )
    return re.compile(rf"(?<!\w){subject_pattern}(?!\w)")


def _forbidden_subject_token_pattern(token: str) -> str:
    escaped_token = re.escape(token)
    if not token.isalpha() or len(token) < 3:
        return escaped_token
    if token in _FORBIDDEN_SUBJECT_PLURAL_EXACT_TOKENS:
        return escaped_token
    if token.endswith("ies") and len(token) > 4:
        return rf"(?:{re.escape(token[:-3])}y|{escaped_token})"
    if token.endswith("s") and len(token) > 3:
        return rf"{re.escape(token[:-1])}s?"
    return rf"{escaped_token}s?"


def _claim_subject_is_negated(normalized_answer: str, claim_subject: str) -> bool:
    starts = [
        match.start()
        for match in _claim_subject_pattern(claim_subject).finditer(normalized_answer)
    ]
    if not starts:
        return False

    for start in starts:
        if _claim_subject_has_following_safety_denial(
            normalized_answer=normalized_answer,
            subject_start=start,
            claim_subject=claim_subject,
        ):
            continue
        context = normalized_answer[max(0, start - 128) : start]
        sentence_start = max(context.rfind("."), context.rfind("?"), context.rfind("!"))
        if sentence_start >= 0:
            context = context[sentence_start + 1 :]
        clause_start = max(context.rfind(";"), context.rfind(":"))
        if clause_start >= 0:
            context = context[clause_start + 1 :]
        if not _negated_claim_context_reaches_subject(context, claim_subject):
            return False
    return True


def _claim_subject_has_following_safety_denial(
    *,
    normalized_answer: str,
    subject_start: int,
    claim_subject: str,
) -> bool:
    subject_match = _claim_subject_pattern(claim_subject).match(
        normalized_answer,
        subject_start,
    )
    if subject_match is None:
        return False
    after_subject = normalized_answer[subject_match.end() : subject_match.end() + 96]
    clause_end_candidates = [
        index
        for index in (after_subject.find("."), after_subject.find(";"))
        if index >= 0
    ]
    if clause_end_candidates:
        after_subject = after_subject[: min(clause_end_candidates)]
    if not _claim_subject_allows_following_safety_denial(claim_subject):
        return False
    if _NEGATED_CLAIM_CONTRAST_PATTERN.search(after_subject):
        return False
    return bool(
        re.search(
            r"\b(?:cannot|can't|will\s+not|must\s+not|should\s+not|do\s+not|don't)"
            r"\s+(?:be\s+)?(?:shared|revealed|exposed|provided|returned|disclosed)\b",
            after_subject,
            re.IGNORECASE,
        )
    )


def _claim_subject_allows_following_safety_denial(claim_subject: str) -> bool:
    return bool(
        re.search(
            r"\b(?:instruction|instructions|sql|dump|row|rows|source|sources|"
            r"record|records|account|identifier|identifiers)\b",
            claim_subject,
            re.IGNORECASE,
        )
    )


def _negated_claim_context_reaches_subject(context: str, claim_subject: str) -> bool:
    negation_matches = tuple(
        match
        for match in _NEGATED_CLAIM_PATTERN.finditer(context)
        if not _is_ignored_negation_match(match, context)
    )
    if not negation_matches:
        return False

    if _has_uncoordinated_double_negation(negation_matches, context):
        return False

    after_negation = context[negation_matches[-1].end() :]
    if _NEGATED_CLAIM_CONTRAST_PATTERN.search(after_negation):
        return False
    if _claim_subject_pattern(claim_subject).search(after_negation):
        return False
    if _has_later_affirmative_forbidden_action(after_negation):
        return False
    if _has_uncoordinated_clause_boundary(after_negation):
        return False
    if "," in after_negation and not re.search(r"\w", after_negation):
        return False

    gap_words = re.findall(r"\b\w+\b", after_negation)
    return len(gap_words) <= _NEGATED_CLAIM_MAX_GAP_WORDS


def _has_uncoordinated_double_negation(
    negation_matches: Sequence[re.Match[str]],
    context: str,
) -> bool:
    if len(negation_matches) < 2:
        return False

    previous_match = negation_matches[-2]
    latest_match = negation_matches[-1]
    between_negations = context[previous_match.end() : latest_match.start()]
    return re.search(r"\b(?:and|or|nor)\b", between_negations) is None


def _has_uncoordinated_clause_boundary(after_negation: str) -> bool:
    last_comma = after_negation.rfind(",")
    if last_comma < 0:
        return False
    tail = after_negation[last_comma + 1 :]
    if not re.search(r"\w", tail) and "," in after_negation[:last_comma]:
        return False
    return re.search(r"\b(?:and|or)\s*$", tail) is None


def _is_ignored_negation_match(match: re.Match[str], context: str) -> bool:
    return _is_not_only_negation(match, context) or _is_discourse_marker_no(
        match,
        context,
    )


def _is_not_only_negation(match: re.Match[str], context: str) -> bool:
    return context[match.end() :].lstrip().startswith("only ")


def _is_discourse_marker_no(match: re.Match[str], context: str) -> bool:
    if match.group(0).casefold() != "no":
        return False
    return context[match.end() :].lstrip().startswith((",", "/", "-", "\u2013", "\u2014"))


def _has_later_affirmative_forbidden_action(text: str) -> bool:
    for prefix in _FORBIDDEN_ACTION_PREFIXES:
        verb = re.escape(prefix.strip())
        if re.search(
            rf"(?:\band\b|[,;])\s+(?:then\s+)?(?:i\s+|we\s+)?"
            rf"(?:will\s+|would\s+|can\s+|could\s+|should\s+)?{verb}\b",
            text,
        ):
            return True
    return False


def _claimed_result_values(answer_text: str) -> tuple[str, ...]:
    return tuple(
        claim_value
        for claim_value, _, _ in _claimed_result_value_matches(answer_text)
    )


def _claimed_result_value_matches(answer_text: str) -> tuple[ResultValueClaim, ...]:
    claimed_values: list[ResultValueClaim] = []
    for match in _RESULT_VALUE_PATTERN.finditer(answer_text):
        value = match.group(0)
        if _is_incidental_integer_claim(answer_text, match) or _is_row_reference_value(
            answer_text,
            match,
        ):
            continue
        claimed_values.append((value, match.start(), match.end()))
    return tuple(claimed_values)


def _is_incidental_integer_claim(answer_text: str, match: re.Match[str]) -> bool:
    value = match.group(0)
    bare_value = value.strip("()")
    if not bare_value.isdigit():
        return False
    context = answer_text[max(0, match.start() - 16) : match.start()]
    return bool(
        _is_numbered_list_marker(answer_text, match)
        or _INCIDENTAL_INTEGER_PREFIX_PATTERN.search(context)
        or _INCIDENTAL_PARENTHESES_YEAR_PREFIX_PATTERN.search(context)
    )


def _is_numbered_list_marker(answer_text: str, match: re.Match[str]) -> bool:
    value = match.group(0)
    bare_value = value.strip("()")
    if not bare_value.isdigit() or int(bare_value) > 99:
        return False

    before = answer_text[: match.start()].rstrip()
    if before and before[-1] not in ".:;\n\r":
        return False

    after = answer_text[match.end() : match.end() + 2]
    if value.startswith("(") and value.endswith(")"):
        return after.startswith((" ", "\t", "\n", "\r"))
    return after in {". ", ") "}


def _is_row_reference_value(answer_text: str, match: re.Match[str]) -> bool:
    if not match.group(0).isdigit():
        return False
    for citation_match in _ROW_REFERENCE_CITATION_PATTERN.finditer(answer_text):
        citation_value_start = citation_match.start(1)
        citation_value_end = citation_match.end(1)
        if citation_value_start <= match.start() and match.end() <= citation_value_end:
            return True
    return False


def _supported_result_values(result_rows: Sequence[Mapping[str, Any]]) -> set[str]:
    supported: set[str] = set()
    for row in result_rows:
        for value in row.values():
            supported.update(_value_forms(value))
    return supported


def _unsupported_claimed_result_values(
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
    result_metadata: Mapping[str, Any],
) -> tuple[str, ...]:
    supported_values = _supported_result_values(result_rows)
    unsupported: list[str] = []
    for claim_value, start, end in _claimed_result_value_matches(answer_text):
        if _metadata_row_count_claim_is_supported(
            answer_text=answer_text,
            claim_value=claim_value,
            start=start,
            end=end,
            result_metadata=result_metadata,
        ):
            continue
        if _value_forms(claim_value).isdisjoint(supported_values):
            unsupported.append(claim_value)
    return tuple(unsupported)


def _unsupported_claimed_result_row_combinations(
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    row_value_forms = [_row_value_forms(row) for row in result_rows]
    supported_values = set().union(*row_value_forms) if row_value_forms else set()
    unsupported: list[str] = []
    claimed_values = _claimed_result_value_matches(answer_text)
    for left, right in zip(claimed_values, claimed_values[1:]):
        if _claim_value_pair_is_unsupported(
            left=left,
            right=right,
            between_values=answer_text[left[2] : right[1]],
            row_value_forms=row_value_forms,
            supported_values=supported_values,
        ):
            unsupported.append(f"{left[0]} with {right[0]}")
    unsupported.extend(
        _unsupported_respective_result_row_combinations(
            answer_text=answer_text,
            claimed_values=claimed_values,
            row_value_forms=row_value_forms,
            supported_values=supported_values,
        )
    )
    return tuple(unsupported)


def _claimed_result_row_value_pairs(
    answer_text: str,
) -> tuple[tuple[ResultValueClaim, ResultValueClaim], ...]:
    pairs: list[tuple[ResultValueClaim, ResultValueClaim]] = []
    claimed_values = _claimed_result_value_matches(answer_text)
    for left, right in zip(claimed_values, claimed_values[1:]):
        between_values = _claim_value_link_context(answer_text[left[2] : right[1]])
        if _claim_values_are_row_linked(between_values):
            pairs.append((left, right))
    return tuple(pairs)


def _row_reference_citation_for_claim(
    *,
    answer_text: str,
    claim_start: int,
    claim_end: int,
) -> int | None:
    sentence_start = _sentence_start_before(answer_text, claim_start)
    sentence_end = _sentence_end_after(answer_text, claim_end)
    citation_matches = tuple(
        _ROW_REFERENCE_CITATION_PATTERN.finditer(
            answer_text[sentence_start:sentence_end]
        )
    )
    if not citation_matches:
        return None

    def citation_distance(match: re.Match[str]) -> int:
        citation_start = sentence_start + match.start()
        citation_end = sentence_start + match.end()
        if citation_end < claim_start:
            return claim_start - citation_end
        if citation_start > claim_end:
            return citation_start - claim_end
        return 0

    nearest_citation = min(citation_matches, key=citation_distance)
    return int(nearest_citation.group(1))


def _sentence_end_after(text: str, start: int) -> int:
    sentence_end = re.search(r"[.!?]", text[start:])
    if sentence_end is None:
        return len(text)
    return start + sentence_end.start()


def _unsupported_no_evidence_result_value_claims(
    answer_text: str,
    result_metadata: Mapping[str, Any],
) -> tuple[str, ...]:
    unsupported: list[str] = []
    claimed_values = _claimed_result_value_matches(answer_text)
    paired_claim_values: set[tuple[int, int]] = set()
    for left, right in zip(claimed_values, claimed_values[1:]):
        left_value, _, left_end = left
        right_value, right_start, _ = right
        if _claim_values_are_row_linked(answer_text[left_end:right_start]):
            unsupported.append(f"{left_value} with {right_value}")
            paired_claim_values.add((left[1], left[2]))
            paired_claim_values.add((right[1], right[2]))
    for value, start, end in claimed_values:
        if (start, end) in paired_claim_values:
            continue
        if _metadata_row_count_claim_is_supported(
            answer_text=answer_text,
            claim_value=value,
            start=start,
            end=end,
            result_metadata=result_metadata,
        ):
            continue
        if _value_is_numeric_result_claim(value):
            unsupported.append(value)
    return tuple(unsupported)


def _metadata_row_count_claim_is_supported(
    *,
    answer_text: str,
    claim_value: str,
    start: int,
    end: int,
    result_metadata: Mapping[str, Any],
) -> bool:
    observed_row_count = result_metadata.get("row_count")
    if type(observed_row_count) is not int:
        return False
    if _value_forms(claim_value).isdisjoint(_value_forms(observed_row_count)):
        return False
    return _claim_value_has_row_count_context(
        answer_text=answer_text,
        start=start,
        end=end,
    )


def _claim_value_has_row_count_context(
    *,
    answer_text: str,
    start: int,
    end: int,
) -> bool:
    before = answer_text[max(0, start - 40) : start]
    after = answer_text[end : end + 40]
    return bool(
        re.search(r"^\s+(?:result\s+)?(?:row|rows|record|records)\b", after, re.I)
        or re.search(
            r"\b(?:row|rows|record|records)\s+"
            r"(?:count|returned|observed|available|included|matched)\s*(?::|=)?\s*$",
            before,
            re.I,
        )
    )


def _row_value_forms(row: Mapping[str, Any]) -> set[str]:
    forms: set[str] = set()
    for value in row.values():
        forms.update(_value_forms(value))
    return forms


def _claim_values_are_row_linked(between_values: str) -> bool:
    link_context = _claim_value_link_context(between_values)
    if _claim_value_link_context_has_sentence_break(link_context):
        return False
    row_link_match = _CLAIM_VALUE_ROW_LINK_PATTERN.search(link_context)
    if row_link_match is None:
        return False
    if _has_unlinked_value_conjunction(link_context):
        return False
    if _CLAIM_VALUE_NON_ROW_COMPARISON_PATTERN.search(link_context):
        return False
    if _CLAIM_VALUE_NEGATED_COPULA_PATTERN.search(link_context):
        return False
    return True


def _claim_value_link_context(between_values: str) -> str:
    return _ROW_REFERENCE_CITATION_PATTERN.sub(" ", between_values)


def _claim_value_link_context_has_sentence_break(link_context: str) -> bool:
    abbreviation_safe_context = _CLAIM_VALUE_ABBREVIATION_PERIOD_PATTERN.sub(
        lambda match: match.group(0).replace(".", ""),
        link_context,
    )
    return bool(re.search(r"[.!?]", abbreviation_safe_context))


def _has_unlinked_value_conjunction(between_values: str) -> bool:
    conjunction_matches = tuple(
        re.finditer(r"\b(?:and|or)\b", between_values, re.IGNORECASE)
    )
    if not conjunction_matches:
        return False
    return _CLAIM_VALUE_ROW_LINK_PATTERN.search(
        between_values[conjunction_matches[-1].end() :]
    ) is None


def _unsupported_respective_result_row_combinations(
    *,
    answer_text: str,
    claimed_values: Sequence[tuple[str, int, int]],
    row_value_forms: Sequence[set[str]],
    supported_values: set[str],
) -> tuple[str, ...]:
    unsupported: list[str] = []
    for respectively_match in re.finditer(
        r"\brespectively\b",
        answer_text,
        re.IGNORECASE,
    ):
        segment_start = _sentence_start_before(answer_text, respectively_match.start())
        segment_values = tuple(
            claimed_value
            for claimed_value in claimed_values
            if segment_start <= claimed_value[1] < respectively_match.start()
        )
        if len(segment_values) < 4 or len(segment_values) % 2:
            continue
        midpoint = len(segment_values) // 2
        for left, right in zip(segment_values[:midpoint], segment_values[midpoint:]):
            if _claim_value_pair_is_unsupported(
                left=left,
                right=right,
                between_values="respectively",
                row_value_forms=row_value_forms,
                supported_values=supported_values,
                require_link=False,
            ):
                unsupported.append(f"{left[0]} with {right[0]}")
    return tuple(unsupported)


def _claim_value_pair_is_unsupported(
    *,
    left: tuple[str, int, int],
    right: tuple[str, int, int],
    between_values: str,
    row_value_forms: Sequence[set[str]],
    supported_values: set[str],
    require_link: bool = True,
) -> bool:
    left_value = left[0]
    right_value = right[0]
    left_forms = _value_forms(left_value)
    right_forms = _value_forms(right_value)
    if left_forms.isdisjoint(supported_values) or right_forms.isdisjoint(
        supported_values
    ):
        return False
    if require_link and not _claim_values_are_row_linked(between_values):
        return False
    return not any(
        not left_forms.isdisjoint(row_forms) and not right_forms.isdisjoint(row_forms)
        for row_forms in row_value_forms
    )


def _sentence_start_before(text: str, end: int) -> int:
    sentence_boundaries = tuple(re.finditer(r"[.!?]\s+", text[:end]))
    if not sentence_boundaries:
        return 0
    return sentence_boundaries[-1].end()


def _value_is_numeric_result_claim(value: str) -> bool:
    try:
        _decimal_from_value_text(value)
    except (InvalidOperation, ValueError):
        return False
    return True


def _value_forms(value: Any) -> set[str]:
    text = str(value).strip()
    uncomma_text = text.replace(",", "")
    forms = {text, text.casefold(), uncomma_text, uncomma_text.casefold()}
    try:
        normalized_decimal = _decimal_from_value_text(text).normalize()
    except (InvalidOperation, ValueError):
        return forms
    forms.add(format(normalized_decimal, "f"))
    if normalized_decimal == normalized_decimal.to_integral():
        forms.add(str(int(normalized_decimal)))
    return forms


def _decimal_from_value_text(text: str) -> Decimal:
    accounting_match = re.fullmatch(
        r"\(\s*([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:e[+-]?\d+)?)\s*\)",
        text,
        re.IGNORECASE,
    )
    if accounting_match:
        magnitude_text = accounting_match.group(1).replace(",", "").lstrip("+-")
        return -Decimal(magnitude_text)
    return Decimal(text.replace(",", ""))
