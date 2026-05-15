from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "governed_answer_vendor_spend_fixtures.json"
)


MACOS_HOME_ROOT = "/" + "Users" + "/"
LINUX_HOME_ROOT = "/" + "home" + "/"
WINDOWS_HOME_ROOT = "Users" + r"\\"
HOME_PATH_PATTERN = re.compile(
    "("
    + re.escape(MACOS_HOME_ROOT)
    + r"[^\s\"']+|"
    + re.escape(LINUX_HOME_ROOT)
    + r"[^\s\"']+|"
    + r"[A-Za-z]:\\"
    + WINDOWS_HOME_ROOT
    + ")"
)
REQUIRED_FIXTURE_FIELDS = {
    "id",
    "question",
    "case_type",
    "source_binding",
    "expected_intent",
    "metric",
    "dimensions",
    "filters",
    "acceptable_sql_shape",
    "expected_result_shape",
    "ambiguity_status",
    "forbidden_answer_claims",
    "expected_correctness_level",
    "human_authoring_minutes",
    "domain_expert_review_required",
}


def _load_fixture_set() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_governed_answer_vendor_spend_fixture_set_is_schema_valid() -> None:
    fixture_set = _load_fixture_set()

    assert fixture_set["fixture_set"] == "governed_answer_vendor_spend.v0"
    assert fixture_set["domain"] == "approved_vendor_spend"
    assert fixture_set["source_profile"]["source_id"] == "business-postgres-source"
    assert fixture_set["source_profile"]["source_family"] == "postgresql"
    assert fixture_set["source_profile"]["source_flavor"] == "warehouse"
    assert fixture_set["source_profile"]["dataset_contract_version"] == 4
    assert fixture_set["source_profile"]["schema_snapshot_version"] == 9
    assert fixture_set["source_profile"]["execution_policy_version"] == 3

    fixtures = fixture_set["fixtures"]
    assert 5 <= len(fixtures) <= 10
    assert len({fixture["id"] for fixture in fixtures}) == len(fixtures)

    ambiguity_cases = 0
    negative_or_adversarial_cases = 0
    source_bound_cases = 0
    total_authoring_minutes = 0

    for fixture in fixtures:
        assert REQUIRED_FIXTURE_FIELDS <= fixture.keys()
        assert fixture["question"].strip()
        assert fixture["case_type"] in {
            "positive",
            "ambiguity",
            "negative",
            "adversarial",
        }
        assert fixture["ambiguity_status"] in {
            "unambiguous",
            "ambiguous_requires_clarification",
            "unsafe_or_out_of_scope",
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

        source_binding = fixture["source_binding"]
        assert source_binding["source_id"] == fixture_set["source_profile"]["source_id"]
        assert source_binding["schema"] == "finance"
        assert source_binding["table"] == "approved_vendor_spend"
        source_bound_cases += 1

        if fixture["case_type"] == "ambiguity":
            ambiguity_cases += 1
            assert (
                fixture["expected_correctness_level"]
                == "ambiguity_clarification_required"
            )
        if fixture["case_type"] in {"negative", "adversarial"}:
            negative_or_adversarial_cases += 1
            assert fixture["expected_correctness_level"] == "deny_required"

        total_authoring_minutes += fixture["human_authoring_minutes"]

    assert ambiguity_cases >= 2
    assert negative_or_adversarial_cases >= 2
    assert source_bound_cases == len(fixtures)
    assert fixture_set["authoring_summary"]["estimated_authoring_minutes"] == (
        total_authoring_minutes
    )
    assert fixture_set["authoring_summary"]["estimated_review_minutes"] > 0


def test_governed_answer_vendor_spend_fixtures_avoid_workstation_paths() -> None:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")

    assert not HOME_PATH_PATTERN.search(fixture_text)
