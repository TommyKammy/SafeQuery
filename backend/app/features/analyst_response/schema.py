from __future__ import annotations

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
)

AnalystConfidence = Literal["low", "medium", "high", "unknown"]


class AnalystResponseSourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dataset_contract_version: Optional[PositiveInt] = None
    schema_snapshot_version: Optional[PositiveInt] = None
    execution_policy_version: Optional[PositiveInt] = None


class OperatorHistoryHooks(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_event_id: Optional[UUID] = None
    history_record_ids: list[NonEmptyTrimmedString] = Field(default_factory=list)


class AnalystResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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
