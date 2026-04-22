from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from typing_extensions import Annotated

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


class SQLGenerationAdapter(Protocol):
    def generate_sql(self, request: SQLGenerationAdapterRequest) -> str:
        """Generate SQL from the adapter-safe request projection."""


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
