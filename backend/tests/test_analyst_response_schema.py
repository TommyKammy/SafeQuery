from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.analyst_response.schema import AnalystResponsePayload


def _citation(source_id: str, source_family: str) -> dict[str, object]:
    return {
        "asset_id": f"{source_id}-metric-definition",
        "asset_kind": "metric_definition",
        "citation_label": f"{source_id} metric definition",
        "source_id": source_id,
        "source_family": source_family,
        "source_flavor": "warehouse" if source_family == "postgresql" else "sqlserver",
        "dataset_contract_version": 2,
        "schema_snapshot_version": 5,
        "authority": "advisory_context",
        "can_authorize_execution": False,
    }


def _executed_evidence(source_id: str, source_family: str) -> dict[str, object]:
    return {
        "type": "executed_evidence",
        "source_id": source_id,
        "source_family": source_family,
        "source_flavor": "warehouse" if source_family == "postgresql" else "sqlserver",
        "dataset_contract_version": 2,
        "schema_snapshot_version": 5,
        "execution_policy_version": 3,
        "connector_profile_version": 11,
        "candidate_id": f"{source_id}-candidate-123",
        "execution_audit_event_id": uuid4(),
        "execution_audit_event_type": "execution_completed",
        "row_count": 12,
        "result_truncated": False,
        "authority": "backend_execution_result",
        "can_authorize_execution": False,
    }


def test_analyst_response_payload_preserves_multi_source_advisory_labels() -> None:
    response = AnalystResponsePayload(
        response_id="analyst-response-123",
        request_id="request-123",
        narrative="PostgreSQL and MSSQL advisory context differ; execution evidence stays source-labeled.",
        advisory_only=True,
        can_authorize_execution=False,
        analyst_mode_version="analyst-schema-v1",
        confidence="medium",
        caveats=["Advisory narrative does not approve SQL execution."],
        retrieval_citations=[
            _citation("business-postgres-source", "postgresql"),
            _citation("business-mssql-source", "mssql"),
        ],
        executed_evidence=[
            _executed_evidence("business-postgres-source", "postgresql"),
            _executed_evidence("business-mssql-source", "mssql"),
        ],
        operator_history_hooks={
            "audit_event_id": uuid4(),
            "history_record_ids": ["request-123", "business-postgres-source-candidate-123"],
        },
    )

    dumped = response.model_dump()

    assert dumped["advisory_only"] is True
    assert dumped["can_authorize_execution"] is False
    assert [item["source_id"] for item in dumped["retrieval_citations"]] == [
        "business-postgres-source",
        "business-mssql-source",
    ]
    assert [item["source_id"] for item in dumped["executed_evidence"]] == [
        "business-postgres-source",
        "business-mssql-source",
    ]
    assert "approval_status" not in dumped
    assert "sql_execution_approved" not in dumped


def test_source_summary_coverage_uses_source_identity_not_execution_policy() -> None:
    response = AnalystResponsePayload(
        response_id="analyst-response-123",
        request_id="request-123",
        narrative="A single source can have advisory citations and executed evidence.",
        advisory_only=True,
        can_authorize_execution=False,
        analyst_mode_version="analyst-schema-v1",
        source_summaries=[
            {
                "source_id": "business-postgres-source",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
                "dataset_contract_version": 2,
                "schema_snapshot_version": 5,
            }
        ],
        retrieval_citations=[_citation("business-postgres-source", "postgresql")],
        executed_evidence=[_executed_evidence("business-postgres-source", "postgresql")],
    )

    assert response.source_summaries[0].execution_policy_version is None


def test_source_summary_coverage_rejects_missing_source_identity() -> None:
    with pytest.raises(ValidationError):
        AnalystResponsePayload(
            response_id="analyst-response-123",
            request_id="request-123",
            narrative="All cited sources must be summarized when summaries are supplied.",
            advisory_only=True,
            can_authorize_execution=False,
            analyst_mode_version="analyst-schema-v1",
            source_summaries=[
                {
                    "source_id": "business-postgres-source",
                    "source_family": "postgresql",
                    "source_flavor": "warehouse",
                    "dataset_contract_version": 2,
                    "schema_snapshot_version": 5,
                }
            ],
            retrieval_citations=[
                _citation("business-postgres-source", "postgresql"),
                _citation("business-mssql-source", "mssql"),
            ],
        )


def test_source_summary_requires_dataset_and_schema_versions() -> None:
    with pytest.raises(ValidationError):
        AnalystResponsePayload(
            response_id="analyst-response-123",
            request_id="request-123",
            narrative="Source summaries must identify the concrete governed source versions.",
            advisory_only=True,
            can_authorize_execution=False,
            analyst_mode_version="analyst-schema-v1",
            source_summaries=[
                {
                    "source_id": "business-postgres-source",
                    "source_family": "postgresql",
                    "source_flavor": "warehouse",
                }
            ],
            retrieval_citations=[_citation("business-postgres-source", "postgresql")],
        )


@pytest.mark.parametrize(
    "payload_overrides",
    [
        {"advisory_only": False},
        {"can_authorize_execution": True},
        {
            "retrieval_citations": [
                {
                    **_citation("business-postgres-source", "postgresql"),
                    "source_id": " business-postgres-source ",
                }
            ]
        },
    ],
)
def test_analyst_response_payload_rejects_execution_authority_and_bad_source_labels(
    payload_overrides: dict[str, object],
) -> None:
    payload = {
        "response_id": "analyst-response-123",
        "request_id": "request-123",
        "narrative": "Advisory answer with source-labeled context.",
        "advisory_only": True,
        "can_authorize_execution": False,
        "analyst_mode_version": "analyst-schema-v1",
        "retrieval_citations": [_citation("business-postgres-source", "postgresql")],
        "executed_evidence": [_executed_evidence("business-postgres-source", "postgresql")],
        **payload_overrides,
    }

    with pytest.raises(ValidationError):
        AnalystResponsePayload(**payload)
