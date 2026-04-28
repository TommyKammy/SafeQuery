from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SELECTION_DOC = REPO_ROOT / "docs" / "design" / "source-family-activation-selection.md"


def _section(content: str, header: str) -> str:
    start = content.find(header)
    assert start != -1, f"missing section {header}"
    next_section = content.find("\n## ", start + len(header))
    return content[start : next_section if next_section != -1 else len(content)]


def test_first_planning_candidate_selection_is_recorded() -> None:
    content = SELECTION_DOC.read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    assert "Recommended first planning candidate: Aurora PostgreSQL" in content
    assert "`source_family=postgresql`" in content
    assert "`source_flavor=aurora-postgresql`" in content
    assert "active connector implementation is out of scope" in normalized

    for source in [
        "target-source-registry.md",
        "security/threat-model.md",
        "dialect-capability-matrix.md",
        "dialect-guard-readiness-checklists.md",
        "evaluation-harness.md",
    ]:
        assert source in content


def test_deferred_families_have_explicit_blockers() -> None:
    content = SELECTION_DOC.read_text(encoding="utf-8")
    deferral_section = _section(content, "## Deferred Families")
    normalized_deferral_section = " ".join(deferral_section.split())

    expected_blockers = {
        "`mysql`": [
            "missing MySQL-specific guard readiness",
            "missing MySQL runtime readiness",
            "missing MySQL secrets readiness",
            "missing MySQL release-gate reconstruction",
        ],
        "`mariadb`": [
            "missing MariaDB-specific guard readiness",
            "missing MariaDB runtime readiness",
            "missing MariaDB secrets readiness",
            "missing MariaDB release-gate reconstruction",
        ],
        "`mysql` / `aurora-mysql`": [
            "blocked by the underlying MySQL family",
            "missing Aurora MySQL flavor regression evidence",
        ],
        "`oracle`": [
            "missing Oracle-specific guard readiness",
            "missing Oracle runtime and wallet readiness",
            "missing Oracle release-gate reconstruction",
        ],
    }

    for family, blockers in expected_blockers.items():
        assert family in deferral_section
        for blocker in blockers:
            assert blocker in normalized_deferral_section


def test_selection_preserves_non_executable_metadata_boundary() -> None:
    content = SELECTION_DOC.read_text(encoding="utf-8")
    boundary_section = _section(content, "## Non-Executable Boundary")
    normalized_boundary = " ".join(boundary_section.split())

    for phrase in [
        "does not add connector code",
        "does not wire runtime drivers",
        "does not add secret handling",
        "does not add SQL execution support",
        "planned metadata only",
        "must not appear in active execution coverage",
    ]:
        assert phrase in normalized_boundary


def test_next_roadmap_handoff_artifact_is_defined() -> None:
    content = SELECTION_DOC.read_text(encoding="utf-8")
    handoff_section = _section(content, "## Next-Roadmap Handoff")
    normalized_handoff_section = " ".join(handoff_section.split())

    for requirement in [
        "Aurora PostgreSQL activation planning packet",
        "registry profile draft",
        "flavor-specific runtime readiness plan",
        "backend-owned secret indirection plan",
        "fixture manifest",
        "release-gate reconstruction plan",
        "operator-history checklist",
        "must be reviewed before active connector implementation is scoped",
    ]:
        assert requirement in normalized_handoff_section
