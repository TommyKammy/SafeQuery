from pydantic import ValidationError

from app.services.sql_generation_adapter import (
    SQLGenerationAdapterConfigurationError,
    SQLGenerationAdapterRequest,
    SQLGenerationAdapterResponse,
    SQLGenerationContextReferences,
    SQLGenerationSourceBinding,
    resolve_sql_generation_adapter,
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


def test_sql_generation_adapter_response_shape_is_typed_and_credential_free() -> None:
    response = SQLGenerationAdapterResponse(
        candidate_sql="select vendor_id, total_spend from approved_vendor_spend limit 50",
        provider="local_llm",
        adapter_version="local_llm.v1",
        model="safequery-local-sql",
    )

    assert response.model_dump(exclude_none=True) == {
        "candidate_sql": (
            "select vendor_id, total_spend from approved_vendor_spend limit 50"
        ),
        "provider": "local_llm",
        "adapter_version": "local_llm.v1",
        "model": "safequery-local-sql",
    }

    try:
        SQLGenerationAdapterResponse.model_validate(
            {
                "candidate_sql": "select 1",
                "provider": "local_llm",
                "adapter_version": "local_llm.v1",
                "source_credentials": {"password": "not-allowed"},
            }
        )
    except ValidationError as exc:
        assert exc.errors()[0]["loc"] == ("source_credentials",)
        assert exc.errors()[0]["type"] == "extra_forbidden"
    else:
        raise AssertionError("Expected response validation to reject credentials.")


def test_sql_generation_adapter_registry_fails_closed_when_disabled() -> None:
    try:
        resolve_sql_generation_adapter({"provider": "disabled"})
    except SQLGenerationAdapterConfigurationError as exc:
        assert exc.code == "sql_generation_disabled"
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Expected disabled SQL generation to fail closed.")


def test_sql_generation_adapter_registry_selects_configured_providers() -> None:
    local_adapter = resolve_sql_generation_adapter(
        {
            "provider": "local_llm",
            "local_llm_base_url": "http://local-llm:8080",
            "local_llm_model": "safequery-local-sql",
        }
    )
    vanna_adapter = resolve_sql_generation_adapter(
        {
            "provider": "vanna",
            "vanna_base_url": "http://vanna:8084",
            "vanna_model": "warehouse-assistant",
        }
    )

    assert local_adapter.model_dump(exclude_none=True) == {
        "provider": "local_llm",
        "adapter_version": "local_llm.v1",
        "base_url": "http://local-llm:8080/",
        "model": "safequery-local-sql",
        "timeout_seconds": 30,
    }
    assert vanna_adapter.model_dump(exclude_none=True) == {
        "provider": "vanna",
        "adapter_version": "vanna.v1",
        "base_url": "http://vanna:8084/",
        "model": "warehouse-assistant",
        "timeout_seconds": 30,
    }


def test_sql_generation_adapter_registry_preserves_masked_vanna_api_key() -> None:
    vanna_adapter = resolve_sql_generation_adapter(
        {
            "provider": "vanna",
            "vanna_base_url": "http://vanna:8084",
            "vanna_model": "warehouse-assistant",
            "vanna_api_key": "trusted-vanna-token",
        }
    )

    assert vanna_adapter.api_key is not None
    assert vanna_adapter.api_key.get_secret_value() == "trusted-vanna-token"
    assert (
        vanna_adapter.model_dump(mode="json", exclude_none=True)["api_key"]
        == "**********"
    )


def test_sql_generation_adapter_registry_wraps_mapping_validation_errors() -> None:
    try:
        resolve_sql_generation_adapter({"provider": "not-a-provider"})
    except SQLGenerationAdapterConfigurationError as exc:
        assert exc.code == "sql_generation_settings_invalid"
        assert isinstance(exc.__cause__, ValidationError)
    else:
        raise AssertionError("Expected invalid adapter settings to fail closed.")


def test_configured_sql_generation_adapter_fails_closed_before_dispatch() -> None:
    adapter = resolve_sql_generation_adapter(
        {
            "provider": "local_llm",
            "local_llm_base_url": "http://local-llm:8080",
        }
    )
    request = SQLGenerationAdapterRequest(
        request_id="req_80_preview",
        question="Show approved vendors",
        source=SQLGenerationSourceBinding(
            source_id="sap-approved-spend",
            source_family="postgresql",
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
        ),
    )

    try:
        adapter.generate_sql(request)
    except SQLGenerationAdapterConfigurationError as exc:
        assert exc.code == "sql_generation_provider_not_implemented"
        assert "dispatch is not implemented" in str(exc)
    else:
        raise AssertionError("Expected configured adapter dispatch to fail closed.")
