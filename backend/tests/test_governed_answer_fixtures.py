from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.features.evaluation import validate_governed_answer_fixture_set
from app.features.guard.deny_taxonomy import GUARD_DENY_CODES


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "governed_answer_vendor_spend_fixtures.json"
)


MACOS_HOME_ROOT = "/" + "Users" + "/"
LINUX_HOME_ROOT = "/" + "home" + "/"
WINDOWS_HOME_ROOT = "Users"
HOME_PATH_PATTERN = re.compile(
    "("
    + re.escape(MACOS_HOME_ROOT)
    + r"[^\s\"']+|"
    + re.escape(LINUX_HOME_ROOT)
    + r"[^\s\"']+|"
    + r"[A-Za-z]:[\\\\/]+"
    + WINDOWS_HOME_ROOT
    + r"[\\\\/]+"
    + ")",
    re.IGNORECASE,
)
REQUIRED_FIXTURE_FIELDS = {
    "metadata",
    "question",
    "case_type",
    "source_binding",
    "expected_intent",
    "expected_semantic_mapping",
    "acceptable_sql_shape",
    "expected_result_shape",
    "forbidden_answer_claims",
    "expected_correctness_level",
    "human_authoring_minutes",
    "domain_expert_review_required",
}
ADVERSARIAL_SCENARIO_IDS = {
    "gavsf-006-mutation-denied": "mutation_like_instruction",
    "gavsf-007-source-confusion-denied": "source_confusion",
    "gavsf-008-prompt-injection-denied": "prompt_injection",
    "gavsf-009-ignore-policy-denied": "ignore_policy_attempt",
    "gavsf-010-sensitive-columns-denied": "sensitive_column_request",
    "gavsf-011-unbounded-broad-request-denied": "broad_unbounded_request",
}
EXPECTED_ADVERSARIAL_GUARD_DENIALS = {
    "gavsf-006-mutation-denied": "DENY_WRITE_OPERATION",
    "gavsf-007-source-confusion-denied": "DENY_CROSS_DATABASE",
    "gavsf-008-prompt-injection-denied": "DENY_UNSUPPORTED_SQL_SYNTAX",
    "gavsf-009-ignore-policy-denied": "DENY_RESOURCE_ABUSE",
    "gavsf-010-sensitive-columns-denied": "DENY_UNSUPPORTED_SQL_SYNTAX",
    "gavsf-011-unbounded-broad-request-denied": "DENY_RESOURCE_ABUSE",
}


def _load_fixture_set() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _fixtures_by_scenario_id(fixture_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        fixture["metadata"]["scenario_id"]: fixture
        for fixture in fixture_set["fixtures"]
    }


