from app.services.generation_context import (
    GenerationContextGovernance,
    GenerationContextRequest,
    GenerationContextSource,
    PreparedGenerationContext,
)
from app.services.sql_generation_adapter import (
    SQLGenerationAdapterRequest,
    build_sql_generation_adapter_request,
)


def test_build_sql_generation_adapter_request_uses_only_adapter_safe_fields() -> None:
    prepared_context = PreparedGenerationContext(
        request=GenerationContextRequest(
            request_id="req_82_preview",
            question="Show approved vendors by quarterly spend",
        ),
        source=GenerationContextSource(
            source_id="sap-approved-spend",
            display_label="SAP Approved Spend",
            source_family="postgresql",
            source_flavor="warehouse",
        ),
        governance=GenerationContextGovernance(
            dataset_contract_id="contract_finance_v1",
            schema_snapshot_id="snapshot_finance_v3",
        ),
        datasets=[],
    )

    adapter_request = build_sql_generation_adapter_request(prepared_context)

    assert isinstance(adapter_request, SQLGenerationAdapterRequest)
    assert adapter_request.model_dump() == {
        "request_id": "req_82_preview",
        "question": "Show approved vendors by quarterly spend",
        "source": {
            "source_id": "sap-approved-spend",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        },
        "context": {
            "dataset_contract": {
                "context_id": "contract_finance_v1",
                "source_id": "sap-approved-spend",
            },
            "schema_snapshot": {
                "context_id": "snapshot_finance_v3",
                "source_id": "sap-approved-spend",
            },
            "glossary": None,
            "policy": None,
        },
    }
    dumped = adapter_request.model_dump()
    assert "display_label" not in str(dumped)
    assert "datasets" not in dumped
    assert "connection_reference" not in str(dumped)
    assert "connector_profile_id" not in str(dumped)
    assert "execution_policy_id" not in str(dumped)
