from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.features.evaluation import (
    ReviewLLMCalibrationCategory,
    build_review_llm_calibration_report,
    validate_review_llm_calibration_fixture_set,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "review_llm_calibration_fixtures.json"


def _load_fixture_set() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_review_llm_calibration_fixture_set_is_schema_valid() -> None:
    fixture_set = _load_fixture_set()
    validated = validate_review_llm_calibration_fixture_set(fixture_set)

    assert validated.fixture_set == "review_llm_calibration.v0"
    assert validated.format_status == "review_llm_calibration.v1"
    assert validated.release_gate_authority is False
    assert "does not make Review LLM release-gate authority" in (
        validated.authority_note
    )

    categories = {fixture.category for fixture in validated.fixtures}
    assert categories == {
        "false_approval",
        "false_denial",
        "ambiguity",
        "source_confusion",
    }

    by_category = {
        category: [
            fixture
            for fixture in validated.fixtures
            if fixture.category == category
        ]
        for category in categories
    }
    assert by_category["false_approval"][0].expected_review_status == "blocked"
    assert by_category["false_denial"][0].expected_review_status == "ready"
    assert by_category["ambiguity"][0].expected_review_status == "needs_clarification"
    assert by_category["source_confusion"][0].expected_review_status == "blocked"


def test_review_llm_calibration_report_lists_failure_categories_separately() -> None:
    fixture_set = validate_review_llm_calibration_fixture_set(_load_fixture_set())
    report = build_review_llm_calibration_report(fixture_set)

    assert report.fixture_count == len(fixture_set.fixtures)
    assert report.release_gate_authority is False
    assert report.authority_statement == fixture_set.authority_note
    assert set(report.failure_categories) == {
        "false_approval",
        "false_denial",
        "ambiguity",
        "source_confusion",
    }
    assert report.failure_categories["false_approval"].fixture_count >= 1
    assert report.failure_categories["false_denial"].fixture_count >= 1
    assert report.failure_categories["ambiguity"].fixture_count >= 1
    assert report.failure_categories["source_confusion"].fixture_count >= 1
    assert "malformed_output" not in report.failure_categories
    assert report.malformed_output_handling == "excluded_parser_contract"


def test_review_llm_calibration_requires_false_approval_and_false_denial_cases() -> None:
    fixture_set = _load_fixture_set()
    fixture_set["fixtures"] = [
        fixture
        for fixture in fixture_set["fixtures"]  # type: ignore[index]
        if fixture["category"] != "false_denial"
    ]

    with pytest.raises(ValidationError, match="false approval, false denial"):
        validate_review_llm_calibration_fixture_set(fixture_set)


def test_review_llm_calibration_rejects_release_gate_authority_claim() -> None:
    fixture_set = _load_fixture_set()
    fixture_set["release_gate_authority"] = True

    with pytest.raises(ValidationError, match="must not grant release-gate authority"):
        validate_review_llm_calibration_fixture_set(fixture_set)


def test_review_llm_calibration_categories_are_closed() -> None:
    assert set(ReviewLLMCalibrationCategory.__args__) == {
        "false_approval",
        "false_denial",
        "ambiguity",
        "source_confusion",
    }
