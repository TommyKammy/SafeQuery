from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Optional, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
)

from app.core.config import ReviewLLMProvider, ReviewLLMSettings
from app.features.review_llm.schema import (
    ReviewLLMAdapterOutput,
    ReviewLLMAdapterOutputError,
    parse_review_llm_adapter_output,
)
from app.services.sql_generation_adapter import (
    NonEmptyTrimmedString,
    SQLGenerationAdapterRequest,
    SQLGenerationAdapterResponse,
    SQLGenerationAdapterRunMetadata,
)


REVIEW_LLM_PROMPT_VERSION = "review_llm_critique_request.v1"


class ReviewLLMAdapterConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReviewLLMGenerationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_provider: NonEmptyTrimmedString
    adapter_version: NonEmptyTrimmedString
    adapter_model: Optional[NonEmptyTrimmedString] = None
    generation_prompt_version: NonEmptyTrimmedString


class ReviewLLMAdapterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyTrimmedString
    question: NonEmptyTrimmedString
    candidate_sql: NonEmptyTrimmedString
    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None
    generation: ReviewLLMGenerationSummary
    prompt_version: NonEmptyTrimmedString = REVIEW_LLM_PROMPT_VERSION

    def to_runtime_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)


class ReviewLLMPromptMessages(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_version: NonEmptyTrimmedString
    system: NonEmptyTrimmedString
    user: NonEmptyTrimmedString


class ReviewLLMAdapter(Protocol):
    def review_sql(self, request: ReviewLLMAdapterRequest) -> ReviewLLMAdapterOutput:
        """Critique generated SQL from a minimized, review-only request projection."""


class ConfiguredReviewLLMAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: NonEmptyTrimmedString
    adapter_version: NonEmptyTrimmedString
    base_url: NonEmptyTrimmedString
    model: Optional[NonEmptyTrimmedString] = None
    timeout_seconds: int
    retry_count: int
    circuit_breaker_failure_threshold: int
    _consecutive_failures: int = PrivateAttr(default=0)

    def review_sql(self, request: ReviewLLMAdapterRequest) -> ReviewLLMAdapterOutput:
        if self.provider == "local_llm":
            return self._review_with_local_llm(request)

        raise ReviewLLMAdapterConfigurationError(
            "review_llm_provider_not_implemented",
            f"Provider '{self.provider}' is configured but dispatch is not implemented.",
        )

    def _review_with_local_llm(
        self,
        request: ReviewLLMAdapterRequest,
    ) -> ReviewLLMAdapterOutput:
        if self._consecutive_failures >= self.circuit_breaker_failure_threshold:
            raise ReviewLLMAdapterConfigurationError(
                "review_llm_runtime_circuit_open",
                "Review LLM runtime is unhealthy; circuit breaker is open.",
            )

        last_error: BaseException | None = None
        for _attempt in range(self.retry_count + 1):
            try:
                response = self._dispatch_local_llm_review(request)
            except (
                HTTPError,
                URLError,
                TimeoutError,
                OSError,
                ValidationError,
                json.JSONDecodeError,
                ReviewLLMAdapterOutputError,
                ReviewLLMAdapterConfigurationError,
            ) as exc:
                last_error = exc
                continue

            self._consecutive_failures = 0
            return response

        self._consecutive_failures += 1
        detail = (
            last_error.__class__.__name__
            if last_error is not None
            else "UnknownAdapterFailure"
        )
        raise ReviewLLMAdapterConfigurationError(
            "review_llm_runtime_unhealthy",
            f"Review LLM runtime is unavailable ({detail}).",
        )

    def _dispatch_local_llm_review(
        self,
        request: ReviewLLMAdapterRequest,
    ) -> ReviewLLMAdapterOutput:
        prompt = build_review_llm_prompt_messages(request)
        payload: dict[str, object] = {
            "request": request.to_runtime_payload(),
            "prompt": prompt.model_dump(mode="json"),
        }
        if self.model is not None:
            payload["model"] = self.model

        http_request = Request(
            f"{self.base_url.rstrip('/')}/review-sql",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(http_request, timeout=self.timeout_seconds) as response:  # noqa: S310
            status = getattr(response, "status", 200)
            raw_body = response.read().decode("utf-8", errors="replace")

        if status >= 400:
            raise ReviewLLMAdapterConfigurationError(
                "review_llm_runtime_unhealthy",
                "Review LLM runtime returned an unhealthy response.",
            )

        decoded = json.loads(raw_body)
        if not isinstance(decoded, Mapping):
            raise ReviewLLMAdapterConfigurationError(
                "review_llm_response_invalid",
                "Review LLM runtime returned an invalid response.",
            )

        return parse_review_llm_adapter_output(decoded)


def build_review_llm_prompt_messages(
    request: ReviewLLMAdapterRequest,
) -> ReviewLLMPromptMessages:
    request_payload = json.dumps(
        request.to_runtime_payload(),
        sort_keys=True,
        separators=(",", ":"),
    )
    return ReviewLLMPromptMessages(
        prompt_version=REVIEW_LLM_PROMPT_VERSION,
        system=(
            "You are SafeQuery's critique-only SQL review model. Review the "
            "candidate for uncertainty, ambiguity, missing context, unsafe "
            "assumptions, and business-intent mismatch. Return only the "
            "review_llm_adapter_output.v1 JSON object. Do not approve "
            "execution, select candidates, bypass SQL Guard, or infer hidden "
            "generation reasoning. Hidden scratchpads, chain-of-thought, "
            "credentials, and runtime secrets are not provided."
        ),
        user=(
            "Critique this minimized review input. Treat generation metadata as "
            "diagnostic context only and keep the result advisory: "
            f"{request_payload}"
        ),
    )


def build_review_llm_adapter_request(
    *,
    generation_request: SQLGenerationAdapterRequest,
    generation_response: SQLGenerationAdapterResponse,
    generation_metadata: SQLGenerationAdapterRunMetadata,
    candidate_sql: str,
) -> ReviewLLMAdapterRequest:
    return ReviewLLMAdapterRequest(
        request_id=generation_request.request_id,
        question=generation_request.question,
        candidate_sql=candidate_sql,
        source_id=generation_request.source.source_id,
        source_family=generation_request.source.source_family,
        source_flavor=generation_request.source.source_flavor,
        generation=ReviewLLMGenerationSummary(
            adapter_provider=generation_response.provider,
            adapter_version=generation_response.adapter_version,
            adapter_model=generation_response.model,
            generation_prompt_version=generation_metadata.prompt_version,
        ),
    )


def _settings_from_mapping(settings: Mapping[str, object]) -> ReviewLLMSettings:
    try:
        return ReviewLLMSettings.model_validate(settings)
    except ValidationError as exc:
        raise ReviewLLMAdapterConfigurationError(
            "review_llm_settings_invalid",
            "Review LLM adapter settings are invalid.",
        ) from exc


def resolve_review_llm_adapter(
    settings: ReviewLLMSettings | Mapping[str, object],
) -> ReviewLLMAdapter:
    review_settings = (
        _settings_from_mapping(settings) if isinstance(settings, Mapping) else settings
    )

    if review_settings.provider == "disabled":
        raise ReviewLLMAdapterConfigurationError(
            "review_llm_disabled",
            "Review LLM is disabled; no adapter can be used for critique.",
        )

    if review_settings.provider == "local_llm":
        if review_settings.local_llm_base_url is None:
            raise ReviewLLMAdapterConfigurationError(
                "review_llm_local_llm_misconfigured",
                "Local review LLM requires a configured base URL.",
            )
        return ConfiguredReviewLLMAdapter(
            provider="local_llm",
            adapter_version="review_local_llm.v1",
            base_url=str(review_settings.local_llm_base_url),
            model=review_settings.local_llm_model,
            timeout_seconds=review_settings.timeout_seconds,
            retry_count=review_settings.retry_count,
            circuit_breaker_failure_threshold=(
                review_settings.circuit_breaker_failure_threshold
            ),
        )

    raise ReviewLLMAdapterConfigurationError(
        "review_llm_provider_unknown",
        "Review LLM provider selection is not recognized.",
    )
