from typing import Optional

import pytest

from app.features.guard.deny_taxonomy import DENY_UNSUPPORTED_SOURCE_BINDING
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata


def _candidate_source(
    *,
    source_id: str = "approved-spend",
    source_family: str = "postgresql",
    source_flavor: Optional[str] = "warehouse",
) -> SourceBoundCandidateMetadata:
    return SourceBoundCandidateMetadata(
        source_id=source_id,
        source_family=source_family,
        source_flavor=source_flavor,
        dataset_contract_version=3,
        schema_snapshot_version=7,
    )


def test_select_execution_connector_uses_candidate_bound_source_metadata() -> None:
    from app.features.execution.connector_selection import select_execution_connector

    selection = select_execution_connector(candidate_source=_candidate_source())

    assert selection.model_dump() == {
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "connector_id": "postgresql_readonly",
        "ownership": "backend",
    }


def test_select_execution_connector_normalizes_candidate_source_binding_values() -> None:
    from app.features.execution.connector_selection import select_execution_connector

    selection = select_execution_connector(
        candidate_source=_candidate_source(
            source_family=" postgresql ",
            source_flavor=" warehouse ",
        )
    )

    assert selection.model_dump() == {
        "source_id": "approved-spend",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "connector_id": "postgresql_readonly",
        "ownership": "backend",
    }


def test_select_execution_connector_rejects_unsupported_source_binding_fail_closed() -> None:
    from app.features.execution.connector_selection import (
        ExecutionConnectorSelectionError,
        select_execution_connector,
    )

    with pytest.raises(
        ExecutionConnectorSelectionError,
        match="No backend-owned execution connector is registered",
    ) as exc_info:
        select_execution_connector(
            candidate_source=_candidate_source(
                source_id="future-mysql-source",
                source_family="mysql",
                source_flavor=None,
            )
        )

    assert exc_info.value.deny_code == DENY_UNSUPPORTED_SOURCE_BINDING


def test_select_execution_connector_rejects_unsupported_source_flavor_without_fallback() -> None:
    from app.features.execution.connector_selection import (
        ExecutionConnectorSelectionError,
        select_execution_connector,
    )

    with pytest.raises(
        ExecutionConnectorSelectionError,
        match="candidate-bound source family 'postgresql' and flavor 'analytics'",
    ) as exc_info:
        select_execution_connector(
            candidate_source=_candidate_source(
                source_flavor="analytics",
            )
        )

    assert exc_info.value.deny_code == DENY_UNSUPPORTED_SOURCE_BINDING