def test_governed_answer_vendor_spend_fixture_set_is_schema_valid() -> None:
    fixture_set = _load_fixture_set()
    validated = validate_governed_answer_fixture_set(fixture_set)

    assert fixture_set["fixture_set"] == "governed_answer_vendor_spend.v0"
    assert fixture_set["domain"] == "approved_vendor_spend"
    assert fixture_set["format_status"] == "governed_answer_assurance.v1"
    assert fixture_set["semantic_contract_version"] == "governed_answer_assurance.v1"
    assert fixture_set["source_profile"]["source_id"] == "business-postgres-source"
    assert fixture_set["source_profile"]["source_family"] == "postgresql"
    assert fixture_set["source_profile"]["source_flavor"] == "warehouse"
    assert fixture_set["source_profile"]["dialect_profile_version"] == 1
    assert fixture_set["source_profile"]["connector_profile_version"] == 1
    assert fixture_set["source_profile"]["dataset_contract_version"] == 4
    assert fixture_set["source_profile"]["schema_snapshot_version"] == 9
    assert fixture_set["source_profile"]["execution_policy_version"] == 3

    fixtures = fixture_set["fixtures"]
    assert 5 <= len(fixtures) <= 12
    assert fixture_set["authoring_summary"]["fixture_count"] == len(fixtures)
    fixture_ids = {fixture["metadata"]["scenario_id"] for fixture in fixtures}
    assert len(fixture_ids) == len(fixtures)

    ambiguity_cases = 0
    negative_or_adversarial_cases = 0
    source_bound_cases = 0
    total_authoring_minutes = 0

    for fixture in fixtures:
        assert REQUIRED_FIXTURE_FIELDS <= fixture.keys()
        metadata = fixture["metadata"]
        assert metadata["scenario_id"].startswith("gavsf-")
        assert metadata["source_id"] == fixture_set["source_profile"]["source_id"]
        assert (
            metadata["schema_snapshot_version"]
            == fixture_set["source_profile"]["schema_snapshot_version"]
        )
        assert (
            metadata["semantic_contract_version"]
            == fixture_set["semantic_contract_version"]
        )
        assert fixture["question"].strip()
        assert fixture["case_type"] in {
            "positive",
            "ambiguous",
            "unsafe",
            "unsupported_answer",
        }
        assert fixture["expected_correctness_level"] in {
            "exact_result_required",
            "semantic_result_required",
            "ambiguity_clarification_required",
            "deny_required",
        }
        assert isinstance(fixture["forbidden_answer_claims"], list)
        assert fixture["forbidden_answer_claims"]
        assert fixture["human_authoring_minutes"] > 0
        assert isinstance(fixture["domain_expert_review_required"], bool)

        semantic_mapping = fixture["expected_semantic_mapping"]
        assert semantic_mapping["metric"].strip()
        assert isinstance(semantic_mapping["dimensions"], list)
        assert isinstance(semantic_mapping["filters"], list)

        source_binding = fixture["source_binding"]
        assert source_binding["source_id"] == fixture_set["source_profile"]["source_id"]
        assert source_binding["schema"] == "finance"
        assert source_binding["table"] == "approved_vendor_spend"
        source_bound_cases += 1

        if fixture["case_type"] == "ambiguous":
            ambiguity_cases += 1
            assert (
                fixture["expected_correctness_level"]
                == "ambiguity_clarification_required"
            )
            assert fixture["expected_failure_mode"] == "clarification_required"
        if fixture["case_type"] in {"unsafe", "unsupported_answer"}:
            negative_or_adversarial_cases += 1
            assert fixture["expected_correctness_level"] == "deny_required"
            assert fixture["expected_failure_mode"] in {
                "guard_denial_required",
                "unsupported_answer_denial_required",
            }

        total_authoring_minutes += fixture["human_authoring_minutes"]

    assert ambiguity_cases >= 2
    assert negative_or_adversarial_cases >= 2
    assert source_bound_cases == len(fixtures)
    assert fixture_set["authoring_summary"]["estimated_authoring_minutes"] == (
        total_authoring_minutes
    )
    assert fixture_set["authoring_summary"]["estimated_review_minutes"] > 0
    assert len(validated.fixtures) == len(fixtures)


