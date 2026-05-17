from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from app.features.semantic_contract.schema import (
    SemanticContractDefinition,
    validate_semantic_contract_definition,
)


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "semantic_contract_vendor_spend.v1.json"
)


def _load_contract() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _make_non_spend_contract(payload: dict[str, Any]) -> dict[str, Any]:
    payload["contract_id"] = "support_ticket_volume"
    payload["domain"] = "support_ticket_volume"
    payload["version"]["identifier"] = "support_ticket_volume.v1"
    payload["dimensions"][0]["source_column"] = "support.ticket_volume.vendor_name"
    payload["dimensions"][1]["source_column"] = "support.ticket_volume.fiscal_quarter"
    payload["filters"][0]["filter_id"] = "closed_tickets_only"
    payload["filters"][0]["label"] = "Closed tickets only"
    payload["filters"][0]["expression"] = "status = 'closed'"
    payload["metrics"][0]["metric_id"] = "sum_closed_tickets"
    payload["metrics"][0]["label"] = "Closed tickets"
    payload["metrics"][0]["expression"] = "COUNT(ticket_id)"
    payload["metrics"][0]["default_filters"] = ["closed_tickets_only"]
    payload["sensitive_concepts"][0]["reason"] = (
        "Ticket status handling requires review."
    )
    return payload


def test_vendor_spend_semantic_contract_fixture_validates_and_serializes() -> None:
    contract = validate_semantic_contract_definition(_load_contract())

    assert contract.contract_id == "approved_vendor_spend"
    assert contract.version.identifier == "approved_vendor_spend.v1"
    assert contract.version.status == "active"
    assert contract.metrics[0].metric_id == "sum_approved_vendor_spend"
    assert contract.metrics[0].allowed_source_ids == ("business-postgres-source",)
    assert contract.metrics[0].allowed_dimensions == (
        "vendor_name",
        "fiscal_quarter",
    )
    assert contract.metrics[0].default_filters == ("approved_spend_only",)
    assert contract.time_semantics.default_grain == "fiscal_quarter"
    assert contract.time_semantics.ambiguous_terms == ("quarter",)
    assert contract.ambiguity_rules["quarter"] == (
        "Clarify fiscal versus calendar quarter before mapping."
    )
    assert contract.ambiguity_rules["spend_definition"] == (
        "Clarify gross spend versus net-of-refunds spend before mapping."
    )

    serialized = contract.to_wire_payload()

    assert serialized["contractId"] == "approved_vendor_spend"
    assert serialized["version"]["identifier"] == "approved_vendor_spend.v1"
    assert serialized["metrics"][0]["metricId"] == "sum_approved_vendor_spend"
    assert serialized["timeSemantics"]["defaultGrain"] == "fiscal_quarter"
    assert "contract_id" not in serialized


def test_validated_semantic_contract_collections_are_immutable() -> None:
    contract = validate_semantic_contract_definition(_load_contract())

    with pytest.raises(AttributeError):
        contract.metrics.append(contract.metrics[0])
    with pytest.raises(AttributeError):
        contract.metrics[0].allowed_source_ids.append("undeclared-source")
    with pytest.raises(TypeError):
        contract.ambiguity_rules["unchecked_rule"] = "mutated after validation."


def test_non_spend_contract_does_not_require_spend_definition_ambiguity() -> None:
    payload = _make_non_spend_contract(deepcopy(_load_contract()))
    payload["ambiguity_rules"].pop("spend_definition")

    contract = validate_semantic_contract_definition(payload)

    assert contract.contract_id == "support_ticket_volume"
    assert "spend_definition" not in contract.ambiguity_rules


@pytest.mark.parametrize(
    "mutator, expected_message",
    [
        (
            lambda payload: payload["metrics"][0].__setitem__("allowed_source_ids", []),
            "at least one allowed source",
        ),
        (
            lambda payload: payload["metrics"][0].__setitem__(
                "allowed_dimensions", ["undeclared_dimension"]
            ),
            "undeclared dimensions",
        ),
        (
            lambda payload: payload["metrics"][0].__setitem__(
                "default_filters", ["missing_filter"]
            ),
            "undeclared default filters",
        ),
        (
            lambda payload: payload["time_semantics"].__setitem__(
                "default_grain", "calendar_quarter"
            ),
            "must be one of the allowed time grains",
        ),
        (
            lambda payload: payload["ambiguity_rules"].pop("quarter"),
            "Quarter ambiguity must be explicit",
        ),
        (
            lambda payload: payload["sensitive_concepts"][0].__setitem__(
                "requires_review", False
            ),
            "Sensitive concepts must require review",
        ),
        (
            lambda payload: payload["sensitive_concepts"][0].__setitem__(
                "requires_review", "true"
            ),
            "Input should be a valid boolean",
        ),
    ],
)
def test_semantic_contract_schema_fails_closed_for_malformed_definitions(
    mutator: Callable[[dict[str, object]], object],
    expected_message: str,
) -> None:
    payload = deepcopy(_load_contract())
    mutator(payload)

    with pytest.raises(ValidationError, match=expected_message):
        SemanticContractDefinition.model_validate(payload)
