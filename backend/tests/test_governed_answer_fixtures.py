from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.features.evaluation import validate_governed_answer_fixture_set


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


def _load_fixture_set() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


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
    assert 5 <= len(fixtures) <= 10
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
