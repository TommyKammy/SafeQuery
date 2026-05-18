from __future__ import annotations

import json

from app.features.review_llm import (
    build_answer_plan_from_review,
    parse_review_llm_adapter_output,
)


def _review_payload() -> dict[str, object]:
    return {
        "status": "ready",
        "confidence": "high",
        "intent_summary": "Compare approved vendor spend by fiscal quarter.",
        "data_used": ["approved_vendor_spend semantic contract v1"],
        "metrics": ["Approved vendor spend"],
        "dimensions": ["Vendor", "Fiscal quarter"],
        "filters": ["Approved spend only"],
        "assumptions": ["Quarter means fiscal quarter."],
        "risk_flags": [],
        "clarifying_questions": [],
        "diagnostics": {
            "adapter_version": "review_llm_contract.v1",
            "model": "contract-test",
            "raw_output_excerpt": "postgresql://reader:secret-value@db/business",
        },
    }


def test_answer_plan_turns_candidate_review_into_business_readable_snapshot() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Which approved vendors had the highest quarterly spend?",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "mapping_id": "show_top_approved_vendors_by_quarterly_spend",
            "classification": "supported",
            "metric": "sum_approved_vendor_spend",
            "dimensions": ["vendor_name", "fiscal_quarter"],
            "filters": ["approved_spend_only"],
        },
        candidate_metadata={
            "candidate_id": "candidate-123",
            "source_id": "business-postgres-source",
            "source_family": "postgresql",
            "selected_columns": ["vendor_name", "fiscal_quarter", "approved_spend"],
            "row_limit": 100,
            "raw_sql": "SELECT vendor_secret FROM finance.approved_vendor_spend",
            "result_rows": [{"vendor_secret": "sk-live-should-not-leak"}],
        },
        guard_metadata={
            "guard_decision": "allow",
            "guard_version": "postgresql-guard-v1",
        },
    )

    assert plan.to_wire_payload() == {
        "contractVersion": "answer_plan.v1",
        "question": "Which approved vendors had the highest quarterly spend?",
        "narrative": (
            "The candidate is intended to compare approved vendor spend by fiscal "
            "quarter. It should group the answer by Vendor and Fiscal quarter, "
            "use Approved vendor spend as the measure, and apply Approved spend "
            "only. Semantic contract evidence: approved_vendor_spend.v1 / "
            "show_top_approved_vendors_by_quarterly_spend."
        ),
        "steps": [
            "Answer the question using candidate candidate-123 for source business-postgres-source.",
            "Use the approved business metric Approved vendor spend.",
            "Group or label the answer by Vendor and Fiscal quarter.",
            "Apply the business filter Approved spend only.",
            "Keep the output at plan level; do not summarize result rows in this step.",
        ],
        "assumptions": ["Quarter means fiscal quarter."],
        "risks": [],
        "clarifications": [],
        "semanticEvidence": [
            {
                "contractVersion": "approved_vendor_spend.v1",
                "mappingId": "show_top_approved_vendors_by_quarterly_spend",
                "classification": "supported",
                "metric": "sum_approved_vendor_spend",
                "dimensions": ["vendor_name", "fiscal_quarter"],
                "filters": ["approved_spend_only"],
            }
        ],
        "candidateSummary": {
            "candidateId": "candidate-123",
            "sourceId": "business-postgres-source",
            "sourceFamily": "postgresql",
            "selectedColumns": ["vendor_name", "fiscal_quarter", "approved_spend"],
            "rowLimit": 100,
        },
        "guardSummary": {
            "guardDecision": "allow",
            "guardVersion": "postgresql-guard-v1",
        },
        "advisoryOnly": True,
        "canAuthorizeExecution": False,
    }


def test_answer_plan_lists_unsupported_assumptions_as_risks_or_clarifications() -> None:
    review = parse_review_llm_adapter_output(
        {
            **_review_payload(),
            "status": "needs_clarification",
            "confidence": "medium",
            "assumptions": ["Refunds are excluded, but the contract does not prove it."],
            "risk_flags": ["Refund handling is unsupported by the semantic mapping."],
            "clarifying_questions": ["Should refunded spend be excluded?"],
        }
    )

    plan = build_answer_plan_from_review(
        question="Show quarterly spend net of refunds.",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "ambiguous",
            "ambiguity_rule_refs": ["spend_definition"],
        },
        candidate_metadata={"candidate_id": "candidate-123"},
        guard_metadata={"guard_decision": "allow"},
    )

    assert "Refund handling is unsupported by the semantic mapping." in plan.risks
    assert (
        "Semantic mapping is ambiguous; do not present the plan as a final answer."
        in plan.risks
    )
    assert plan.clarifications == ("Should refunded spend be excluded?",)
    assert plan.can_authorize_execution is False


def test_answer_plan_redacts_secret_like_prompt_and_output_context() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question='Use token=raw-secret-token and {"password":"quoted-secret"} to show vendor spend.',
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
            "metric": "sum_approved_vendor_spend",
        },
        candidate_metadata={
            "candidate_id": "candidate-123",
            "source_id": "business-postgres-source",
            "selected_columns": ["vendor_secret", "approved_spend"],
            "connection_string": "postgresql://reader:secret-value@db/business",
            "scratchpad": "hidden chain of thought with password=hunter2",
        },
        guard_metadata={
            "guard_decision": "reject",
            "denial_reason": "Driver failed with {'token': 'quoted-token'} and password=hunter2",
        },
    )

    serialized = json.dumps(plan.to_wire_payload(), sort_keys=True).lower()

    assert "raw-secret-token" not in serialized
    assert "quoted-secret" not in serialized
    assert "quoted-token" not in serialized
    assert "secret-value" not in serialized
    assert "hunter2" not in serialized
    assert "vendor_secret" not in serialized
    assert "password" not in serialized
    assert "secret" not in serialized
    assert "token" not in serialized
    assert "scratchpad" not in serialized
    assert "connection_string" not in serialized
    assert "canAuthorizeExecution" not in plan.model_dump()


def test_answer_plan_omits_unknown_source_family_without_failing() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Which approved vendors had the highest quarterly spend?",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
        },
        candidate_metadata={
            "candidate_id": "candidate-123",
            "source_id": "business-mysql-source",
            "source_family": "mysql",
        },
        guard_metadata={"guard_decision": "allow"},
    )

    candidate_summary = plan.to_wire_payload()["candidateSummary"]
    assert candidate_summary["candidateId"] == "candidate-123"
    assert candidate_summary["sourceId"] == "business-mysql-source"
    assert "sourceFamily" not in candidate_summary
