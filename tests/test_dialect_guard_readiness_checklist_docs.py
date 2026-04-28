from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKLIST_DOC = REPO_ROOT / "docs" / "design" / "dialect-guard-readiness-checklists.md"


def _section(content: str, header: str) -> str:
    start = content.find(header)
    assert start != -1, f"missing section {header}"
    next_section = content.find("\n## ", start + len(header))
    return content[start : next_section if next_section != -1 else len(content)]


def test_planned_dialect_guard_readiness_checklists_are_reviewable() -> None:
    content = CHECKLIST_DOC.read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    for phrase in [
        "checklist/evaluation planning only",
        "No new guard profile is activated",
        "release-gate reconstruction",
        "must remain non-executable",
        "missing checklist evidence",
    ]:
        assert phrase in normalized

    common_section = _section(content, "## Common Evidence Required")
    for requirement in [
        "Canonicalization fixtures",
        "Deny corpus fixtures",
        "System catalog access fixtures",
        "Mutating statement fixtures",
        "Comment and hint fixtures",
        "Function and procedure fixtures",
        "Dialect-specific edge-case fixtures",
    ]:
        assert requirement in common_section

    family_expectations = {
        "## MySQL Guard Readiness Checklist": [
            "backtick identifier",
            "sql_mode",
            "information_schema",
            "multi-statement",
            "LIMIT",
            "stored procedure",
        ],
        "## MariaDB Guard Readiness Checklist": [
            "MariaDB mode",
            "version-specific",
            "executable comments",
            "optimizer hints",
            "information_schema",
            "separate MariaDB",
        ],
        "## Aurora PostgreSQL Guard Readiness Checklist": [
            "source_family=postgresql",
            "source_flavor=aurora-postgresql",
            "PostgreSQL guard profile",
            "cluster or instance endpoint",
            "flavor regression",
        ],
        "## Aurora MySQL Guard Readiness Checklist": [
            "source_family=mysql",
            "source_flavor=aurora-mysql",
            "MySQL guard profile",
            "cluster or instance endpoint",
            "underlying MySQL family",
        ],
        "## Oracle Guard Readiness Checklist": [
            "PL/SQL",
            "database link",
            "package state",
            "session mutation",
            "FETCH FIRST",
            "ROWNUM",
        ],
    }
    for header, phrases in family_expectations.items():
        family_section = _section(content, header)
        normalized_family_section = " ".join(family_section.split())
        for phrase in phrases:
            assert phrase in normalized_family_section
