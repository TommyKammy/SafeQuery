from pydantic import ValidationError

from app.services.sql_generation_adapter import SQLGenerationAdapterRequest


def test_adapter_request_accepts_single_source_context_fragments() -> None:
    request = SQLGenerationAdapterRequest.model_validate(
        {
            "request_id": "req_83_preview",
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
    )

    assert request.model_dump() == {
        "request_id": "req_83_preview",
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
            "datasets": [],
        },
    }


def test_adapter_request_rejects_mixed_source_context_fragments() -> None:
    try:
        SQLGenerationAdapterRequest.model_validate(
            {
                "request_id": "req_83_preview",
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
                        "context_id": "snapshot_sales_v5",
                        "source_id": "crm-pipeline",
                    },
                },
            }
        )
    except ValidationError as exc:
        errors = exc.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "value_error"
        assert errors[0]["loc"] == ()
        assert (
            "Adapter request context must stay bound to source_id "
            "'sap-approved-spend'."
        ) in errors[0]["msg"]
    else:
        raise AssertionError("Expected validation to fail for mixed-source context.")
