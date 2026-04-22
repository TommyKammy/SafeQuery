from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints
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

    dataset_contract_id: NonEmptyTrimmedString
    schema_snapshot_id: NonEmptyTrimmedString
    glossary_id: Optional[NonEmptyTrimmedString] = None
    policy_id: Optional[NonEmptyTrimmedString] = None


class SQLGenerationAdapterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyTrimmedString
    question: NonEmptyTrimmedString
    source: SQLGenerationSourceBinding
    context: SQLGenerationContextReferences


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
            dataset_contract_id=prepared_context.governance.dataset_contract_id,
            schema_snapshot_id=prepared_context.governance.schema_snapshot_id,
        ),
    )
