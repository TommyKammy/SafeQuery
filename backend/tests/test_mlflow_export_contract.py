from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.features.audit import SourceAwareAuditEvent
from app.features.evaluation import (
    list_mssql_evaluation_scenarios,
    list_postgresql_evaluation_scenarios,
)
from app.features.mlflow_export import (
    MLflowEvaluationArtifactLink,
    MLflowRedactedSample,
    MLflowExportPayload,
    prepare_mlflow_export_from_audit_event,
    prepare_mlflow_export_from_evaluation_scenario,
    build_mlflow_export_from_audit_event,
    build_mlflow_export_from_evaluation_scenario,
)


def _execution_audit_event(**overrides: object) -> SourceAwareAuditEvent:
    payload: dict[str, object] = {
        "event_id": uuid4(),
        "event_type": "execution_completed",
        "occurred_at": datetime.now(timezone.utc),
        "request_id": "request-123",
        "correlation_id": "correlation-123",
        "user_subject": "user:alice",
        "session_id": "session-123",
        "query_candidate_id": "candidate-123",
        "adapter_version": "adapter-v1",
        "application_version": "app-v1",
        "source_id": "business-mssql-source",
        "source_family": "mssql",
        "source_flavor": "sqlserver",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": 2,
        "connector_profile_version": 1,
        "execution_row_count": 10,
        "result_truncated": False,
    }
    payload.update(overrides)
    return SourceAwareAuditEvent(**payload)


def test_mlflow_export_payload_serializes_source_aware_audit_metadata() -> None:
    audit_event = _execution_audit_event()

    payload = build_mlflow_export_from_audit_event(
        audit_event,
        enabled=True,
        latency_ms=42,
        mlflow_run_id="mlflow-run-123",
        prompt_version="prompt-v1",
        model_version="model-v1",
    )

    assert payload is not None
    serialized = payload.model_dump(exclude_none=True)
    assert serialized == {
        "export_schema_version": 1,
        "export_kind": "audit_trace",
        "authority": "engineering_observability",
        "can_authorize_or_mutate_audit": False,
        "retention_days": 30,
        "authoritative_audit_retention_days": 90,
        "access_posture": "approved_engineering_operations",
        "access_roles": ("engineering", "operations"),
        "safequery_audit_event_id": audit_event.event_id,
        "mlflow_run_id": "mlflow-run-123",
        "request_id": "request-123",
        "candidate_id": "candidate-123",
        "source_id": "business-mssql-source",
        "source_family": "mssql",
        "source_flavor": "sqlserver",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": 2,
        "connector_profile_version": 1,
        "latency_ms": 42,
        "row_count": 10,
        "result_truncated": False,
        "prompt_version": "prompt-v1",
        "model_version": "model-v1",
        "application_version": "app-v1",
        "adapter_version": "adapter-v1",
        "redacted_samples": (),
    }
    assert "canonical_sql" not in serialized
    assert "raw_result_set" not in serialized
    assert "user_subject" not in serialized
    assert serialized["safequery_audit_event_id"] != serialized["mlflow_run_id"]


def test_mlflow_export_audit_builder_rejects_missing_source_versions() -> None:
    audit_event = _execution_audit_event(
        dataset_contract_version=None,
        schema_snapshot_version=None,
        execution_policy_version=None,
    )

    with pytest.raises(ValueError) as exc_info:
        build_mlflow_export_from_audit_event(audit_event, enabled=True)

    assert str(exc_info.value) == (
        "Cannot build MLflow audit export without required source version fields: "
        "dataset_contract_version, schema_snapshot_version, execution_policy_version"
    )


