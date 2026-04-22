from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated


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
