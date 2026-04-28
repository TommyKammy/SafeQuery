from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
THREAT_MODEL_DOC = REPO_ROOT / "docs" / "security" / "threat-model.md"


def _section(content: str, header: str) -> str:
    start = content.find(header)
    assert start != -1, f"Missing section: {header}"

    header_prefix = header.split(" ", maxsplit=1)[0]
    assert header_prefix and set(header_prefix) == {"#"}, f"Invalid header: {header}"

    next_sections = [
        content.find(f"\n{'#' * level} ", start + len(header))
        for level in range(1, len(header_prefix) + 1)
    ]
    next_sections = [index for index in next_sections if index != -1]
    next_section = min(next_sections) if next_sections else -1
    return content[start : next_section if next_section != -1 else len(content)]


def test_section_stops_at_same_or_higher_heading_boundary() -> None:
    content = "\n".join(
        [
            "## Future Connector Threat Model",
            "intro",
            "### MySQL",
            "mysql details",
            "#### Nested context",
            "nested details",
            "### MariaDB",
            "mariadb details",
            "## Residual Risks",
            "residual details",
        ]
    )

    assert _section(content, "### MySQL") == "\n".join(
        [
            "### MySQL",
            "mysql details",
            "#### Nested context",
            "nested details",
        ]
    )
    assert _section(content, "## Future Connector Threat Model") == "\n".join(
        [
            "## Future Connector Threat Model",
            "intro",
            "### MySQL",
            "mysql details",
            "#### Nested context",
            "nested details",
            "### MariaDB",
            "mariadb details",
        ]
    )


def test_connector_threat_model_covers_planned_families_and_flavors() -> None:
    content = THREAT_MODEL_DOC.read_text(encoding="utf-8")
    connector_header = "## Future Connector Threat Model"
    start = content.find(connector_header)
    assert start != -1

    connector_section = content[start:]
    for header in [
        "### MySQL",
        "### MariaDB",
        "### Aurora PostgreSQL",
        "### Aurora MySQL",
        "### Oracle",
    ]:
        family_section = _section(connector_section, header)
        normalized = " ".join(family_section.split())
        for required_risk in [
            "dialect ambiguity",
            "privilege scope",
            "driver behavior",
            "secret handling",
            "result bounds",
            "audit evidence",
        ]:
            assert required_risk in normalized

        assert "Activation blocker" in family_section
        assert "Mitigation requirement" in family_section


def test_connector_threat_model_preserves_safequery_authority_boundary() -> None:
    content = THREAT_MODEL_DOC.read_text(encoding="utf-8")
    connector_section = _section(content, "## Future Connector Threat Model")
    normalized = " ".join(connector_section.split())

    required_boundary_claims = [
        "SafeQuery remains the application-owned trusted control boundary",
        "External systems, database drivers, adapter output, request metadata, hostnames, connection strings, MLflow traces, analyst artifacts, and operator-facing labels are not authority sources",
        "No planned family or flavor may dispatch connector code",
        "source registry",
        "activation gate",
    ]
    for claim in required_boundary_claims:
        assert claim in normalized