def test_mlflow_export_payload_serializes_mssql_and_postgresql_evaluation_metadata() -> None:
    mssql_scenario = list_mssql_evaluation_scenarios()[0]
    postgresql_scenario = list_postgresql_evaluation_scenarios()[0]

    mssql_payload = build_mlflow_export_from_evaluation_scenario(
        mssql_scenario,
        enabled=True,
        mlflow_run_id="mlflow-run-123",
        evaluation_run_id="evaluation-run-123",
        evaluation_outcome_id="mssql-outcome-123",
        latency_ms=55,
        row_count=10,
        result_truncated=False,
    )
    postgresql_payload = build_mlflow_export_from_evaluation_scenario(
        postgresql_scenario,
        enabled=True,
        mlflow_run_id="mlflow-run-456",
        evaluation_run_id="evaluation-run-123",
        evaluation_outcome_id="postgresql-outcome-123",
        deny_code="DENY_TEST",
        latency_ms=20,
        result_truncated=True,
    )

    assert mssql_payload is not None
    assert postgresql_payload is not None
    assert mssql_payload.model_dump(exclude_none=True) == {
        "export_schema_version": 1,
        "export_kind": "evaluation_record",
        "authority": "engineering_observability",
        "can_authorize_or_mutate_audit": False,
        "retention_days": 30,
        "authoritative_audit_retention_days": 90,
        "access_posture": "approved_engineering_operations",
        "access_roles": ("engineering", "operations"),
        "mlflow_run_id": "mlflow-run-123",
        "evaluation_run_id": "evaluation-run-123",
        "evaluation_outcome_id": "mssql-outcome-123",
        "source_id": "business-mssql-source",
        "source_family": "mssql",
        "source_flavor": "sqlserver",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": 2,
        "connector_profile_version": 1,
        "latency_ms": 55,
        "row_count": 10,
        "result_truncated": False,
        "evaluation_scenario_id": mssql_scenario.scenario_id,
        "evaluation_kind": "positive",
        "evaluation_boundary": "execution",
        "evaluation_artifact_link": {
            "mlflow_run_id": "mlflow-run-123",
            "evaluation_run_id": "evaluation-run-123",
            "evaluation_scenario_id": mssql_scenario.scenario_id,
            "evaluation_outcome_id": "mssql-outcome-123",
            "source_id": "business-mssql-source",
            "source_family": "mssql",
            "source_flavor": "sqlserver",
            "dataset_contract_version": 3,
            "schema_snapshot_version": 7,
            "execution_policy_version": 2,
            "connector_profile_version": 1,
        },
        "redacted_samples": (),
    }
    assert postgresql_payload.model_dump(exclude_none=True) == {
        "export_schema_version": 1,
        "export_kind": "evaluation_record",
        "authority": "engineering_observability",
        "can_authorize_or_mutate_audit": False,
        "retention_days": 30,
        "authoritative_audit_retention_days": 90,
        "access_posture": "approved_engineering_operations",
        "access_roles": ("engineering", "operations"),
        "mlflow_run_id": "mlflow-run-456",
        "evaluation_run_id": "evaluation-run-123",
        "evaluation_outcome_id": "postgresql-outcome-123",
        "source_id": "business-postgres-source",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "dataset_contract_version": 4,
        "schema_snapshot_version": 9,
        "execution_policy_version": 3,
        "connector_profile_version": 1,
        "deny_code": "DENY_TEST",
        "latency_ms": 20,
        "result_truncated": True,
        "evaluation_scenario_id": postgresql_scenario.scenario_id,
        "evaluation_kind": "positive",
        "evaluation_boundary": "execution",
        "evaluation_artifact_link": {
            "mlflow_run_id": "mlflow-run-456",
            "evaluation_run_id": "evaluation-run-123",
            "evaluation_scenario_id": postgresql_scenario.scenario_id,
            "evaluation_outcome_id": "postgresql-outcome-123",
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
            "dataset_contract_version": 4,
            "schema_snapshot_version": 9,
            "execution_policy_version": 3,
            "connector_profile_version": 1,
        },
        "redacted_samples": (),
    }


def test_mlflow_evaluation_export_links_run_to_authoritative_artifacts() -> None:
    scenario = list_mssql_evaluation_scenarios()[0]
    audit_event_id = uuid4()

    payload = build_mlflow_export_from_evaluation_scenario(
        scenario,
        enabled=True,
        mlflow_run_id="mlflow-run-123",
        evaluation_run_id="evaluation-run-123",
        evaluation_outcome_id="outcome-123",
        safequery_audit_event_id=audit_event_id,
        release_gate_summary_id="release-gate-summary-123",
        validation_status="passed",
        latency_ms=55,
        prompt_token_count=100,
        completion_token_count=20,
        total_token_count=120,
        row_count=10,
        result_truncated=False,
    )

    assert payload is not None
    serialized = payload.model_dump(exclude_none=True)
    assert serialized["mlflow_run_id"] == "mlflow-run-123"
    assert serialized["evaluation_run_id"] == "evaluation-run-123"
    assert serialized["safequery_audit_event_id"] == audit_event_id
    assert serialized["evaluation_outcome_id"] == "outcome-123"
    assert serialized["release_gate_summary_id"] == "release-gate-summary-123"
    assert serialized["validation_status"] == "passed"
    assert serialized["prompt_token_count"] == 100
    assert serialized["completion_token_count"] == 20
    assert serialized["total_token_count"] == 120
    assert serialized["evaluation_artifact_link"] == {
        "mlflow_run_id": "mlflow-run-123",
        "evaluation_run_id": "evaluation-run-123",
        "evaluation_scenario_id": scenario.scenario_id,
        "evaluation_outcome_id": "outcome-123",
        "safequery_audit_event_id": audit_event_id,
        "release_gate_summary_id": "release-gate-summary-123",
        "source_id": "business-mssql-source",
        "source_family": "mssql",
        "source_flavor": "sqlserver",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": 2,
        "connector_profile_version": 1,
    }
    assert serialized["can_authorize_or_mutate_audit"] is False


