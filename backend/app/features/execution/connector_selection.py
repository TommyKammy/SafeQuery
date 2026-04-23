from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated

from app.features.guard.deny_taxonomy import DENY_UNSUPPORTED_SOURCE_BINDING
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


NonEmptyTrimmedString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ExecutionConnectorSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: NonEmptyTrimmedString
    source_family: NonEmptyTrimmedString
    source_flavor: Optional[NonEmptyTrimmedString] = None
    connector_id: NonEmptyTrimmedString
    ownership: Literal["backend"]


class ExecutionConnectorSelectionError(PermissionError):
    def __init__(self, *, deny_code: str, message: str) -> None:
        super().__init__(f"{deny_code}: {message}")
        self.deny_code = deny_code


_EXACT_CONNECTOR_BINDINGS: dict[tuple[str, str], str] = {
    ("mssql", "sqlserver"): "mssql_readonly",
    ("postgresql", "warehouse"): "postgresql_readonly",
}

_FAMILY_DEFAULT_CONNECTORS: dict[str, str] = {
    "mssql": "mssql_readonly",
    "postgresql": "postgresql_readonly",
}


def select_execution_connector(
    *,
    candidate_source: SourceBoundCandidateMetadata,
) -> ExecutionConnectorSelection:
    connector_id: str | None = None
    source_family = candidate_source.source_family.strip()
    source_flavor = (
        candidate_source.source_flavor.strip()
        if candidate_source.source_flavor is not None
        else None
    )

    if source_flavor is not None:
        connector_id = _EXACT_CONNECTOR_BINDINGS.get((source_family, source_flavor))
    else:
        connector_id = _FAMILY_DEFAULT_CONNECTORS.get(source_family)

    if connector_id is None:
        raise ExecutionConnectorSelectionError(
            deny_code=DENY_UNSUPPORTED_SOURCE_BINDING,
            message=(
                "No backend-owned execution connector is registered for the "
                f"candidate-bound source family '{source_family}'"
                + (
                    f" and flavor '{source_flavor}'."
                    if source_flavor is not None
                    else "."
                )
            ),
        )

    return ExecutionConnectorSelection(
        source_id=candidate_source.source_id,
        source_family=source_family,
        source_flavor=source_flavor,
        connector_id=connector_id,
        ownership="backend",
    )
