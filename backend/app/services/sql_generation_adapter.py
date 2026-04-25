from __future__ import annotations

from collections.abc import Mapping
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from typing_extensions import Annotated

from app.core.config import SQLGenerationProvider, SQLGenerationSettings
from app.services.generation_context import PreparedGenerationContext


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SQLGenerationSourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None


class SQLGenerationContextReferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_contract: "SQLGenerationContextReference"
    schema_snapshot: "SQLGenerationContextReference"
    glossary: Optional["SQLGenerationContextReference"] = None
    policy: Optional["SQLGenerationContextReference"] = None


class SQLGenerationContextReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_id: NonEmptyTrimmedString
    source_id: NonEmptyTrimmedString


class SQLGenerationAdapterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyTrimmedString
    question: NonEmptyTrimmedString
    source: SQLGenerationSourceBinding
    context: SQLGenerationContextReferences

    @model_validator(mode="after")
    def validate_single_source_context(self) -> "SQLGenerationAdapterRequest":
        fragment_source_ids = {
            fragment.source_id
            for fragment in (
                self.context.dataset_contract,
                self.context.schema_snapshot,
                self.context.glossary,
                self.context.policy,
            )
            if fragment is not None
        }
        if fragment_source_ids != {self.source.source_id}:
            raise ValueError(
                "Adapter request context must stay bound to source_id "
                f"'{self.source.source_id}'."
            )
        return self


class SQLGenerationAdapterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_sql: NonEmptyTrimmedString
    provider: SQLGenerationProvider
    adapter_version: NonEmptyTrimmedString
    model: Optional[NonEmptyTrimmedString] = None


class SQLGenerationAdapterError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: NonEmptyTrimmedString
    message: NonEmptyTrimmedString
    provider: Optional[SQLGenerationProvider] = None
    retryable: bool = False


class SQLGenerationAdapterConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SQLGenerationAdapter(Protocol):
    def generate_sql(
        self,
        request: SQLGenerationAdapterRequest,
    ) -> SQLGenerationAdapterResponse:
        """Generate SQL from the adapter-safe request projection."""


class ConfiguredSQLGenerationAdapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: NonEmptyTrimmedString
    adapter_version: NonEmptyTrimmedString
    base_url: NonEmptyTrimmedString
    model: Optional[NonEmptyTrimmedString] = None
    timeout_seconds: int

    def generate_sql(
        self,
        request: SQLGenerationAdapterRequest,
    ) -> SQLGenerationAdapterResponse:
        raise NotImplementedError(
            "Concrete SQL generation provider dispatch is not implemented yet."
        )


def _settings_from_mapping(settings: Mapping[str, object]) -> SQLGenerationSettings:
    return SQLGenerationSettings.model_validate(settings)


def resolve_sql_generation_adapter(
    settings: SQLGenerationSettings | Mapping[str, object],
) -> SQLGenerationAdapter:
    generation_settings = (
        _settings_from_mapping(settings)
        if isinstance(settings, Mapping)
        else settings
    )

    if generation_settings.provider == "disabled":
        raise SQLGenerationAdapterConfigurationError(
            "sql_generation_disabled",
            "SQL generation is disabled; no adapter can be used for candidate generation.",
        )

    if generation_settings.provider == "local_llm":
        if generation_settings.local_llm_base_url is None:
            raise SQLGenerationAdapterConfigurationError(
                "sql_generation_local_llm_misconfigured",
                "Local LLM SQL generation requires a configured base URL.",
            )
        return ConfiguredSQLGenerationAdapter(
            provider="local_llm",
            adapter_version="local_llm.v1",
            base_url=str(generation_settings.local_llm_base_url),
            model=generation_settings.local_llm_model,
            timeout_seconds=generation_settings.timeout_seconds,
        )

    if generation_settings.provider == "vanna":
        if generation_settings.vanna_base_url is None:
            raise SQLGenerationAdapterConfigurationError(
                "sql_generation_vanna_misconfigured",
                "Vanna SQL generation requires a configured base URL.",
            )
        return ConfiguredSQLGenerationAdapter(
            provider="vanna",
            adapter_version="vanna.v1",
            base_url=str(generation_settings.vanna_base_url),
            model=generation_settings.vanna_model,
            timeout_seconds=generation_settings.timeout_seconds,
        )

    raise SQLGenerationAdapterConfigurationError(
        "sql_generation_provider_unknown",
        "SQL generation provider selection is not recognized.",
    )


def build_sql_generation_adapter_request(
    prepared_context: PreparedGenerationContext,
) -> SQLGenerationAdapterRequest:
    return SQLGenerationAdapterRequest(
        request_id=prepared_context.request.request_id,
        question=prepared_context.request.question,
        source=SQLGenerationSourceBinding(
            source_id=prepared_context.source.source_id,
            source_family=prepared_context.source.source_family,
            source_flavor=prepared_context.source.source_flavor,
        ),
        context=SQLGenerationContextReferences(
            dataset_contract=SQLGenerationContextReference(
                context_id=prepared_context.governance.dataset_contract_id,
                source_id=prepared_context.source.source_id,
            ),
            schema_snapshot=SQLGenerationContextReference(
                context_id=prepared_context.governance.schema_snapshot_id,
                source_id=prepared_context.source.source_id,
            ),
        ),
    )
