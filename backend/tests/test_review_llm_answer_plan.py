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
    wire_payload = plan.to_wire_payload()
    assert wire_payload["advisoryOnly"] is True
    assert wire_payload["canAuthorizeExecution"] is False


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


def test_answer_plan_preserves_valid_source_id_with_secret_keyword() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Show quarterly spend for the configured source.",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
        },
        candidate_metadata={
            "candidate_id": "candidate-123",
            "source_id": "secret-source",
            "source_family": "mysql",
        },
        guard_metadata={"guard_decision": "allow"},
    )

    candidate_summary = plan.to_wire_payload()["candidateSummary"]
    assert candidate_summary["sourceId"] == "secret-source"
    assert "sourceFamily" not in candidate_summary


def test_answer_plan_redacts_spaced_secret_values_and_dsn_attributes() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Use token: alpha beta gamma",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
        },
        candidate_metadata={"candidate_id": "candidate-123"},
        guard_metadata={
            "guard_decision": "reject",
            "denial_reason": (
                "ODBC failed with Pwd={correct horse battery staple};"
                "Server=finance warehouse host;Password=multi word phrase"
            ),
        },
    )

    serialized = json.dumps(plan.to_wire_payload(), sort_keys=True).lower()

    assert "alpha beta gamma" not in serialized
    assert "correct horse battery staple" not in serialized
    assert "horse battery" not in serialized
    assert "finance warehouse host" not in serialized
    assert "multi word phrase" not in serialized


def test_answer_plan_redacts_escaped_quoted_secret_values() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question=r'Inspect {\\"password\\":\\"hunter2\\"} safely.',
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
        },
        candidate_metadata={"candidate_id": "candidate-123"},
        guard_metadata={
            "guard_decision": "reject",
            "denial_reason": r'Driver returned {\\"token\\":\\"raw-token\\"}.',
        },
    )

    serialized = json.dumps(plan.to_wire_payload(), sort_keys=True).lower()

    assert "hunter2" not in serialized
    assert "raw-token" not in serialized


def test_answer_plan_redacts_multiline_key_value_secret_values() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Use password=northwind\nsouthwind safely.",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
        },
        candidate_metadata={"candidate_id": "candidate-123"},
        guard_metadata={
            "guard_decision": "reject",
            "denial_reason": "Driver failed with token: redwood\ncedar; retry later",
        },
    )

    serialized = json.dumps(plan.to_wire_payload(), sort_keys=True).lower()

    assert "northwind" not in serialized
    assert "southwind" not in serialized
    assert "redwood" not in serialized
    assert "cedar" not in serialized


def test_answer_plan_redacts_basic_auth_credentials() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Retry with Basic dXNlcjpwYXNzLXNlY3JldA== safely.",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
        },
        candidate_metadata={"candidate_id": "candidate-123"},
        guard_metadata={
            "guard_decision": "reject",
            "denial_reason": "Authorization failed for Basic YXBpOnNlY3JldA==",
        },
    )

    serialized = json.dumps(plan.to_wire_payload(), sort_keys=True).lower()

    assert "dxnlcjpwyxnzlxnly3jlda" not in serialized
    assert "yxbponnly3jlda" not in serialized


def test_answer_plan_redacts_full_bearer_token_with_equals() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Use Bearer abc=def safely.",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
        },
        candidate_metadata={"candidate_id": "candidate-123"},
        guard_metadata={
            "guard_decision": "reject",
            "denial_reason": "Authorization failed for Bearer opaque-token==",
        },
    )

    serialized = json.dumps(plan.to_wire_payload(), sort_keys=True).lower()

    assert "abc=def" not in serialized
    assert "opaque-token==" not in serialized
    assert "=def" not in serialized


