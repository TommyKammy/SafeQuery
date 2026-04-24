from __future__ import annotations

from typing import Literal, Optional, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, NonNegativeInt, PositiveInt, model_validator

from app.features.audit.event_model import (
    NonEmptyTrimmedString,
    SourceAwareAuditEvent,
    SourceFamily,
    SourceFlavor,
    SourceIdentifier,
)
from app.features.evaluation.harness import EvaluationBoundary, EvaluationScenarioKind


PROHIBITED_EXPORT_FIELDS = frozenset(
    {
        "credentials",
        "connection_string",
        "connection_strings",
        "raw_result_set",
        "raw_result_sets",
        "result_rows",
        "controlled_corpus_body",
        "controlled_corpus_bodies",
        "natural_language_request",
        "unredacted_natural_language_request",
        "canonical_sql",
        "identity_claims",
        "user_subject",
        "session_cookie",
        "token",
    }
)


class MLflowExportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_schema_version: Literal[1] = 1
    export_kind: Literal["audit_trace", "evaluation_record"]
    authority: Literal["engineering_observability"] = "engineering_observability"
    can_authorize_or_mutate_audit: Literal[False] = False

    safequery_audit_event_id: Optional[UUID] = None
    mlflow_run_id: Optional[NonEmptyTrimmedString] = None
    evaluation_run_id: Optional[NonEmptyTrimmedString] = None

    request_id: Optional[NonEmptyTrimmedString] = None
    candidate_id: Optional[NonEmptyTrimmedString] = None
    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: PositiveInt
    connector_profile_version: Optional[PositiveInt] = None

    deny_code: Optional[NonEmptyTrimmedString] = None
    latency_ms: Optional[NonNegativeInt] = None
    row_count: Optional[NonNegativeInt] = None
    result_truncated: Optional[bool] = None

    prompt_version: Optional[NonEmptyTrimmedString] = None
    model_version: Optional[NonEmptyTrimmedString] = None
    application_version: Optional[NonEmptyTrimmedString] = None
    adapter_version: Optional[NonEmptyTrimmedString] = None

    evaluation_scenario_id: Optional[NonEmptyTrimmedString] = None
    evaluation_kind: Optional[EvaluationScenarioKind] = None
    evaluation_boundary: Optional[EvaluationBoundary] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_prohibited_export_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        prohibited = sorted(PROHIBITED_EXPORT_FIELDS.intersection(value))
        if prohibited:
            raise ValueError(
                "MLflow export payload includes prohibited field(s): "
                + ", ".join(prohibited)
            )
        return value

    @model_validator(mode="after")
    def _require_kind_specific_identifiers(self) -> "MLflowExportPayload":
        if self.export_kind == "audit_trace":
            if self.safequery_audit_event_id is None:
                raise ValueError("Audit trace exports must reference a SafeQuery audit event.")
            if self.request_id is None:
                raise ValueError("Audit trace exports must include a request identifier.")
        if self.export_kind == "evaluation_record":
            if self.evaluation_scenario_id is None:
                raise ValueError("Evaluation exports must include an evaluation scenario id.")
            if self.evaluation_kind is None:
                raise ValueError("Evaluation exports must include an evaluation kind.")
            if self.evaluation_boundary is None:
                raise ValueError("Evaluation exports must include an evaluation boundary.")
        return self


class _EvaluationScenario(Protocol):
    scenario_id: str
    kind: EvaluationScenarioKind
    evaluation_boundary: EvaluationBoundary
    source: object


def build_mlflow_export_from_audit_event(
    audit_event: SourceAwareAuditEvent,
    *,
    enabled: bool,
    latency_ms: Optional[int] = None,
    mlflow_run_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> Optional[MLflowExportPayload]:
    if not enabled:
        return None
    return MLflowExportPayload(
        export_kind="audit_trace",
        safequery_audit_event_id=audit_event.event_id,
        mlflow_run_id=mlflow_run_id,
        request_id=audit_event.request_id,
        candidate_id=audit_event.query_candidate_id,
        source_id=audit_event.source_id,
        source_family=audit_event.source_family,
        source_flavor=audit_event.source_flavor,
        dataset_contract_version=audit_event.dataset_contract_version,
        schema_snapshot_version=audit_event.schema_snapshot_version,
        execution_policy_version=audit_event.execution_policy_version,
        connector_profile_version=audit_event.connector_profile_version,
        deny_code=audit_event.primary_deny_code,
        latency_ms=latency_ms,
        row_count=audit_event.execution_row_count,
        result_truncated=audit_event.result_truncated,
        prompt_version=prompt_version,
        model_version=model_version,
        application_version=audit_event.application_version,
        adapter_version=audit_event.adapter_version,
    )


def build_mlflow_export_from_evaluation_scenario(
    scenario: _EvaluationScenario,
    *,
    enabled: bool,
    evaluation_run_id: Optional[str] = None,
    deny_code: Optional[str] = None,
    latency_ms: Optional[int] = None,
    row_count: Optional[int] = None,
    result_truncated: Optional[bool] = None,
    prompt_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> Optional[MLflowExportPayload]:
    if not enabled:
        return None
    source = scenario.source
    return MLflowExportPayload(
        export_kind="evaluation_record",
        evaluation_run_id=evaluation_run_id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dataset_contract_version=source.dataset_contract_version,
        schema_snapshot_version=source.schema_snapshot_version,
        execution_policy_version=source.execution_policy_version,
        connector_profile_version=source.connector_profile_version,
        deny_code=deny_code,
        latency_ms=latency_ms,
        row_count=row_count,
        result_truncated=result_truncated,
        prompt_version=prompt_version,
        model_version=model_version,
        evaluation_scenario_id=scenario.scenario_id,
        evaluation_kind=scenario.kind,
        evaluation_boundary=scenario.evaluation_boundary,
    )
