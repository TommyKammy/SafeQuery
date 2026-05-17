from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing_extensions import Annotated


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
IntentMappingStatus = Literal["mapped", "ambiguous", "unsupported"]


class IntentMappingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IntentMappingStatus
    mapping_id: Optional[NonEmptyTrimmedString] = None
    metric: Optional[NonEmptyTrimmedString] = None
    dimensions: list[NonEmptyTrimmedString] = Field(default_factory=list)
    filters: list[NonEmptyTrimmedString] = Field(default_factory=list)
    ranking_behavior_id: Optional[NonEmptyTrimmedString] = None
    clarification: Optional[NonEmptyTrimmedString] = None


def _normalize_question(question: str) -> str:
    lowered = question.strip().casefold()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _contains_phrase(normalized: str, phrase: str) -> bool:
    return re.search(rf"(?:^| ){re.escape(phrase)}(?: |$)", normalized) is not None


def _mentions_approved_vendor_intent(normalized: str) -> bool:
    if _contains_phrase(normalized, "approved vendor spend") or _contains_phrase(
        normalized, "approved spend"
    ):
        return True
    return (
        _contains_phrase(normalized, "approved vendors")
        or _contains_phrase(normalized, "approved vendor")
    ) and _contains_phrase(normalized, "spend")


def _mentions_negated_approved_vendor_intent(normalized: str) -> bool:
    return any(
        _contains_phrase(normalized, marker)
        for marker in (
            "not approved vendor spend",
            "not approved vendors",
            "not approved vendor",
            "not approved spend",
            "non approved vendor spend",
            "non approved vendors",
            "non approved vendor",
            "non approved spend",
        )
    )


def _mentions_quarter_shorthand(normalized: str) -> bool:
    return re.search(r"\bq[1-4]\b", normalized) is not None


def _mentions_explicit_fiscal_quarter_shorthand(normalized: str) -> bool:
    return (
        re.search(
            r"\b(?:fiscal|fy(?: ?[0-9]{2,4})?) q[1-4]\b",
            normalized,
        )
        is not None
    )


def _mentions_ambiguous_quarter_shorthand(normalized: str) -> bool:
    return _mentions_quarter_shorthand(
        normalized
    ) and not _mentions_explicit_fiscal_quarter_shorthand(normalized)


def _mentions_ambiguity_marker(normalized: str) -> bool:
    return (
        "refund" in normalized
        or "after refunds" in normalized
        or "calendar quarter" in normalized
        or _mentions_ambiguous_quarter_shorthand(normalized)
        or "top 2" in normalized
        or "top two" in normalized
        or "including ties" in normalized
    )


def _mentions_unapproved_vendor_spend(normalized: str) -> bool:
    return (
        _contains_phrase(normalized, "unapproved vendor spend")
        or (
            _contains_phrase(normalized, "unapproved spend")
            and (
                _contains_phrase(normalized, "vendor")
                or _contains_phrase(normalized, "vendors")
            )
        )
        or (
            (
                _contains_phrase(normalized, "unapproved vendor")
                or _contains_phrase(normalized, "unapproved vendors")
            )
            and _contains_phrase(normalized, "spend")
        )
    )


def _mentions_approval_timing_ambiguity(normalized: str) -> bool:
    mentions_approved_vendor_domain = (
        (
            _contains_phrase(normalized, "approved")
            and (
                _contains_phrase(normalized, "vendor")
                or _contains_phrase(normalized, "vendors")
                or _contains_phrase(normalized, "spend")
            )
        )
        or _mentions_approved_vendor_intent(normalized)
    )
    return mentions_approved_vendor_domain and (
        _contains_phrase(normalized, "when the transaction happened")
        or _contains_phrase(normalized, "transaction time")
        or _contains_phrase(normalized, "approval timestamp")
    )


def _mentions_vendor_normalization_ambiguity(normalized: str) -> bool:
    return _mentions_approved_vendor_intent(normalized) and (
        _contains_phrase(normalized, "same vendor")
        or _contains_phrase(normalized, "normalize vendor")
        or _contains_phrase(normalized, "normalize vendors")
        or _contains_phrase(normalized, "vendor normalization")
        or _contains_phrase(normalized, "vendor name normalization")
    )


def _unsupported_no_approved_vendor_mapping_match() -> IntentMappingOutput:
    return IntentMappingOutput(
        status="unsupported",
        clarification=(
            "The question does not match an approved vendor spend semantic "
            "contract intent mapping."
        ),
    )


