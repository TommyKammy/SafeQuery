from __future__ import annotations

import json
from pathlib import Path

from app.services.intent_mapping import map_question_intent


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "governed_answer_vendor_spend_fixtures.json"
)


def _fixture_question(case_type: str) -> str:
    fixture_set = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for fixture in fixture_set["fixtures"]:
        if fixture["case_type"] == case_type:
            return fixture["question"]
    raise AssertionError(f"Expected Epic AA fixture for case_type={case_type}")


def test_intent_mapping_maps_positive_epic_aa_fixture_to_concepts() -> None:
    mapping = map_question_intent(
        _fixture_question("positive"),
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.model_dump(exclude_none=True) == {
        "status": "mapped",
        "mapping_id": "show_top_approved_vendors_by_quarterly_spend",
        "metric": "sum_approved_vendor_spend",
        "dimensions": ["vendor_name", "fiscal_quarter"],
        "filters": ["approved_spend_only"],
        "ranking_behavior_id": "top_approved_vendors_by_quarterly_spend",
    }


def test_intent_mapping_keeps_ambiguous_epic_aa_fixture_in_clarification_state() -> None:
    mapping = map_question_intent(
        _fixture_question("ambiguous"),
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "ambiguous"
    assert mapping.metric == "sum_approved_vendor_spend"
    assert mapping.dimensions == ["vendor_name", "fiscal_quarter"]
    assert mapping.filters == ["approved_spend_only"]
    assert mapping.clarification is not None


def test_intent_mapping_keeps_bare_quarter_shorthand_in_clarification_state() -> None:
    mapping = map_question_intent(
        "Show approved vendor spend for Q3.",
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "ambiguous"
    assert mapping.mapping_id == "clarify_calendar_vs_fiscal_quarter"
    assert mapping.metric == "sum_approved_vendor_spend"
    assert mapping.dimensions == ["fiscal_quarter"]
    assert mapping.filters == ["approved_spend_only"]


def test_intent_mapping_maps_explicit_fiscal_quarter_shorthand() -> None:
    mapping = map_question_intent(
        "Show approved vendor spend for fiscal Q3.",
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "mapped"
    assert mapping.mapping_id == "approved_vendor_spend_by_fiscal_quarter"
    assert mapping.metric == "sum_approved_vendor_spend"
    assert mapping.dimensions == ["fiscal_quarter"]
    assert mapping.filters == ["approved_spend_only"]


def test_intent_mapping_fails_closed_for_unrelated_ambiguity_markers() -> None:
    mapping = map_question_intent(
        "Show refund totals by calendar quarter.",
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "unsupported"
    assert mapping.metric is None
    assert mapping.dimensions == []
    assert mapping.filters == []
    assert mapping.clarification is not None


def test_intent_mapping_fails_closed_for_generic_vendor_spend_ambiguity_marker() -> None:
    mapping = map_question_intent(
        "Show vendor spend by calendar quarter.",
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "unsupported"
    assert mapping.metric is None
    assert mapping.dimensions == []
    assert mapping.filters == []
    assert mapping.clarification is not None


def test_intent_mapping_matches_approved_markers_on_token_boundaries() -> None:
    mapping = map_question_intent(
        "Show notapproved vendor spend for Q1.",
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "unsupported"
    assert mapping.metric is None
    assert mapping.dimensions == []
    assert mapping.filters == []
    assert mapping.clarification is not None


def test_intent_mapping_fails_closed_for_hyphenated_unapproved_spend() -> None:
    mapping = map_question_intent(
        "Compare approved and unapproved-spend by vendor for Q1.",
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "unsupported"
    assert mapping.metric is None
    assert mapping.dimensions == []
    assert mapping.filters == []
    assert mapping.clarification is not None


def test_intent_mapping_fails_closed_for_unsupported_epic_aa_fixture() -> None:
    mapping = map_question_intent(
        _fixture_question("unsupported_answer"),
        semantic_contract_version="approved_vendor_spend.v1",
    )

    assert mapping.status == "unsupported"
    assert mapping.metric is None
    assert mapping.dimensions == []
    assert mapping.filters == []
    assert mapping.clarification is not None
