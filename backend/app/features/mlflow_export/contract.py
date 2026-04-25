from __future__ import annotations

import re
from collections.abc import Callable
from collections.abc import Mapping
from typing import Literal, Optional, Protocol
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    ValidationError,
    model_validator,
)

from app.features.audit.event_model import (
    NonEmptyTrimmedString,
    SourceAwareAuditEvent,
    SourceFamily,
    SourceFlavor,
    SourceIdentifier,
)
from app.features.evaluation.harness import EvaluationBoundary, EvaluationScenarioKind


RedactionSourceField = Literal[
    "natural_language_request",
    "sql_snippet",
    "explanation_sample",
    "retrieved_asset_reference",
    "evaluation_diagnostic",
]
RedactionProfile = Literal[
    "nl_excerpt_v1",
    "sql_snippet_v1",
    "explanation_sample_v1",
    "retrieved_asset_reference_v1",
    "evaluation_diagnostic_v1",
]
AccessRole = Literal["engineering", "operations", "security"]
EvaluationValidationStatus = Literal["passed", "failed", "skipped", "error"]

_APPROVED_PROFILE_BY_FIELD: dict[str, str] = {
    "natural_language_request": "nl_excerpt_v1",
    "sql_snippet": "sql_snippet_v1",
    "explanation_sample": "explanation_sample_v1",
    "retrieved_asset_reference": "retrieved_asset_reference_v1",
    "evaluation_diagnostic": "evaluation_diagnostic_v1",
}

_PROHIBITED_SAMPLE_PATTERNS = (
    re.compile(r"\bpassword\s*=", re.IGNORECASE),
    re.compile(r"\b(token|secret|api[_-]?key)\s*=", re.IGNORECASE),
    re.compile(r"\bbearer\s+[a-z0-9._~+/-]+", re.IGNORECASE),
    re.compile(r"\bserver\s*=.+\b(password|pwd)\s*=", re.IGNORECASE),
    re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE),
)

_RAW_WORKSTATION_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_.-])/(?:Users|home)/[^/\s]+/"),
    re.compile(r"(?<![A-Za-z0-9_.-])[A-Za-z]:\\Users\\[^\\\s]+\\"),
)


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
        "candidate_lifecycle_state",
        "candidate_state",
        "entitlement_state",
        "execution_approval_state",
        "guard_decision",
        "identity_claims",
        "connection_reference",
        "connection_references",
        "release_gate_status",
        "runtime_safety_state",
        "sql_guard_decision",
        "user_subject",
        "session_cookie",
        "token",
    }
)


class MLflowRedactedSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_field: RedactionSourceField
    redaction_profile: RedactionProfile
    value: NonEmptyTrimmedString
    source_metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _reject_prohibited_source_metadata(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        source_metadata = value.get("source_metadata")
        prohibited = _prohibited_export_fields_in_mapping(source_metadata)
        if prohibited:
            raise ValueError(
                "MLflow redacted sample metadata includes prohibited field(s): "
                + ", ".join(prohibited)
            )
        return value

    @model_validator(mode="after")
    def _require_field_specific_profile(self) -> "MLflowRedactedSample":
        expected_profile = _APPROVED_PROFILE_BY_FIELD[self.source_field]
        if self.redaction_profile != expected_profile:
            raise ValueError(
                "Redacted MLflow sample uses profile "
                f"{self.redaction_profile!r} for {self.source_field}; "
                f"expected {expected_profile!r}."
            )
        return self


class MLflowExportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: Optional["MLflowExportPayload"] = None
    suppressed: bool = False
    reasons: tuple[NonEmptyTrimmedString, ...] = Field(default_factory=tuple)
    safequery_audit_event_id: Optional[UUID] = None
    request_id: Optional[NonEmptyTrimmedString] = None
    evaluation_scenario_id: Optional[NonEmptyTrimmedString] = None

    @model_validator(mode="after")
    def _require_reason_for_suppression(self) -> "MLflowExportDecision":
        if self.suppressed and not self.reasons:
            raise ValueError("Suppressed MLflow exports must include a machine-readable reason.")
        if not self.suppressed and self.reasons:
            raise ValueError("Unsuppressed MLflow exports must not include suppression reasons.")
        return self


class MLflowExportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_schema_version: Literal[1] = 1
    export_kind: Literal["audit_trace", "evaluation_record"]
    authority: Literal["engineering_observability"] = "engineering_observability"
    can_authorize_or_mutate_audit: Literal[False] = False
    retention_days: PositiveInt = 30
    authoritative_audit_retention_days: PositiveInt = 90
    retention_extension_approval_id: Optional[NonEmptyTrimmedString] = None
    access_posture: Literal["approved_engineering_operations"] = (
        "approved_engineering_operations"
    )
    access_roles: tuple[AccessRole, ...] = ("engineering", "operations")

    safequery_audit_event_id: Optional[UUID] = None
    mlflow_run_id: Optional[NonEmptyTrimmedString] = None
    evaluation_run_id: Optional[NonEmptyTrimmedString] = None
    evaluation_outcome_id: Optional[NonEmptyTrimmedString] = None
    release_gate_summary_id: Optional[NonEmptyTrimmedString] = None

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
    validation_status: Optional[EvaluationValidationStatus] = None
    latency_ms: Optional[NonNegativeInt] = None
    prompt_token_count: Optional[NonNegativeInt] = None
    completion_token_count: Optional[NonNegativeInt] = None
    total_token_count: Optional[NonNegativeInt] = None
    row_count: Optional[NonNegativeInt] = None
    result_truncated: Optional[bool] = None

    prompt_version: Optional[NonEmptyTrimmedString] = None
    model_version: Optional[NonEmptyTrimmedString] = None
    application_version: Optional[NonEmptyTrimmedString] = None
    adapter_provider: Optional[NonEmptyTrimmedString] = None
    adapter_model: Optional[NonEmptyTrimmedString] = None
    adapter_version: Optional[NonEmptyTrimmedString] = None
    adapter_run_id: Optional[NonEmptyTrimmedString] = None

    evaluation_scenario_id: Optional[NonEmptyTrimmedString] = None
    evaluation_kind: Optional[EvaluationScenarioKind] = None
    evaluation_boundary: Optional[EvaluationBoundary] = None
    evaluation_artifact_link: Optional["MLflowEvaluationArtifactLink"] = None
    redacted_samples: tuple[MLflowRedactedSample, ...] = Field(default_factory=tuple)

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
        raw_path_fields = _raw_workstation_path_fields_in_mapping(value)
        if raw_path_fields:
            raise ValueError(
                "MLflow export payload includes raw workstation-local path field(s): "
                + ", ".join(raw_path_fields)
            )
        return value

    @model_validator(mode="after")
    def _validate_export_contract(self) -> "MLflowExportPayload":
        if self.export_kind == "audit_trace":
            if self.safequery_audit_event_id is None:
                raise ValueError("Audit trace exports must reference a SafeQuery audit event.")
            if self.request_id is None:
                raise ValueError("Audit trace exports must include a request identifier.")
        if self.export_kind == "evaluation_record":
            if self.mlflow_run_id is None:
                raise ValueError("Evaluation exports must include an MLflow run id.")
            if self.evaluation_scenario_id is None:
                raise ValueError("Evaluation exports must include an evaluation scenario id.")
            if self.evaluation_kind is None:
                raise ValueError("Evaluation exports must include an evaluation kind.")
            if self.evaluation_boundary is None:
                raise ValueError("Evaluation exports must include an evaluation boundary.")
            if self.evaluation_run_id is None:
                raise ValueError("Evaluation exports must include a SafeQuery evaluation run id.")
            if self.evaluation_outcome_id is None:
                raise ValueError("Evaluation exports must include a SafeQuery outcome id.")
            if self.evaluation_artifact_link is None:
                raise ValueError("Evaluation exports must include an artifact linkage record.")
            mismatches = self.evaluation_artifact_link.mismatches_for_payload(self)
            if mismatches:
                raise ValueError(
                    "Evaluation artifact link does not match export payload: "
                    + ", ".join(mismatches)
                )
            if self.total_token_count is not None and (
                self.prompt_token_count is not None
                and self.completion_token_count is not None
                and self.total_token_count
                != self.prompt_token_count + self.completion_token_count
            ):
                raise ValueError(
                    "Total token count must equal prompt and completion token counts."
                )
        if (
            self.retention_days > self.authoritative_audit_retention_days
            and self.retention_extension_approval_id is None
        ):
            raise ValueError(
                "MLflow retention must be equal to or shorter than authoritative audit "
                "retention unless an explicit approval id is present."
            )
        sample_reasons = _suppression_reasons_for_samples(self.redacted_samples)
        if sample_reasons:
            raise ValueError(
                "MLflow export payload includes unsafe redacted sample(s): "
                + ", ".join(sample_reasons)
            )
        return self


class MLflowEvaluationArtifactLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mlflow_run_id: NonEmptyTrimmedString
    evaluation_run_id: NonEmptyTrimmedString
    evaluation_scenario_id: NonEmptyTrimmedString
    evaluation_outcome_id: NonEmptyTrimmedString
    safequery_audit_event_id: Optional[UUID] = None
    release_gate_summary_id: Optional[NonEmptyTrimmedString] = None
    source_id: SourceIdentifier
    source_family: SourceFamily
    source_flavor: Optional[SourceFlavor] = None
    dataset_contract_version: PositiveInt
    schema_snapshot_version: PositiveInt
    execution_policy_version: PositiveInt
    connector_profile_version: Optional[PositiveInt] = None

    def mismatches_for_payload(self, payload: MLflowExportPayload) -> tuple[str, ...]:
        expected_values = {
            "mlflow_run_id": payload.mlflow_run_id,
            "evaluation_run_id": payload.evaluation_run_id,
            "evaluation_scenario_id": payload.evaluation_scenario_id,
            "evaluation_outcome_id": payload.evaluation_outcome_id,
            "safequery_audit_event_id": payload.safequery_audit_event_id,
            "release_gate_summary_id": payload.release_gate_summary_id,
            "source_id": payload.source_id,
            "source_family": payload.source_family,
            "source_flavor": payload.source_flavor,
            "dataset_contract_version": payload.dataset_contract_version,
            "schema_snapshot_version": payload.schema_snapshot_version,
            "execution_policy_version": payload.execution_policy_version,
            "connector_profile_version": payload.connector_profile_version,
        }
        return tuple(
            field_name
            for field_name, expected_value in expected_values.items()
            if getattr(self, field_name) != expected_value
        )


class _EvaluationScenario(Protocol):
    scenario_id: str
    kind: EvaluationScenarioKind
    evaluation_boundary: EvaluationBoundary
    source: object


def build_mlflow_export_from_audit_event(
    audit_event: SourceAwareAuditEvent,
    *,
    enabled: bool,
    retention_days: int = 30,
    authoritative_audit_retention_days: int = 90,
    retention_extension_approval_id: Optional[str] = None,
    access_roles: tuple[AccessRole, ...] = ("engineering", "operations"),
    redacted_samples: tuple[MLflowRedactedSample, ...] = (),
    latency_ms: Optional[int] = None,
    mlflow_run_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> Optional[MLflowExportPayload]:
    if not enabled:
        return None
    missing_required = [
        field_name
        for field_name, field_value in (
            ("dataset_contract_version", audit_event.dataset_contract_version),
            ("schema_snapshot_version", audit_event.schema_snapshot_version),
            ("execution_policy_version", audit_event.execution_policy_version),
        )
        if field_value is None
    ]
    if missing_required:
        raise ValueError(
            "Cannot build MLflow audit export without required source version fields: "
            + ", ".join(missing_required)
        )
    return MLflowExportPayload(
        export_kind="audit_trace",
        retention_days=retention_days,
        authoritative_audit_retention_days=authoritative_audit_retention_days,
        retention_extension_approval_id=retention_extension_approval_id,
        access_roles=access_roles,
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
        adapter_provider=audit_event.adapter_provider,
        adapter_model=audit_event.adapter_model,
        adapter_version=audit_event.adapter_version,
        adapter_run_id=audit_event.adapter_run_id,
        redacted_samples=redacted_samples,
    )


def prepare_mlflow_export_from_audit_event(
    audit_event: SourceAwareAuditEvent,
    *,
    enabled: bool,
    retention_days: int = 30,
    authoritative_audit_retention_days: int = 90,
    retention_extension_approval_id: Optional[str] = None,
    access_roles: tuple[AccessRole, ...] = ("engineering", "operations"),
    redacted_samples: tuple[MLflowRedactedSample, ...] = (),
    latency_ms: Optional[int] = None,
    mlflow_run_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> MLflowExportDecision:
    if not enabled:
        return MLflowExportDecision(
            payload=None,
            suppressed=False,
            safequery_audit_event_id=audit_event.event_id,
            request_id=audit_event.request_id,
        )
    reasons = _suppression_reasons_for_samples(redacted_samples)
    if reasons:
        return MLflowExportDecision(
            payload=None,
            suppressed=True,
            reasons=tuple(reasons),
            safequery_audit_event_id=audit_event.event_id,
            request_id=audit_event.request_id,
        )
    try:
        payload = build_mlflow_export_from_audit_event(
            audit_event,
            enabled=enabled,
            retention_days=retention_days,
            authoritative_audit_retention_days=authoritative_audit_retention_days,
            retention_extension_approval_id=retention_extension_approval_id,
            access_roles=access_roles,
            redacted_samples=redacted_samples,
            latency_ms=latency_ms,
            mlflow_run_id=mlflow_run_id,
            prompt_version=prompt_version,
            model_version=model_version,
        )
    except (ValueError, ValidationError) as exc:
        return MLflowExportDecision(
            payload=None,
            suppressed=True,
            reasons=(f"invalid_export_contract:{exc.__class__.__name__}",),
            safequery_audit_event_id=audit_event.event_id,
            request_id=audit_event.request_id,
        )
    return MLflowExportDecision(
        payload=payload,
        suppressed=False,
        safequery_audit_event_id=audit_event.event_id,
        request_id=audit_event.request_id,
    )


def export_adapter_run_trace_from_audit_event(
    audit_event: SourceAwareAuditEvent,
    *,
    enabled: bool,
    export_sink: Callable[[MLflowExportPayload], object] | None = None,
    retention_days: int = 30,
    authoritative_audit_retention_days: int = 90,
    retention_extension_approval_id: Optional[str] = None,
    access_roles: tuple[AccessRole, ...] = ("engineering", "operations"),
    redacted_samples: tuple[MLflowRedactedSample, ...] = (),
    latency_ms: Optional[int] = None,
    mlflow_run_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> MLflowExportDecision:
    decision = prepare_mlflow_export_from_audit_event(
        audit_event,
        enabled=enabled,
        retention_days=retention_days,
        authoritative_audit_retention_days=authoritative_audit_retention_days,
        retention_extension_approval_id=retention_extension_approval_id,
        access_roles=access_roles,
        redacted_samples=redacted_samples,
        latency_ms=latency_ms,
        mlflow_run_id=mlflow_run_id,
        prompt_version=prompt_version or audit_event.prompt_version,
        model_version=model_version,
    )
    if not enabled or decision.payload is None:
        return decision
    if export_sink is None:
        return MLflowExportDecision(
            payload=decision.payload,
            suppressed=True,
            reasons=("export_sink_missing",),
            safequery_audit_event_id=audit_event.event_id,
            request_id=audit_event.request_id,
        )

    try:
        export_sink(decision.payload)
    except Exception as exc:
        return MLflowExportDecision(
            payload=decision.payload,
            suppressed=True,
            reasons=(f"export_sink_failed:{exc.__class__.__name__}",),
            safequery_audit_event_id=audit_event.event_id,
            request_id=audit_event.request_id,
        )

    return decision


def build_mlflow_export_from_evaluation_scenario(
    scenario: _EvaluationScenario,
    *,
    enabled: bool,
    retention_days: int = 30,
    authoritative_audit_retention_days: int = 90,
    retention_extension_approval_id: Optional[str] = None,
    access_roles: tuple[AccessRole, ...] = ("engineering", "operations"),
    redacted_samples: tuple[MLflowRedactedSample, ...] = (),
    mlflow_run_id: Optional[str] = None,
    evaluation_run_id: Optional[str] = None,
    evaluation_outcome_id: Optional[str] = None,
    safequery_audit_event_id: Optional[UUID] = None,
    release_gate_summary_id: Optional[str] = None,
    deny_code: Optional[str] = None,
    validation_status: Optional[EvaluationValidationStatus] = None,
    latency_ms: Optional[int] = None,
    prompt_token_count: Optional[int] = None,
    completion_token_count: Optional[int] = None,
    total_token_count: Optional[int] = None,
    row_count: Optional[int] = None,
    result_truncated: Optional[bool] = None,
    prompt_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> Optional[MLflowExportPayload]:
    if not enabled:
        return None
    source = scenario.source
    artifact_link = (
        MLflowEvaluationArtifactLink(
            mlflow_run_id=mlflow_run_id,
            evaluation_run_id=evaluation_run_id,
            evaluation_scenario_id=scenario.scenario_id,
            evaluation_outcome_id=evaluation_outcome_id,
            safequery_audit_event_id=safequery_audit_event_id,
            release_gate_summary_id=release_gate_summary_id,
            source_id=source.source_id,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
            dataset_contract_version=source.dataset_contract_version,
            schema_snapshot_version=source.schema_snapshot_version,
            execution_policy_version=source.execution_policy_version,
            connector_profile_version=source.connector_profile_version,
        )
        if mlflow_run_id is not None
        and evaluation_run_id is not None
        and evaluation_outcome_id is not None
        else None
    )
    return MLflowExportPayload(
        export_kind="evaluation_record",
        retention_days=retention_days,
        authoritative_audit_retention_days=authoritative_audit_retention_days,
        retention_extension_approval_id=retention_extension_approval_id,
        access_roles=access_roles,
        safequery_audit_event_id=safequery_audit_event_id,
        mlflow_run_id=mlflow_run_id,
        evaluation_run_id=evaluation_run_id,
        evaluation_outcome_id=evaluation_outcome_id,
        release_gate_summary_id=release_gate_summary_id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dataset_contract_version=source.dataset_contract_version,
        schema_snapshot_version=source.schema_snapshot_version,
        execution_policy_version=source.execution_policy_version,
        connector_profile_version=source.connector_profile_version,
        deny_code=deny_code,
        validation_status=validation_status,
        latency_ms=latency_ms,
        prompt_token_count=prompt_token_count,
        completion_token_count=completion_token_count,
        total_token_count=total_token_count,
        row_count=row_count,
        result_truncated=result_truncated,
        prompt_version=prompt_version,
        model_version=model_version,
        evaluation_scenario_id=scenario.scenario_id,
        evaluation_kind=scenario.kind,
        evaluation_boundary=scenario.evaluation_boundary,
        evaluation_artifact_link=artifact_link,
        redacted_samples=redacted_samples,
    )


def prepare_mlflow_export_from_evaluation_scenario(
    scenario: _EvaluationScenario,
    *,
    enabled: bool,
    retention_days: int = 30,
    authoritative_audit_retention_days: int = 90,
    retention_extension_approval_id: Optional[str] = None,
    access_roles: tuple[AccessRole, ...] = ("engineering", "operations"),
    redacted_samples: tuple[MLflowRedactedSample, ...] = (),
    mlflow_run_id: Optional[str] = None,
    evaluation_run_id: Optional[str] = None,
    evaluation_outcome_id: Optional[str] = None,
    safequery_audit_event_id: Optional[UUID] = None,
    release_gate_summary_id: Optional[str] = None,
    deny_code: Optional[str] = None,
    validation_status: Optional[EvaluationValidationStatus] = None,
    latency_ms: Optional[int] = None,
    prompt_token_count: Optional[int] = None,
    completion_token_count: Optional[int] = None,
    total_token_count: Optional[int] = None,
    row_count: Optional[int] = None,
    result_truncated: Optional[bool] = None,
    prompt_version: Optional[str] = None,
    model_version: Optional[str] = None,
) -> MLflowExportDecision:
    if not enabled:
        return MLflowExportDecision(
            payload=None,
            suppressed=False,
            evaluation_scenario_id=scenario.scenario_id,
        )
    reasons = _suppression_reasons_for_samples(redacted_samples)
    if reasons:
        return MLflowExportDecision(
            payload=None,
            suppressed=True,
            reasons=tuple(reasons),
            evaluation_scenario_id=scenario.scenario_id,
        )
    try:
        payload = build_mlflow_export_from_evaluation_scenario(
            scenario,
            enabled=enabled,
            retention_days=retention_days,
            authoritative_audit_retention_days=authoritative_audit_retention_days,
            retention_extension_approval_id=retention_extension_approval_id,
            access_roles=access_roles,
            redacted_samples=redacted_samples,
            mlflow_run_id=mlflow_run_id,
            evaluation_run_id=evaluation_run_id,
            evaluation_outcome_id=evaluation_outcome_id,
            safequery_audit_event_id=safequery_audit_event_id,
            release_gate_summary_id=release_gate_summary_id,
            deny_code=deny_code,
            validation_status=validation_status,
            latency_ms=latency_ms,
            prompt_token_count=prompt_token_count,
            completion_token_count=completion_token_count,
            total_token_count=total_token_count,
            row_count=row_count,
            result_truncated=result_truncated,
            prompt_version=prompt_version,
            model_version=model_version,
        )
    except (ValueError, ValidationError) as exc:
        return MLflowExportDecision(
            payload=None,
            suppressed=True,
            reasons=(f"invalid_export_contract:{exc.__class__.__name__}",),
            evaluation_scenario_id=scenario.scenario_id,
        )
    return MLflowExportDecision(
        payload=payload,
        suppressed=False,
        evaluation_scenario_id=scenario.scenario_id,
    )


def _suppression_reasons_for_samples(
    samples: tuple[MLflowRedactedSample, ...],
) -> list[str]:
    reasons: list[str] = []
    for sample in samples:
        if any(pattern.search(sample.value) for pattern in _PROHIBITED_SAMPLE_PATTERNS):
            reasons.append(f"prohibited_pattern_detected:{sample.source_field}")
        metadata_fields = _prohibited_export_fields_in_mapping(sample.source_metadata)
        if metadata_fields:
            reasons.append(
                "prohibited_metadata_field_detected:"
                f"{sample.source_field}:{','.join(metadata_fields)}"
            )
    return reasons


def _prohibited_export_fields_in_mapping(value: object) -> tuple[str, ...]:
    prohibited: set[str] = set()

    def collect(candidate: object) -> None:
        if isinstance(candidate, Mapping):
            for key, nested_value in candidate.items():
                if isinstance(key, str) and key in PROHIBITED_EXPORT_FIELDS:
                    prohibited.add(key)
                collect(nested_value)
        elif isinstance(candidate, (list, tuple)):
            for item in candidate:
                collect(item)

    collect(value)
    return tuple(sorted(prohibited))


def _raw_workstation_path_fields_in_mapping(value: object) -> tuple[str, ...]:
    fields: set[str] = set()

    def collect(candidate: object, field_name: str | None = None) -> None:
        if isinstance(candidate, Mapping):
            for key, nested_value in candidate.items():
                collect(nested_value, key if isinstance(key, str) else field_name)
        elif isinstance(candidate, (list, tuple)):
            for item in candidate:
                collect(item, field_name)
        elif isinstance(candidate, str) and any(
            pattern.search(candidate) for pattern in _RAW_WORKSTATION_PATH_PATTERNS
        ):
            fields.add(field_name or "<unknown>")

    collect(value)
    return tuple(sorted(fields))