def test_mlflow_evaluation_export_rejects_missing_run_linkage() -> None:
    scenario = list_mssql_evaluation_scenarios()[0]

    with pytest.raises(ValidationError) as exc_info:
        build_mlflow_export_from_evaluation_scenario(
            scenario,
            enabled=True,
            evaluation_run_id="evaluation-run-123",
            evaluation_outcome_id="outcome-123",
        )

    assert "Evaluation exports must include an MLflow run id." in str(exc_info.value)


def test_mlflow_evaluation_export_rejects_mismatched_artifact_link_source() -> None:
    scenario = list_mssql_evaluation_scenarios()[0]

    with pytest.raises(ValidationError) as exc_info:
        MLflowExportPayload(
            export_kind="evaluation_record",
            mlflow_run_id="mlflow-run-123",
            evaluation_run_id="evaluation-run-123",
            evaluation_outcome_id="outcome-123",
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
            dataset_contract_version=3,
            schema_snapshot_version=7,
            execution_policy_version=2,
            connector_profile_version=1,
            evaluation_scenario_id=scenario.scenario_id,
            evaluation_kind=scenario.kind,
            evaluation_boundary=scenario.evaluation_boundary,
            evaluation_artifact_link=MLflowEvaluationArtifactLink(
                mlflow_run_id="mlflow-run-123",
                evaluation_run_id="evaluation-run-123",
                evaluation_scenario_id=scenario.scenario_id,
                evaluation_outcome_id="outcome-123",
                source_id="business-postgres-source",
                source_family="postgresql",
                source_flavor="warehouse",
                dataset_contract_version=4,
                schema_snapshot_version=9,
                execution_policy_version=3,
                connector_profile_version=1,
            ),
        )

    assert "Evaluation artifact link does not match export payload" in str(exc_info.value)
    assert "source_id" in str(exc_info.value)
    assert "dataset_contract_version" in str(exc_info.value)


def test_mlflow_evaluation_export_rejects_inconsistent_token_counts() -> None:
    scenario = list_mssql_evaluation_scenarios()[0]

    with pytest.raises(ValidationError) as exc_info:
        build_mlflow_export_from_evaluation_scenario(
            scenario,
            enabled=True,
            mlflow_run_id="mlflow-run-123",
            evaluation_run_id="evaluation-run-123",
            evaluation_outcome_id="outcome-123",
            prompt_token_count=100,
            completion_token_count=20,
            total_token_count=119,
        )

    assert "Total token count must equal prompt and completion token counts." in str(
        exc_info.value
    )


@pytest.mark.parametrize(
    "prohibited_field",
    [
        "credentials",
        "connection_string",
        "raw_result_set",
        "controlled_corpus_body",
        "natural_language_request",
        "canonical_sql",
        "candidate_state",
        "execution_approval_state",
        "guard_decision",
        "identity_claims",
        "release_gate_status",
        "runtime_safety_state",
        "sql_guard_decision",
    ],
)
def test_mlflow_export_payload_rejects_prohibited_data_classes(
    prohibited_field: str,
) -> None:
    payload = {
        "export_kind": "audit_trace",
        "safequery_audit_event_id": uuid4(),
        "request_id": "request-123",
        "source_id": "business-mssql-source",
        "source_family": "mssql",
        "source_flavor": "sqlserver",
        "dataset_contract_version": 3,
        "schema_snapshot_version": 7,
        "execution_policy_version": 2,
        prohibited_field: "blocked",
    }

    with pytest.raises(ValidationError) as exc_info:
        MLflowExportPayload(**payload)

    assert (
        f"MLflow export payload includes prohibited field(s): {prohibited_field}"
        in str(exc_info.value)
    )


def test_mlflow_export_payload_rejects_mlflow_as_audit_authority() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MLflowExportPayload(
            export_kind="audit_trace",
            authority="engineering_observability",
            can_authorize_or_mutate_audit=True,
            safequery_audit_event_id=uuid4(),
            request_id="request-123",
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
            dataset_contract_version=3,
            schema_snapshot_version=7,
            execution_policy_version=2,
        )

    assert any(
        error["loc"] == ("can_authorize_or_mutate_audit",)
        for error in exc_info.value.errors()
    )


def test_mlflow_export_payload_rejects_retention_longer_than_audit_without_approval() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MLflowExportPayload(
            export_kind="audit_trace",
            safequery_audit_event_id=uuid4(),
            request_id="request-123",
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
            dataset_contract_version=3,
            schema_snapshot_version=7,
            execution_policy_version=2,
            retention_days=120,
            authoritative_audit_retention_days=90,
        )

    assert "MLflow retention must be equal to or shorter" in str(exc_info.value)


