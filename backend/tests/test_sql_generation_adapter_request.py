from pydantic import ValidationError

from app.services.sql_generation_adapter import (
    SQLGenerationAdapterRequest,
    SQLGenerationContextReferences,
    SQLGenerationSourceBinding,
)


def test_sql_generation_adapter_request_is_source_aware_and_single_source() -> None:
    request = SQLGenerationAdapterRequest(
        request_id="req_79_preview",
        question="Show approved vendors by quarterly spend",
        source=SQLGenerationSourceBinding(
            source_id="sap-approved-spend",
            source_family="postgresql",
            source_flavor="warehouse",
        ),
        context=SQLGenerationContextReferences(
            dataset_contract={
                "context_id": "contract_finance_v1",
                "source_id": "sap-approved-spend",
            },
            schema_snapshot={
                "context_id": "snapshot_finance_v3",
                "source_id": "sap-approved-spend",
            },
            glossary={
                "context_id": "glossary_finance_v2",
                "source_id": "sap-approved-spend",
            },
            policy={
                "context_id": "policy_generation_v1",
                "source_id": "sap-approved-spend",
            },
        ),
    )

    assert request.model_dump() == {
        "request_id": "req_79_preview",
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
            "glossary": {
                "context_id": "glossary_finance_v2",
                "source_id": "sap-approved-spend",
            },
            "policy": {
                "context_id": "policy_generation_v1",
                "source_id": "sap-approved-spend",
            },
        },
    }


def test_sql_generation_adapter_request_rejects_credentials_and_unbounded_context() -> None:
    try:
        SQLGenerationAdapterRequest.model_validate(
            {
                "request_id": "req_79_preview",
                "question": "Show approved vendors by quarterly spend",
                "source": {
                    "source_id": "sap-approved-spend",
                    "source_family": "postgresql",
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
                },
                "credentials": {
                    "username": "analyst",
                    "password": "not-allowed",
                },
                "execution_authority": True,
                "raw_schema_inventory": [
                    {
                        "schema": "finance",
                        "table": "approved_vendor_spend",
                    }
                ],
            }
        )
    except ValidationError as exc:
        field_error_types = {
            (error["loc"][0], error["type"])
            for error in exc.errors()
        }
    else:
        raise AssertionError("Expected validation to fail for forbidden adapter fields.")

    assert field_error_types == {
        ("credentials", "extra_forbidden"),
        ("execution_authority", "extra_forbidden"),
        ("raw_schema_inventory", "extra_forbidden"),
    }
