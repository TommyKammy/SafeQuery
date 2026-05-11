from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FLOW_DOC = REPO_ROOT / "docs" / "design" / "runtime-flow.md"
ROADMAP_DOC = REPO_ROOT / "docs" / "implementation-roadmap.md"


def test_runtime_flow_does_not_claim_unimplemented_rate_or_concurrency_enforcement() -> None:
    runtime_flow = RUNTIME_FLOW_DOC.read_text(encoding="utf-8")

    overstatements = (
        "Generate-path rate limits and concurrency checks apply",
        "Execute-path rate limits and concurrency checks are applied",
        "If rate limits or concurrency limits are exceeded",
    )

    for overstatement in overstatements:
        assert overstatement not in runtime_flow


def test_roadmap_tracks_preview_execute_rate_and_concurrency_enforcement() -> None:
    roadmap = ROADMAP_DOC.read_text(encoding="utf-8")

    required_phrases = (
        "preview and execute rate-limit and concurrency enforcement",
        "authenticated subject, source, and endpoint kind",
        "deterministic public deny codes",
        "audit denial events",
        "burst and concurrent request tests",
    )

    for phrase in required_phrases:
        assert phrase in roadmap
