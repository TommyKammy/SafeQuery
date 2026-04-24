from __future__ import annotations

import re
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from app.features.audit.event_model import (
    ExecutedEvidenceAuditPayload,
    NonEmptyTrimmedString,
    RetrievalCitationAuditPayload,
    SourceFamily,
    SourceFlavor,
    SourceIdentifier,
    to_camel,
)

AnalystConfidence = Literal["low", "medium", "high", "unknown"]
AnalystValidationCheck = Literal[
    "source_labeled_evidence_present",
    "source_summary_coverage",
    "narrative_execution_authority",
    "narrative_execution_grounding",
    "narrative_cross_source_execution",
]

_EXECUTION_APPROVAL_PATTERN = re.compile(
    r"\b("
    r"approv(?:e|es|ed|ing)\s+(?:sql\s+)?execution|"
    r"execution\s+(?:is\s+)?approv(?:e|ed)|"
    r"authori[sz](?:e|es|ed|ing)\s+(?:sql\s+)?execution|"
    r"execution\s+(?:is\s+)?authori[sz](?:e|ed)|"
    r"safe\s+to\s+(?:execute|run)|"
    r"can\s+(?:execute|run)\s+(?:this\s+)?(?:sql|query|candidate)"
    r")\b",
    re.IGNORECASE,
)
_EXECUTION_CLAIM_PATTERN = re.compile(
    r"\b("
    r"backend\s+execution\s+(?:show(?:s|ed)?|returned|produced)|"
    r"completed\s+backend\s+execution|"
    r"execut(?:e|ed|ion)\s+(?:result|evidence)\s+(?:show(?:s|ed)?|returned|produced)|"
    r"(?:query|candidate)\s+(?:ran|executed)\b|"
    r"rows?\s+(?:were\s+)?returned"
    r")",
    re.IGNORECASE,
)
_CROSS_SOURCE_EXECUTION_PATTERN = re.compile(
    r"\b("
    r"cross[- ]source\s+(?:execution|query|join)|"
    r"federated\s+(?:execution|query)|"
    r"(?:joined|merged|combined)\s+(?:across\s+sources|execution\s+results)|"
    r"executed\s+together|"
    r"ran\s+across\s+(?:both|multiple)\s+sources"
    r")\b",
    re.IGNORECASE,
)


class AnalystResponseSourceSummary(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: Optional[PositiveInt] = None


class OperatorHistoryHooks(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    audit_event_id: Optional[UUID] = None
    history_record_ids: list[NonEmptyTrimmedString] = Field(default_factory=list)


class AnalystResponseValidationOutcome(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    status: Literal["safe"] = "safe"
    checks: list[AnalystValidationCheck] = Field(
        default_factory=lambda: [
            "source_labeled_evidence_present",
            "source_summary_coverage",
            "narrative_execution_authority",
            "narrative_execution_grounding",
            "narrative_cross_source_execution",
        ]
    )
    unsafe_reasons: list[NonEmptyTrimmedString] = Field(default_factory=list)


class AnalystResponsePayload(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    response_id: NonEmptyTrimmedString
    request_id: NonEmptyTrimmedString
    narrative: NonEmptyTrimmedString
    advisory_only: Literal[True] = True
    can_authorize_execution: Literal[False] = False
    analyst_mode_version: NonEmptyTrimmedString
    confidence: AnalystConfidence = "unknown"
    caveats: list[NonEmptyTrimmedString] = Field(default_factory=list)
    source_summaries: list[AnalystResponseSourceSummary] = Field(default_factory=list)
    retrieval_citations: list[RetrievalCitationAuditPayload] = Field(default_factory=list)
    executed_evidence: list[ExecutedEvidenceAuditPayload] = Field(default_factory=list)
    operator_history_hooks: OperatorHistoryHooks = Field(default_factory=OperatorHistoryHooks)
    validation_outcome: AnalystResponseValidationOutcome = Field(
        default_factory=AnalystResponseValidationOutcome
    )

    def to_wire_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)

    @model_validator(mode="after")
    def validate_source_summaries(self) -> "AnalystResponsePayload":
        if not self.retrieval_citations and not self.executed_evidence:
            raise ValueError(
                "Analyst responses must cite retrieval context or executed evidence."
            )

        expected = {
            (
                item.source_id,
                item.source_family,
                item.source_flavor,
                item.dataset_contract_version,
                item.schema_snapshot_version,
            )
            for item in [*self.retrieval_citations, *self.executed_evidence]
        }
        supplied = {
            (
                item.source_id,
                item.source_family,
                item.source_flavor,
                item.dataset_contract_version,
                item.schema_snapshot_version,
            )
            for item in self.source_summaries
        }

        if supplied and not expected.issubset(supplied):
            raise ValueError(
                "Source summaries must include every citation and executed evidence source."
            )

        return self

    @model_validator(mode="after")
    def validate_narrative_authority(self) -> "AnalystResponsePayload":
        narrative = self.narrative
        cited_sources = {
            (item.source_id, item.source_family)
            for item in [*self.retrieval_citations, *self.executed_evidence]
        }

        if len(cited_sources) > 1 and _CROSS_SOURCE_EXECUTION_PATTERN.search(narrative):
            raise ValueError(
                "Analyst narrative must not imply cross-source execution authority."
            )

        if _EXECUTION_APPROVAL_PATTERN.search(narrative):
            raise ValueError(
                "Analyst narrative must not imply execution approval authority."
            )

        if not self.executed_evidence and _EXECUTION_CLAIM_PATTERN.search(narrative):
            raise ValueError(
                "Analyst narrative must not claim executed evidence without source-labeled executed evidence."
            )

        return self
