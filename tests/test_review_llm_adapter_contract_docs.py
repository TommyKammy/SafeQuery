from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO_ROOT / "docs" / "design" / "review-llm-adapter-contract.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"
READING_ORDER = REPO_ROOT / "docs" / "01_READING_ORDER.md"


def test_review_llm_adapter_contract_documents_critique_only_boundary() -> None:
    content = CONTRACT_DOC.read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    for phrase in [
        "critique-only boundary",
        "not an authorization source",
        "must not approve SQL",
        "Low confidence cannot be returned with `ready`",
        "Malformed output must fail closed",
        "SQL Guard and backend candidate lifecycle remain the enforcement boundary",
        "Review uses a separate prompt boundary and model configuration from SQL generation",
        "SAFEQUERY_REVIEW_LLM_*",
        "It does not eliminate correlated failure",
        "source credentials, connection strings, result rows, or runtime secrets",
    ]:
        assert phrase in normalized

    for forbidden_field in [
        "canAuthorizeExecution",
        "executionAuthorized",
        "approvalStatus",
        "queryCandidateId",
    ]:
        assert forbidden_field in content


def test_review_llm_adapter_contract_is_listed_in_docs_entrypoints() -> None:
    docs_readme = DOCS_README.read_text(encoding="utf-8")
    reading_order = READING_ORDER.read_text(encoding="utf-8")

    assert "design/review-llm-adapter-contract.md" in docs_readme
    assert "design/review-llm-adapter-contract.md" in reading_order