def test_answer_plan_rejects_non_string_selected_columns() -> None:
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
            "selected_columns": [
                {"customer": "alice", "amount": "999.00"},
                "approved_spend",
            ],
        },
        guard_metadata={"guard_decision": "allow"},
    )

    candidate_summary = plan.to_wire_payload()["candidateSummary"]
    assert candidate_summary["selectedColumns"] == []
    serialized = json.dumps(candidate_summary, sort_keys=True).lower()
    assert "alice" not in serialized
    assert "999.00" not in serialized


def test_answer_plan_rejects_non_string_semantic_evidence_items() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Which approved vendors had the highest quarterly spend?",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
            "dimensions": [{"customer": "alice", "amount": "999.00"}],
            "filters": ["approved_spend_only", {"token": "raw-token"}],
        },
        candidate_metadata={"candidate_id": "candidate-123"},
        guard_metadata={"guard_decision": "allow"},
    )

    semantic_evidence = plan.to_wire_payload()["semanticEvidence"][0]
    assert semantic_evidence["dimensions"] == []
    assert semantic_evidence["filters"] == []
    serialized = json.dumps(semantic_evidence, sort_keys=True).lower()
    assert "alice" not in serialized
    assert "999.00" not in serialized
    assert "raw-token" not in serialized


def test_answer_plan_orders_unordered_string_metadata_deterministically() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Which approved vendors had the highest quarterly spend?",
        review=review,
        semantic_mapping={
            "contract_version": "approved_vendor_spend.v1",
            "classification": "supported",
            "dimensions": {"vendor_name", "fiscal_quarter"},
            "filters": frozenset(("approved_spend_only", "current_quarter")),
        },
        candidate_metadata={
            "candidate_id": "candidate-123",
            "selected_columns": {"approved_spend", "vendor_name"},
        },
        guard_metadata={"guard_decision": "allow"},
    )

    semantic_evidence = plan.to_wire_payload()["semanticEvidence"][0]
    candidate_summary = plan.to_wire_payload()["candidateSummary"]
    assert semantic_evidence["dimensions"] == ["fiscal_quarter", "vendor_name"]
    assert semantic_evidence["filters"] == ["approved_spend_only", "current_quarter"]
    assert candidate_summary["selectedColumns"] == ["approved_spend", "vendor_name"]


def test_answer_plan_rejects_non_string_scalar_metadata() -> None:
    review = parse_review_llm_adapter_output(_review_payload())

    plan = build_answer_plan_from_review(
        question="Which approved vendors had the highest quarterly spend?",
        review=review,
        semantic_mapping={
            "contract_version": {"customer": "alice", "amount": "999.00"},
            "mapping_id": {"mapping": "customer-row"},
            "classification": "supported",
            "metric": {"token": "raw-token"},
        },
        candidate_metadata={
            "candidate_id": {"customer": "alice", "amount": "999.00"},
            "source_id": {"source": "business-postgres-source"},
        },
        guard_metadata={
            "guard_decision": "allow",
            "guard_version": {"version": "row-like-object"},
            "denial_reason": {"password": "hunter2"},
        },
    )

    wire_payload = plan.to_wire_payload()
    assert wire_payload["semanticEvidence"][0] == {
        "classification": "supported",
        "dimensions": [],
        "filters": [],
    }
    assert wire_payload["candidateSummary"]["selectedColumns"] == []
    assert wire_payload["guardSummary"] == {"guardDecision": "allow"}
    serialized = json.dumps(wire_payload, sort_keys=True).lower()
    assert "alice" not in serialized
    assert "999.00" not in serialized
    assert "customer-row" not in serialized
    assert "raw-token" not in serialized
    assert "hunter2" not in serialized


def test_answer_plan_rejects_overlong_source_id_without_failing() -> None:
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
            "source_id": "a" * 300,
        },
        guard_metadata={"guard_decision": "allow"},
    )

    candidate_summary = plan.to_wire_payload()["candidateSummary"]
    assert candidate_summary["candidateId"] == "candidate-123"
    assert "sourceId" not in candidate_summary
