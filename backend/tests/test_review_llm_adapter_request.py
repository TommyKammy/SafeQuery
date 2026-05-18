from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

import app.features.review_llm.adapter as review_adapter_module
from app.features.review_llm import (
    REVIEW_LLM_PROMPT_VERSION,
    build_review_llm_adapter_request,
    build_review_llm_prompt_messages,
    resolve_review_llm_adapter,
)
from app.services.sql_generation_adapter import (
    SQLGenerationAdapterRequest,
    SQLGenerationAdapterResponse,
    SQLGenerationContextReferences,
    SQLGenerationSourceBinding,
    build_sql_generation_adapter_run_metadata,
)


def _generation_request() -> SQLGenerationAdapterRequest:
    return SQLGenerationAdapterRequest(
        request_id="req_460_preview",
        question="Show approved vendors by quarterly spend.",
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
        ),
    )


def test_review_llm_request_uses_separate_prompt_boundary_and_minimized_inputs() -> None:
    generation_request = _generation_request()
    generation_response = SQLGenerationAdapterResponse(
        candidate_sql="select vendor_id from approved_vendor_spend limit 50",
        provider="vanna",
        adapter_version="vanna.v1",
        model="warehouse-assistant",
    )
    generation_metadata = build_sql_generation_adapter_run_metadata(
        adapter_request=generation_request,
        adapter_response=generation_response,
        adapter_run_id="correlation-460",
    )

    review_request = build_review_llm_adapter_request(
        generation_request=generation_request,
        generation_response=generation_response,
        generation_metadata=generation_metadata,
        candidate_sql=generation_response.candidate_sql,
    )
    prompt = build_review_llm_prompt_messages(review_request)
    serialized_request = json.dumps(review_request.to_runtime_payload(), sort_keys=True)
    serialized_prompt = json.dumps(prompt.model_dump(mode="json"), sort_keys=True)

    assert review_request.prompt_version == REVIEW_LLM_PROMPT_VERSION
    assert review_request.generation.generation_prompt_version == (
        "sql_generation_adapter_request.v1"
    )
    assert review_request.generation.adapter_provider == "vanna"
    assert "prompt_fingerprint" not in serialized_request
    assert "adapter_run_id" not in serialized_request
    assert "credentials" not in serialized_request
    assert "scratchpad" not in serialized_request
    assert "chain-of-thought" not in serialized_request
    assert "Critique" in prompt.user
    assert "uncertainty" in prompt.system
    assert "Do not approve execution" in prompt.system
    assert "Hidden scratchpads, chain-of-thought, credentials" in prompt.system
    assert "sql_generation_adapter_request.v1" in serialized_prompt


def test_review_llm_request_rejects_generation_internals_and_credentials() -> None:
    with pytest.raises(ValidationError) as exc_info:
        review_adapter_module.ReviewLLMAdapterRequest.model_validate(
            {
                "request_id": "req_460_preview",
                "question": "Show approved vendors.",
                "candidate_sql": "select vendor_id from approved_vendor_spend limit 50",
                "source_id": "sap-approved-spend",
                "source_family": "postgresql",
                "generation": {
                    "adapter_provider": "vanna",
                    "adapter_version": "vanna.v1",
                    "generation_prompt_version": "sql_generation_adapter_request.v1",
                },
                "hidden_prompt": "do not expose generation scratchpad",
                "credentials": {"password": "not-allowed"},
            }
        )

    field_errors = {
        (error["loc"][0], error["type"])
        for error in exc_info.value.errors()
    }
    assert ("hidden_prompt", "extra_forbidden") in field_errors
    assert ("credentials", "extra_forbidden") in field_errors


def test_review_llm_adapter_registry_selects_independent_model(monkeypatch) -> None:
    adapter = resolve_review_llm_adapter(
        {
            "provider": "local_llm",
            "local_llm_base_url": "http://review-llm:8090",
            "local_llm_model": "safequery-reviewer",
            "retry_count": 0,
            "timeout_seconds": 12,
        }
    )
    generation_request = _generation_request()
    generation_response = SQLGenerationAdapterResponse(
        candidate_sql="select vendor_id from approved_vendor_spend limit 50",
        provider="local_llm",
        adapter_version="local_llm.v1",
        model="safequery-generator",
    )
    review_request = build_review_llm_adapter_request(
        generation_request=generation_request,
        generation_response=generation_response,
        generation_metadata=build_sql_generation_adapter_run_metadata(
            adapter_request=generation_request,
            adapter_response=generation_response,
            adapter_run_id="correlation-460",
        ),
        candidate_sql=generation_response.candidate_sql,
    )
    seen: dict[str, object] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "contract_version": "review_llm_adapter_output.v1",
                    "status": "needs_clarification",
                    "confidence": "medium",
                    "intent_summary": "Show approved vendors.",
                    "risk_flags": ["The candidate needs reviewer confirmation."],
                    "clarifying_questions": ["Should inactive vendors be included?"],
                    "diagnostics": {
                        "adapter_version": "review_local_llm.v1",
                        "provider": "local_llm",
                        "model": "safequery-reviewer",
                        "prompt_version": REVIEW_LLM_PROMPT_VERSION,
                    },
                }
            ).encode("utf-8")

    def fake_urlopen(http_request, timeout=None):
        seen["url"] = http_request.full_url
        seen["timeout"] = timeout
        seen["body"] = json.loads(http_request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr(review_adapter_module, "urlopen", fake_urlopen)

    review = adapter.review_sql(review_request)

    assert review.status == "needs_clarification"
    assert seen["url"] == "http://review-llm:8090/review-sql"
    assert seen["timeout"] == 12
    assert seen["body"]["model"] == "safequery-reviewer"
    assert seen["body"]["request"]["generation"]["adapter_model"] == (
        "safequery-generator"
    )
    assert seen["body"]["prompt"]["prompt_version"] == REVIEW_LLM_PROMPT_VERSION