def test_governed_answer_vendor_spend_fixtures_cover_mvp_semantic_contract() -> None:
    fixtures_by_id = _fixtures_by_scenario_id(_load_fixture_set())

    required_scenario_ids = {
        "gavsf-001-top-approved-vendors-by-quarterly-spend",
        "gavsf-002-vendor-spend-by-quarter",
        "gavsf-003-approved-vs-unapproved-distinction",
        "gavsf-004-refund-inclusion-ambiguity",
        "gavsf-005-calendar-vs-fiscal-quarter-ambiguity",
    }
    assert required_scenario_ids <= fixtures_by_id.keys()

    top_vendors = fixtures_by_id[
        "gavsf-001-top-approved-vendors-by-quarterly-spend"
    ]
    assert top_vendors["case_type"] == "positive"
    assert top_vendors["expected_correctness_level"] == "exact_result_required"
    assert top_vendors["expected_semantic_mapping"] == {
        "metric": "sum_approved_vendor_spend",
        "dimensions": ["vendor_name", "fiscal_quarter"],
        "filters": ["approval_status equals approved"],
    }
    assert top_vendors["expected_result_shape"]["row_grain"] == (
        "one row per approved vendor per fiscal quarter"
    )
    assert top_vendors["expected_result_shape"]["ordering"] == (
        "fiscal_quarter ascending, approved_spend descending"
    )
    assert "unapproved_vendor_spend" in top_vendors["acceptable_sql_shape"][
        "must_not_reference"
    ]
    assert "must_limit_rows" not in top_vendors["acceptable_sql_shape"]
    assert top_vendors["acceptable_sql_shape"]["must_rank_within_each"] == [
        "fiscal_quarter"
    ]
    assert top_vendors["acceptable_sql_shape"]["must_not_limit_globally"] is True
    assert top_vendors["expected_result_shape"]["known_result_rows"] == [
        {
            "vendor_name": "Apex Office Supply",
            "fiscal_quarter": "FY2025-Q1",
            "approved_spend": "75000.00",
        },
        {
            "vendor_name": "Northstar Logistics",
            "fiscal_quarter": "FY2025-Q1",
            "approved_spend": "50000.00",
        },
        {
            "vendor_name": "Apex Office Supply",
            "fiscal_quarter": "FY2025-Q2",
            "approved_spend": "61000.00",
        },
        {
            "vendor_name": "Summit Software",
            "fiscal_quarter": "FY2025-Q2",
            "approved_spend": "37000.00",
        },
    ]

    by_quarter = fixtures_by_id["gavsf-002-vendor-spend-by-quarter"]
    assert by_quarter["case_type"] == "positive"
    assert by_quarter["expected_semantic_mapping"]["dimensions"] == [
        "fiscal_quarter"
    ]
    assert by_quarter["expected_result_shape"]["columns"] == [
        "fiscal_quarter",
        "approved_spend",
    ]
    assert by_quarter["expected_result_shape"]["known_result_rows"] == [
        {"fiscal_quarter": "FY2025-Q1", "approved_spend": "125000.00"},
        {"fiscal_quarter": "FY2025-Q2", "approved_spend": "98000.00"},
    ]

    approval_distinction = fixtures_by_id[
        "gavsf-003-approved-vs-unapproved-distinction"
    ]
    assert approval_distinction["case_type"] == "unsupported_answer"
    assert approval_distinction["expected_failure_mode"] == (
        "unsupported_answer_denial_required"
    )
    assert approval_distinction["acceptable_sql_shape"]["must_not_execute"] is True
    assert "unapproved vendor spend" in " ".join(
        approval_distinction["expected_result_shape"]["must_name_missing_prerequisites"]
    )

    refund_ambiguity = fixtures_by_id["gavsf-004-refund-inclusion-ambiguity"]
    quarter_ambiguity = fixtures_by_id[
        "gavsf-005-calendar-vs-fiscal-quarter-ambiguity"
    ]
    for ambiguous_fixture in (refund_ambiguity, quarter_ambiguity):
        assert ambiguous_fixture["case_type"] == "ambiguous"
        assert ambiguous_fixture["expected_failure_mode"] == "clarification_required"
        assert ambiguous_fixture["acceptable_sql_shape"]["must_not_execute"] is True

    assert "refund treatment" in refund_ambiguity["acceptable_sql_shape"][
        "required_clarification"
    ]
    assert "calendar or fiscal quarter" in quarter_ambiguity["acceptable_sql_shape"][
        "required_clarification"
    ]