def test_mlflow_export_rejects_unapproved_access_roles() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MLflowExportPayload(
            export_kind="audit_trace",
            safequery_audit_event_id=uuid4(),
            request_id="request-123",
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
            dataset_contract_version=3,
            schema_snapshot_version=7,
            execution_policy_version=2,
            access_roles=("engineering", "public"),
        )

    assert any(error["loc"] == ("access_roles", 1) for error in exc_info.value.errors())


def test_mlflow_export_preserves_safe_redacted_samples_and_source_metadata() -> None:
    audit_event = _execution_audit_event()

    payload = build_mlflow_export_from_audit_event(
        audit_event,
        enabled=True,
        redacted_samples=(
            MLflowRedactedSample(
                source_field="sql_snippet",
                redaction_profile="sql_snippet_v1",
                value="SELECT vendor_name FROM approved_vendor_spend LIMIT 10",
                source_metadata={
                    "source_id": audit_event.source_id,
                    "schema_snapshot_version": audit_event.schema_snapshot_version,
                    "column_count": 1,
                },
            ),
        ),
    )

    assert payload is not None
    assert payload.redacted_samples[0].model_dump() == {
        "source_field": "sql_snippet",
        "redaction_profile": "sql_snippet_v1",
        "value": "SELECT vendor_name FROM approved_vendor_spend LIMIT 10",
        "source_metadata": {
            "source_id": "business-mssql-source",
            "schema_snapshot_version": 7,
            "column_count": 1,
        },
    }


@pytest.mark.parametrize(
    "builder",
    [
        lambda: build_mlflow_export_from_audit_event(_execution_audit_event(), enabled=False),
        lambda: build_mlflow_export_from_evaluation_scenario(
            list_mssql_evaluation_scenarios()[0],
            enabled=False,
        ),
    ],
)
def test_mlflow_export_can_be_disabled_without_creating_payload(
    builder: Callable[[], object],
) -> None:
    assert builder() is None


def test_mlflow_export_payload_keeps_audit_reference_typed() -> None:
    audit_event_id = uuid4()

    payload = MLflowExportPayload(
        export_kind="audit_trace",
        safequery_audit_event_id=audit_event_id,
        request_id="request-123",
        source_id="business-postgres-source",
        source_family="postgresql",
        source_flavor="warehouse",
        dataset_contract_version=4,
        schema_snapshot_version=9,
        execution_policy_version=3,
    )

    assert isinstance(payload.safequery_audit_event_id, UUID)
    assert payload.safequery_audit_event_id == audit_event_id


def test_mlflow_export_suppresses_unredacted_sample_without_blocking_audit() -> None:
    audit_event = _execution_audit_event()

    decision = prepare_mlflow_export_from_audit_event(
        audit_event,
        enabled=True,
        redacted_samples=[
            MLflowRedactedSample(
                source_field="natural_language_request",
                redaction_profile="nl_excerpt_v1",
                value="Show spend for alice@example.com with password=hunter2",
                source_metadata={"request_id": audit_event.request_id},
            )
        ],
    )

    assert decision.payload is None
    assert decision.suppressed is True
    assert decision.reasons == ("prohibited_pattern_detected:natural_language_request",)
    assert decision.safequery_audit_event_id == audit_event.event_id
    assert decision.request_id == audit_event.request_id


def test_mlflow_export_suppresses_unsafe_evaluation_diagnostic() -> None:
    scenario = list_mssql_evaluation_scenarios()[0]

    decision = prepare_mlflow_export_from_evaluation_scenario(
        scenario,
        enabled=True,
        redacted_samples=(
            MLflowRedactedSample(
                source_field="evaluation_diagnostic",
                redaction_profile="evaluation_diagnostic_v1",
                value="connector failed with token=sample-token",
                source_metadata={"scenario_id": scenario.scenario_id},
            ),
        ),
    )

    assert decision.payload is None
    assert decision.suppressed is True
    assert decision.reasons == ("prohibited_pattern_detected:evaluation_diagnostic",)
    assert decision.evaluation_scenario_id == scenario.scenario_id


def test_mlflow_export_suppresses_invalid_evaluation_contract_without_throwing() -> None:
    scenario = list_mssql_evaluation_scenarios()[0]

    decision = prepare_mlflow_export_from_evaluation_scenario(
        scenario,
        enabled=True,
        retention_days=120,
        authoritative_audit_retention_days=90,
    )

    assert decision.payload is None
    assert decision.suppressed is True
    assert decision.reasons == ("invalid_export_contract:ValidationError",)
    assert decision.evaluation_scenario_id == scenario.scenario_id