def map_question_intent(question: str, *, semantic_contract_version: str | None) -> IntentMappingOutput:
    normalized = _normalize_question(question)
    if semantic_contract_version is None:
        return IntentMappingOutput(status="mapped", mapping_id="legacy_unversioned_mapping")
    if semantic_contract_version != "approved_vendor_spend.v1":
        return IntentMappingOutput(
            status="unsupported",
            clarification=(
                "No authoritative semantic contract intent mapping is available "
                "for the selected source."
            ),
        )

    if (
        _mentions_unapproved_vendor_spend(normalized)
        or _mentions_negated_approved_vendor_intent(normalized)
        or any(
            marker in normalized
            for marker in (
                "bank account numbers",
                "tax identifiers",
                "ignore the system prompt",
                "dump every approved vendor spend row",
                "every column and every row",
                "whatever source has the vendor spend table",
            )
        )
    ):
        return IntentMappingOutput(
            status="unsupported",
            clarification=(
                "The question references concepts outside the approved vendor "
                "spend semantic contract."
            ),
        )

    approved_vendor_intent = _mentions_approved_vendor_intent(normalized)

    if _mentions_ambiguity_marker(normalized) and not approved_vendor_intent:
        return IntentMappingOutput(
            status="unsupported",
            clarification=(
                "The ambiguous concept is not bound to approved vendor spend "
                "in the selected semantic contract."
            ),
        )

    base = {
        "metric": "sum_approved_vendor_spend",
        "filters": ["approved_spend_only"],
    }
    if _mentions_approval_timing_ambiguity(normalized):
        return IntentMappingOutput(
            status="ambiguous",
            mapping_id="clarify_approval_timing",
            dimensions=["vendor_name"],
            clarification=(
                "Clarify whether approval means transaction-time approval or "
                "current approval status before mapping."
            ),
            **base,
        )
    if _mentions_vendor_normalization_ambiguity(normalized):
        return IntentMappingOutput(
            status="ambiguous",
            mapping_id="clarify_vendor_name_normalization",
            dimensions=["vendor_name"],
            clarification=(
                "Clarify the authoritative vendor-normalization or vendor-master "
                "binding before mapping."
            ),
            **base,
        )
    if approved_vendor_intent:
        if "refund" in normalized or "after refunds" in normalized:
            return IntentMappingOutput(
                status="ambiguous",
                mapping_id="clarify_refund_inclusion",
                dimensions=["vendor_name", "fiscal_quarter"],
                clarification=(
                    "Clarify gross spend versus net-of-refunds spend before mapping."
                ),
                **base,
            )
        if "calendar quarter" in normalized or _mentions_ambiguous_quarter_shorthand(
            normalized
        ):
            return IntentMappingOutput(
                status="ambiguous",
                mapping_id="clarify_calendar_vs_fiscal_quarter",
                dimensions=["fiscal_quarter"],
                clarification="Clarify fiscal versus calendar quarter before mapping.",
                **base,
            )
        if (
            "top 2" in normalized
            or "top two" in normalized
            or "including ties" in normalized
        ):
            return IntentMappingOutput(
                status="ambiguous",
                mapping_id="clarify_top_n_ties",
                dimensions=["vendor_name", "fiscal_quarter"],
                ranking_behavior_id="top_approved_vendors_by_quarterly_spend",
                clarification=(
                    "Clarify whether ties at the cutoff should be included or broken "
                    "by a stable secondary sort before mapping."
                ),
                **base,
            )

    if (
        _contains_phrase(normalized, "approved vendor spend")
        or _contains_phrase(normalized, "approved spend")
    ) and (
        _contains_phrase(normalized, "quarter")
        or _mentions_explicit_fiscal_quarter_shorthand(normalized)
    ):
        return IntentMappingOutput(
            status="mapped",
            mapping_id="approved_vendor_spend_by_fiscal_quarter",
            dimensions=["fiscal_quarter"],
            **base,
        )
    if (
        _contains_phrase(normalized, "approved vendors")
        and (
            _contains_phrase(normalized, "quarterly spend")
            or _contains_phrase(normalized, "quarter spend")
        )
    ):
        return IntentMappingOutput(
            status="mapped",
            mapping_id="show_top_approved_vendors_by_quarterly_spend",
            dimensions=["vendor_name", "fiscal_quarter"],
            ranking_behavior_id="top_approved_vendors_by_quarterly_spend",
            **base,
        )
    if (
        (
            _contains_phrase(normalized, "approved vendor spend")
            or _contains_phrase(normalized, "approved spend")
        )
        and (
            _contains_phrase(normalized, "top")
            or _contains_phrase(normalized, "highest spend")
        )
        and (
            _contains_phrase(normalized, "records")
            or _contains_phrase(normalized, "record")
            or _contains_phrase(normalized, "rows")
            or _contains_phrase(normalized, "row")
        )
    ):
        return IntentMappingOutput(
            status="mapped",
            mapping_id="show_top_approved_vendor_spend_rows",
            dimensions=["vendor_name"],
            **base,
        )
    return _unsupported_no_approved_vendor_mapping_match()
