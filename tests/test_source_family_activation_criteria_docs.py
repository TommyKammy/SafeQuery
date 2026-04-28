from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTIVATION_DOC = REPO_ROOT / "docs" / "design" / "target-source-registry.md"


def test_future_source_family_activation_gate_is_documented() -> None:
    content = ACTIVATION_DOC.read_text(encoding="utf-8")
    header = "## Future Source-Family Activation Gate"
    start = content.find(header)
    assert start != -1

    next_section = content.find("\n## ", start + len(header))
    activation_section = content[start : next_section if next_section != -1 else len(content)]
    normalized_activation_section = " ".join(activation_section.split())

    required_states = [
        "`planned`",
        "`unsupported`",
        "`activation-candidate`",
        "`active-baseline`",
    ]
    for state in required_states:
        assert state in activation_section

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
        assert category in activation_section

    fail_closed_blockers = [
        "missing guard readiness",
        "missing runtime readiness",
        "missing secrets readiness",
        "missing audit readiness",
        "missing evaluation readiness",
        "missing dataset-contract readiness",
        "missing row-bounds readiness",
    ]
    for blocker in fail_closed_blockers:
        assert blocker in normalized_activation_section

    assert (
        "No planned or unsupported family may dispatch connector code"
        in normalized_activation_section
    )
