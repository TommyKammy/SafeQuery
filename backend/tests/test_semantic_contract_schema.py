from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from app.features.semantic_contract.schema import (
    SemanticContractDefinition,
    _SemanticContractModel,
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


def test_validated_contract_does_not_retain_mutable_payload_collections() -> None:
    payload = _load_contract()

    contract = validate_semantic_contract_definition(payload)
    payload["metrics"][0]["allowed_source_ids"].append("undeclared-source")
    payload["ambiguity_rules"]["unchecked_rule"] = "mutated after validation."

    assert contract.metrics[0].allowed_source_ids == ("business-postgres-source",)
    assert "unchecked_rule" not in contract.ambiguity_rules


def test_semantic_contract_model_rejects_mutable_collection_annotations() -> None:
    with pytest.raises(TypeError, match="immutable collection annotations"):
        class MutableCollectionModel(_SemanticContractModel):
            values: list[str]

    with pytest.raises(TypeError, match="immutable collection annotations"):
        class MutableMappingModel(_SemanticContractModel):
            values: dict[str, str]

    with pytest.raises(TypeError, match="immutable collection annotations"):
        class NestedMutableCollectionModel(_SemanticContractModel):
            values: tuple[list[str], ...]


def test_non_spend_contract_does_not_require_spend_definition_ambiguity() -> None:
    payload = _make_non_spend_contract(deepcopy(_load_contract()))
    payload["ambiguity_rules"].pop("spend_definition")

    contract = validate_semantic_contract_definition(payload)

    assert contract.contract_id == "support_ticket_volume"
    assert "spend_definition" not in contract.ambiguity_rules


def test_metric_expression_owner_does_not_drive_spend_definition_ambiguity() -> None:
    payload = _make_non_spend_contract(deepcopy(_load_contract()))
    payload["metrics"][0]["expression_owner"] = "spend_analytics"
    payload["ambiguity_rules"].pop("spend_definition")

    contract = validate_semantic_contract_definition(payload)

    assert contract.metrics[0].expression_owner == "spend_analytics"
    assert "spend_definition" not in contract.ambiguity_rules


def test_spend_definition_detection_uses_tokens_not_substrings() -> None:
    payload = _make_non_spend_contract(deepcopy(_load_contract()))
    payload["contract_id"] = "suspended_ticket_volume"
    payload["domain"] = "suspended_ticket_volume"
    payload["version"]["identifier"] = "suspended_ticket_volume.v1"
    payload["dimensions"][0]["source_column"] = (
        "support.suspended_ticket_volume.vendor_name"
    )
    payload["filters"][0]["expression"] = "status = 'suspended'"
    payload["metrics"][0]["label"] = "Suspended ticket count"
    payload["metrics"][0]["expression"] = "COUNT(suspended_ticket_id)"
    payload["ambiguity_rules"].pop("spend_definition")

    contract = validate_semantic_contract_definition(payload)

    assert contract.contract_id == "suspended_ticket_volume"
    assert "spend_definition" not in contract.ambiguity_rules


def test_spend_definition_detection_catches_compound_spend_terms() -> None:
    payload = _make_non_spend_contract(deepcopy(_load_contract()))
    payload["metrics"][0]["metric_id"] = "sum_overspend_amount"
    payload["metrics"][0]["label"] = "Vendor overage amount"
    payload["metrics"][0]["expression"] = "SUM(overspend_amount)"
    payload["ambiguity_rules"].pop("spend_definition")

    with pytest.raises(
        ValidationError,
        match="Spend definition ambiguity must be explicit in ambiguity_rules",
    ):
        validate_semantic_contract_definition(payload)


@pytest.mark.parametrize(
    "metric_id, expression",
    [
        ("sum_spending_total", "SUM(spending_amount)"),
        ("sum_spend2_amount", "SUM(spend2_amount)"),
        ("sum_totalspending", "SUM(totalspending_amount)"),
    ],
)
def test_spend_definition_detection_catches_spend_prefixed_terms(
    metric_id: str, expression: str
) -> None:
    payload = _make_non_spend_contract(deepcopy(_load_contract()))
    payload["metrics"][0]["metric_id"] = metric_id
    payload["metrics"][0]["expression"] = expression
    payload["ambiguity_rules"].pop("spend_definition")

    with pytest.raises(
        ValidationError,
        match="Spend definition ambiguity must be explicit in ambiguity_rules",
    ):
        validate_semantic_contract_definition(payload)


def test_spend_definition_detection_catches_camel_compound_terms() -> None:
    payload = deepcopy(_load_contract())
    payload["contract_id"] = "approved_amount"
    payload["domain"] = "approved_amount"
    payload["version"]["identifier"] = "approved_amount.v1"
    payload["dimensions"][0]["source_column"] = "finance.approved_amount.vendor_name"
    payload["dimensions"][1]["source_column"] = (
        "finance.approved_amount.fiscal_quarter"
    )
    payload["filters"][0]["filter_id"] = "approved_amount_only"
    payload["filters"][0]["label"] = "Approved amount only"
    payload["metrics"][0]["metric_id"] = "sum_approved_vendor_amount"
    payload["metrics"][0]["label"] = "ApprovedVendorSpend"
    payload["metrics"][0]["expression"] = "SUM(approved_amount)"
    payload["metrics"][0]["default_filters"] = ["approved_amount_only"]
    payload["sensitive_concepts"][0]["reason"] = (
        "Refund handling changes gross-versus-net amount definition."
    )
    payload["ambiguity_rules"].pop("spend_definition")

    with pytest.raises(
        ValidationError,
        match="Spend definition ambiguity must be explicit in ambiguity_rules",
    ):
        validate_semantic_contract_definition(payload)


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
            "Declared ambiguous terms must have matching ambiguity_rules",
        ),
        (
            lambda payload: payload["time_semantics"]["ambiguous_terms"].append(
                "month"
            ),
            "Declared ambiguous terms must have matching ambiguity_rules",
        ),
        (
            lambda payload: payload["sensitive_concepts"].append(
                {
                    "concept_id": "refund_amount",
                    "label": "Refund amount duplicate",
                    "reason": "Duplicate concept metadata must fail closed.",
                    "requires_review": True,
                }
            ),
            "Contract sensitive concepts must not contain duplicate values",
        ),
        (
            lambda payload: (
                payload["source_bindings"].append(
                    {
                        "source_id": "support-postgres-source",
                        "source_family": "postgresql",
                        "source_flavor": "warehouse",
                        "dataset_contract_version": 1,
                        "schema_snapshot_version": 1,
                    }
                ),
                payload["dimensions"][0].__setitem__(
                    "allowed_source_ids", ["support-postgres-source"]
                ),
            ),
            "references dimensions without compatible allowed sources",
        ),
        (
            lambda payload: (
                payload["source_bindings"].append(
                    {
                        "source_id": "support-postgres-source",
                        "source_family": "postgresql",
                        "source_flavor": "warehouse",
                        "dataset_contract_version": 1,
                        "schema_snapshot_version": 1,
                    }
                ),
                payload["filters"][0].__setitem__(
                    "allowed_source_ids", ["support-postgres-source"]
                ),
            ),
            "references default filters without compatible allowed sources",
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
        (
            lambda payload: payload["filters"][0].__setitem__("locked", "true"),
            "Input should be a valid boolean",
        ),
        (
            lambda payload: payload["metrics"][0]["time_range_semantics"].__setitem__(
                "requires_explicit_range", "false"
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
