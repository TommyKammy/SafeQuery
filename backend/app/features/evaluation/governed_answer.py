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
_NEGATED_CLAIM_PATTERN = re.compile(
    r"(?:^|\b)(?:"
    r"not|no|never|cannot|can't|don't|didn't|doesn't|won't|"
    r"did\s+not|does\s+not|do\s+not|will\s+not|"
    r"was\s+not|were\s+not|is\s+not|are\s+not"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_CLAIM_CONTRAST_PATTERN = re.compile(
    r"\b(?:but|however|though|although|except)\b",
    re.IGNORECASE,
)
_CLAIM_VALUE_ROW_LINK_PATTERN = re.compile(
    r"(?:=|:|\b(?:is|are|was|were|had|has|with|at|of|for|totaled|totals?|equals?)\b)",
    re.IGNORECASE,
)
_CLAIM_VALUE_NEGATED_COPULA_PATTERN = re.compile(
    r"\b(?:is|are|was|were)\s+not\b|\b(?:isn't|aren't|wasn't|weren't)\b",
    re.IGNORECASE,
)
_CLAIM_VALUE_NON_ROW_COMPARISON_PATTERN = re.compile(
    r"\b(?:after|before|compared|follows?|precedes?|than|versus|vs\.?)\b",
    re.IGNORECASE,
)
_FORBIDDEN_SUBJECT_SEPARATOR_PATTERN = re.compile(r"[\s\-\u2010-\u2015]+")
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
    categories: list[GovernedAnswerUnsupportedClaimCategory],
    unsupported_claims: list[str],
) -> None:
    if not result_rows:
        for claim_value in _unsupported_no_evidence_result_value_claims(answer_text):
            categories.append("unsupported_result_value")
            unsupported_claims.append(claim_value)
        return

    for claim_value in _unsupported_claimed_result_values(answer_text, result_rows):
        categories.append("unsupported_result_value")
        unsupported_claims.append(claim_value)
    for claim_value in _unsupported_claimed_result_row_combinations(
        answer_text,
        result_rows,
    ):
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
    if not normalized.startswith("do not "):
        return ()

    action = _clean_claim_text(normalized.removeprefix("do not "))
    prefix_subjects: list[str] = []
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
            break

    subjects: list[str] = []
    if matched_action_subject and _has_subject_disjunction(matched_action_subject):
        subjects.extend(prefix_subjects)
        subjects.extend(action_subjects)
    else:
        subjects.extend(action_subjects)
        subjects.extend(prefix_subjects)

    return tuple(
        dict.fromkeys(subject for subject in subjects if len(subject) >= 3)
    )


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


def _coordinated_forbidden_action_parts(subject: str) -> tuple[str, ...]:
    parts: list[str] = []
    for prefix in _FORBIDDEN_ACTION_PREFIXES:
        marker = f" and {prefix}"
        if marker not in subject:
            continue
        before, after = subject.split(marker, 1)
        parts.append(before)
        parts.append(f"{prefix}{after}")
        break
    return tuple(_clean_claim_text(part) for part in parts if _clean_claim_text(part))


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
    separator = r"[\s\-\u2010-\u2015]+"
    subject_pattern = separator.join(re.escape(token) for token in tokens)
    return re.compile(rf"(?<!\w){subject_pattern}(?!\w)")


def _claim_subject_is_negated(normalized_answer: str, claim_subject: str) -> bool:
    starts = [
        match.start()
        for match in _claim_subject_pattern(claim_subject).finditer(normalized_answer)
    ]
    if not starts:
        return False

    for start in starts:
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
    return context[match.end() :].lstrip().startswith((",", "-", "\u2013", "\u2014"))


def _has_later_affirmative_forbidden_action(text: str) -> bool:
    for prefix in _FORBIDDEN_ACTION_PREFIXES:
        verb = re.escape(prefix.strip())
        if re.search(
            rf"(?:\band\b|[,;])\s+(?:i\s+|we\s+)?"
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


def _claimed_result_value_matches(answer_text: str) -> tuple[tuple[str, int, int], ...]:
    claimed_values: list[tuple[str, int, int]] = []
    for match in _RESULT_VALUE_PATTERN.finditer(answer_text):
        value = match.group(0)
        if _is_incidental_integer_claim(answer_text, match):
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
        _INCIDENTAL_INTEGER_PREFIX_PATTERN.search(context)
        or _INCIDENTAL_PARENTHESES_YEAR_PREFIX_PATTERN.search(context)
    )


def _supported_result_values(result_rows: Sequence[Mapping[str, Any]]) -> set[str]:
    supported: set[str] = set()
    for row in result_rows:
        for value in row.values():
            supported.update(_value_forms(value))
    return supported


def _unsupported_claimed_result_values(
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    supported_values = _supported_result_values(result_rows)
    return tuple(
        claim_value
        for claim_value in _claimed_result_values(answer_text)
        if _value_forms(claim_value).isdisjoint(supported_values)
    )


def _unsupported_claimed_result_row_combinations(
    answer_text: str,
    result_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    row_value_forms = [_row_value_forms(row) for row in result_rows]
    supported_values = set().union(*row_value_forms) if row_value_forms else set()
    unsupported: list[str] = []
    claimed_values = _claimed_result_value_matches(answer_text)
    for left, right in zip(claimed_values, claimed_values[1:]):
        left_value, _, left_end = left
        right_value, right_start, _ = right
        left_forms = _value_forms(left_value)
        right_forms = _value_forms(right_value)
        if left_forms.isdisjoint(supported_values) or right_forms.isdisjoint(
            supported_values
        ):
            continue
        if not _claim_values_are_row_linked(answer_text[left_end:right_start]):
            continue
        if any(
            not left_forms.isdisjoint(row_forms)
            and not right_forms.isdisjoint(row_forms)
            for row_forms in row_value_forms
        ):
            continue
        unsupported.append(f"{left_value} with {right_value}")
    return tuple(unsupported)


def _unsupported_no_evidence_result_value_claims(answer_text: str) -> tuple[str, ...]:
    unsupported: list[str] = []
    claimed_values = _claimed_result_value_matches(answer_text)
    for left, right in zip(claimed_values, claimed_values[1:]):
        left_value, _, left_end = left
        right_value, right_start, _ = right
        if _claim_values_are_row_linked(answer_text[left_end:right_start]):
            unsupported.append(f"{left_value} with {right_value}")
    return tuple(unsupported)


def _row_value_forms(row: Mapping[str, Any]) -> set[str]:
    forms: set[str] = set()
    for value in row.values():
        forms.update(_value_forms(value))
    return forms


def _claim_values_are_row_linked(between_values: str) -> bool:
    if len(between_values) > 80:
        return False
    if re.search(r"\b(?:and|or)\b", between_values, re.IGNORECASE):
        return False
    if _CLAIM_VALUE_NON_ROW_COMPARISON_PATTERN.search(between_values):
        return False
    if _CLAIM_VALUE_NEGATED_COPULA_PATTERN.search(between_values):
        return False
    return _CLAIM_VALUE_ROW_LINK_PATTERN.search(between_values) is not None


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
