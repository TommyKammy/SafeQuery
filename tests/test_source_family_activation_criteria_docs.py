from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVATION_DOC = REPO_ROOT / "docs" / "design" / "target-source-registry.md"


def test_future_source_family_activation_gate_is_documented() -> None:
    content = ACTIVATION_DOC.read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())

    assert "## Future Source-Family Activation Gate" in content

    required_states = [
        "`planned`",
        "`unsupported`",
        "`activation-candidate`",
        "`active-baseline`",
    ]
    for state in required_states:
        assert state in content

    required_categories = [
        "Guard readiness",
        "Runtime readiness",
        "Secrets readiness",
        "Audit readiness",
        "Evaluation readiness",
        "Dataset-contract readiness",
        "Row-bounds readiness",
    ]
    for category in required_categories:
        assert category in content

    fail_closed_blockers = [
        "missing guard readiness",
        "missing runtime readiness",
        "missing secrets readiness",
        "missing audit readiness",
        "missing evaluation readiness",
    ]
    for blocker in fail_closed_blockers:
        assert blocker in normalized_content

    assert "No planned or unsupported family may dispatch connector code" in content
