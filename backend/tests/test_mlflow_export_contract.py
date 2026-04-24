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
    MLflowExportPayload,
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
        evaluation_run_id="evaluation-run-123",
        latency_ms=55,
        row_count=10,
        result_truncated=False,
    )
    postgresql_payload = build_mlflow_export_from_evaluation_scenario(
        postgresql_scenario,
        enabled=True,
        evaluation_run_id="evaluation-run-123",
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
        "evaluation_run_id": "evaluation-run-123",
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
    }
    assert postgresql_payload.model_dump(exclude_none=True) == {
        "export_schema_version": 1,
        "export_kind": "evaluation_record",
        "authority": "engineering_observability",
        "can_authorize_or_mutate_audit": False,
        "evaluation_run_id": "evaluation-run-123",
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
    }


@pytest.mark.parametrize(
    "prohibited_field",
    [
        "credentials",
        "connection_string",
        "raw_result_set",
        "controlled_corpus_body",
        "natural_language_request",
        "canonical_sql",
        "identity_claims",
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

    with pytest.raises(ValidationError):
        MLflowExportPayload(**payload)


def test_mlflow_export_payload_rejects_mlflow_as_audit_authority() -> None:
    with pytest.raises(ValidationError):
        MLflowExportPayload(
            export_kind="audit_trace",
            authority="authoritative_audit",
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