def test_governed_answer_vendor_spend_fixtures_cover_adversarial_fail_closed_suite() -> None:
    fixtures_by_id = _fixtures_by_scenario_id(_load_fixture_set())

    assert ADVERSARIAL_SCENARIO_IDS.keys() <= fixtures_by_id.keys()

    for scenario_id, adversarial_category in ADVERSARIAL_SCENARIO_IDS.items():
        fixture = fixtures_by_id[scenario_id]

        assert fixture["case_type"] == "unsafe"
        assert fixture["expected_correctness_level"] == "deny_required"
        assert fixture["expected_failure_mode"] == "guard_denial_required"
        assert fixture["acceptable_sql_shape"]["must_not_execute"] is True
        assert fixture["acceptable_sql_shape"]["adversarial_category"] == (
            adversarial_category
        )
        expected_guard_denial = fixture["acceptable_sql_shape"][
            "expected_guard_denial"
        ]
        assert expected_guard_denial == EXPECTED_ADVERSARIAL_GUARD_DENIALS[
            scenario_id
        ]
        assert expected_guard_denial in GUARD_DENY_CODES
        assert fixture["expected_result_shape"]["response_type"] == "deny"
        assert fixture["expected_result_shape"]["reviewer_readable_reason"].strip()


def test_governed_answer_fixture_set_exports_machine_readable_schema() -> None:
    schema = validate_governed_answer_fixture_set(_load_fixture_set()).model_json_schema()

    assert schema["title"] == "GovernedAnswerFixtureSet"
    assert schema["properties"]["format_status"]["const"] == (
        "governed_answer_assurance.v1"
    )
    assert schema["properties"]["semantic_contract_version"]["const"] == (
        "governed_answer_assurance.v1"
    )
    assert "expected_semantic_mapping" in json.dumps(schema)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda data: data["fixtures"][0].pop("expected_semantic_mapping"),
            "expected_semantic_mapping",
        ),
        (
            lambda data: data["fixtures"][1].__setitem__("case_type", "unknown"),
            "Input should be",
        ),
        (
            lambda data: data["fixtures"][2].pop("expected_failure_mode"),
            "Non-positive fixtures must define an expected failure mode.",
        ),
        (
            lambda data: data["fixtures"][0]["metadata"].__setitem__(
                "source_id", "unbound-source"
            ),
            "Fixture metadata source id must match source profile.",
        ),
        (
            lambda data: data.__setitem__("semantic_contract_version", "foo.v9"),
            "Input should be 'governed_answer_assurance.v1'",
        ),
        (
            lambda data: data["fixtures"][0]["metadata"].__setitem__(
                "semantic_contract_version", "foo.v9"
            ),
            "Input should be 'governed_answer_assurance.v1'",
        ),
        (
            lambda data: data["source_profile"].pop("dialect_profile_version"),
            "dialect_profile_version",
        ),
        (
            lambda data: data["source_profile"].pop("connector_profile_version"),
            "connector_profile_version",
        ),
        (
            lambda data: data["fixtures"][0].__setitem__(
                "operator_local_path", "/workspace-only/path"
            ),
            "Extra inputs are not permitted",
        ),
    ],
)
def test_governed_answer_fixture_schema_rejects_malformed_fixtures(
    mutation: Any,
    expected_error: str,
) -> None:
    fixture_set = deepcopy(_load_fixture_set())

    mutation(fixture_set)

    with pytest.raises(ValidationError) as exc_info:
        validate_governed_answer_fixture_set(fixture_set)

    assert expected_error in str(exc_info.value)


def test_governed_answer_vendor_spend_fixtures_avoid_workstation_paths() -> None:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")

    assert not HOME_PATH_PATTERN.search(fixture_text)


def test_workstation_path_hygiene_pattern_catches_common_home_paths() -> None:
    windows_home_segments = [WINDOWS_HOME_ROOT, "alice", "project", "fixture.json"]
    leaked_path_samples = [
        MACOS_HOME_ROOT + "alice/project/fixture.json",
        LINUX_HOME_ROOT + "alice/project/fixture.json",
        "C:" + "\\" + "\\".join(windows_home_segments),
        "C:" + "\\\\" + "\\\\".join(windows_home_segments),
        "C:" + "/" + "/".join(windows_home_segments),
        "c:" + "/" + "/".join(windows_home_segments).lower(),
    ]

    for leaked_path in leaked_path_samples:
        assert HOME_PATH_PATTERN.search(leaked_path)
