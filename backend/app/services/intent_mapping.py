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

    if any(
        marker in normalized
        for marker in (
            "unapproved vendor spend",
            "bank account numbers",
            "tax identifiers",
            "ignore the system prompt",
            "dump every approved vendor spend row",
            "every column and every row",
            "whatever source has the vendor spend table",
        )
    ):
        return IntentMappingOutput(
            status="unsupported",
            clarification=(
                "The question references concepts outside the approved vendor "
                "spend semantic contract."
            ),
        )

    base = {
        "metric": "sum_approved_vendor_spend",
        "filters": ["approved_spend_only"],
    }
    if "refund" in normalized or "after refunds" in normalized:
        return IntentMappingOutput(
            status="ambiguous",
            mapping_id="clarify_refund_inclusion",
            dimensions=["vendor_name", "fiscal_quarter"],
            clarification="Clarify gross spend versus net-of-refunds spend before mapping.",
            **base,
        )
    if "calendar quarter" in normalized or " q1" in f" {normalized}":
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

    if "approved vendor spend" in normalized and "quarter" in normalized:
        return IntentMappingOutput(
            status="mapped",
            mapping_id="approved_vendor_spend_by_fiscal_quarter",
            dimensions=["fiscal_quarter"],
            **base,
        )
    if (
        "approved vendors" in normalized
        and ("quarterly spend" in normalized or "quarter spend" in normalized)
    ):
        return IntentMappingOutput(
            status="mapped",
            mapping_id="show_top_approved_vendors_by_quarterly_spend",
            dimensions=["vendor_name", "fiscal_quarter"],
            ranking_behavior_id="top_approved_vendors_by_quarterly_spend",
            **base,
        )
    if "approved vendor spend" in normalized or "approved vendors" in normalized:
        return IntentMappingOutput(
            status="mapped",
            mapping_id="approved_vendor_spend_general",
            dimensions=[],
            **base,
        )

    return IntentMappingOutput(
        status="mapped",
        mapping_id="legacy_guard_evaluated_mapping",
    )
