from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.dataset_contract import (
    DatasetContract,
    DatasetContractDataset,
    DatasetContractDatasetKind,
)
from app.db.models.preview import (
    PreviewAuditEvent,
    PreviewCandidate,
    PreviewReviewDecision,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.features.review_llm import parse_review_llm_adapter_output
from app.services.operator_workflow import get_operator_workflow_snapshot
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionRequest,
    persist_review_decision,
    submit_preview_request,
)
from app.services.sql_generation_adapter import SQLGenerationAdapterResponse


class _PreviewAdapter:
    def __init__(self, review_decision=None):
        self.review_decision = review_decision

    def generate_sql(self, request):
        return SQLGenerationAdapterResponse(
            candidate_sql=(
                "SELECT vendor_id FROM finance.approved_vendor_spend LIMIT 50"
            ),
            provider="local_llm",
            adapter_version="test.adapter.v1",
            model="safequery-test-sql",
            review_decision=self.review_decision,
        )


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_source(session: Session) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id="sap-approved-spend",
        display_label="SAP spend cube / approved_vendor_spend",
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=SourceActivationPosture.ACTIVE,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference="vault:sap-approved-spend",
    )
    session.add(source)
    session.flush()

    snapshot = SchemaSnapshot(
        id=uuid4(),
        registered_source_id=source.id,
        snapshot_version=1,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=1,
        semantic_contract_version="approved_vendor_spend.v1",
        display_name="SAP spend cube contract",
        owner_binding="group:finance-analysts",
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()
    session.add(
        DatasetContractDataset(
            id=uuid4(),
            dataset_contract_id=contract.id,
            schema_name="finance",
            dataset_name="approved_vendor_spend",
            dataset_kind=DatasetContractDatasetKind.TABLE,
        )
    )

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()


def _review_payload() -> dict[str, object]:
    return {
        "contract_version": "review_llm_adapter_output.v1",
        "status": "needs_clarification",
        "confidence": "medium",
        "intent_summary": "compare approved vendor spend by vendor",
        "data_used": ["approved vendor spend"],
        "metrics": ["net spend"],
        "dimensions": ["vendor"],
        "filters": ["current quarter"],
        "assumptions": ["Vendor means normalized vendor_id."],
        "risk_flags": ["Vendor names may be sensitive."],
        "clarifying_questions": ["Should inactive vendors be included?"],
        "diagnostics": {
            "adapter_version": "review-adapter.v1",
            "model": "safequery-review-test",
            "provider": "local",
            "prompt_version": "review-prompt.v1",
            "response_id": "review-response-457",
            "raw_output_excerpt": "Should inactive vendors be included?",
        },
    }


def test_review_decision_is_persisted_with_schema_version_and_operator_evidence() -> None:
    session = _session()
    try:
        _seed_source(session)
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )
        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Compare approved vendor spend by vendor this quarter.",
                source_id="sap-approved-spend",
            ),
            authenticated_subject=subject,
            session=session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                request_id="preview-request-457",
                correlation_id="preview-request-457-correlation",
                user_subject="user:alice",
                session_id="preview-request-457-session",
                query_candidate_id="preview-candidate-457",
                candidate_owner_subject="user:alice",
                auth_source="test-helper",
            ),
            sql_generation_adapter=_PreviewAdapter(),
        )
        audit_event = session.scalar(
            select(PreviewAuditEvent).where(
                PreviewAuditEvent.candidate_id == response.candidate.candidate_id,
                PreviewAuditEvent.event_type == "guard_evaluated",
            )
        )
        assert audit_event is not None

        review = parse_review_llm_adapter_output(_review_payload())
        persist_review_decision(
            session,
            candidate_id=response.candidate.candidate_id,
            review=review,
            audit_event_id=audit_event.event_id,
            occurred_at=datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc),
        )

        persisted_review = session.scalar(select(PreviewReviewDecision))
        assert persisted_review is not None
        assert persisted_review.review_decision_id == (
            "review-preview-candidate-457"
        )
        assert persisted_review.request_id == response.request.request_id
        assert persisted_review.candidate_id == response.candidate.candidate_id
        assert persisted_review.audit_event_id == audit_event.event_id
        assert persisted_review.review_contract_version == (
            "review_llm_adapter_output.v1"
        )
        assert persisted_review.review_status == "needs_clarification"
        assert persisted_review.assumptions == ["Vendor means normalized vendor_id."]
        assert persisted_review.risk_flags == ["Vendor names may be sensitive."]
        assert persisted_review.clarifying_questions == [
            "Should inactive vendors be included?"
        ]
        assert (
            persisted_review.review_payload["diagnostics"]["rawOutputExcerpt"]
            == "Should inactive vendors be included?"
        )

        candidate_history = next(
            item
            for item in get_operator_workflow_snapshot(session).history
            if item.item_type == "candidate"
            and item.record_id == response.candidate.candidate_id
        )
        assert len(candidate_history.review_evidence) == 1
        assert candidate_history.review_evidence[0].model_dump(
            mode="json", by_alias=True
        ) == {
            "reviewDecisionId": "review-preview-candidate-457",
            "reviewStatus": "needs_clarification",
            "reviewContractVersion": "review_llm_adapter_output.v1",
            "auditEventId": str(audit_event.event_id),
            "assumptions": ["Vendor means normalized vendor_id."],
            "riskFlags": ["Vendor names may be sensitive."],
            "clarifyingQuestions": ["Should inactive vendors be included?"],
        }
    finally:
        session.close()


def test_operator_review_evidence_sanitizes_llm_text_before_payload_exposure() -> None:
    session = _session()
    try:
        _seed_source(session)
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )
        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Compare approved vendor spend by vendor this quarter.",
                source_id="sap-approved-spend",
            ),
            authenticated_subject=subject,
            session=session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                request_id="preview-request-457",
                correlation_id="preview-request-457-correlation",
                user_subject="user:alice",
                session_id="preview-request-457-session",
                query_candidate_id="preview-candidate-457",
                candidate_owner_subject="user:alice",
                auth_source="test-helper",
            ),
            sql_generation_adapter=_PreviewAdapter(),
        )
        audit_event = session.scalar(
            select(PreviewAuditEvent).where(
                PreviewAuditEvent.candidate_id == response.candidate.candidate_id,
                PreviewAuditEvent.event_type == "guard_evaluated",
            )
        )
        assert audit_event is not None

        unsafe_path = "/" + "/".join(["Users", "example", "review-secret.txt"])
        payload = _review_payload()
        payload["assumptions"] = ["Credential token=raw-review-token; continue."]
        payload["risk_flags"] = [f"Review diagnostics referenced {unsafe_path}."]
        payload["clarifying_questions"] = [
            "Retry with Bearer opaque-review-token; then ask?"
        ]
        review = parse_review_llm_adapter_output(payload)

        persist_review_decision(
            session,
            candidate_id=response.candidate.candidate_id,
            review=review,
            audit_event_id=audit_event.event_id,
            occurred_at=datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc),
        )

        persisted_review = session.scalar(select(PreviewReviewDecision))
        assert persisted_review is not None
        assert persisted_review.assumptions == [
            "Credential token=raw-review-token; continue."
        ]
        assert persisted_review.risk_flags == [
            f"Review diagnostics referenced {unsafe_path}."
        ]
        assert persisted_review.clarifying_questions == [
            "Retry with Bearer opaque-review-token; then ask?"
        ]

        candidate_history = next(
            item
            for item in get_operator_workflow_snapshot(session).history
            if item.item_type == "candidate"
            and item.record_id == response.candidate.candidate_id
        )
        operator_payload = candidate_history.review_evidence[0].model_dump(
            mode="json", by_alias=True
        )
        serialized = json.dumps(operator_payload, sort_keys=True)

        assert operator_payload["assumptions"] == [
            "[redacted] [redacted]; continue."
        ]
        assert operator_payload["riskFlags"] == [
            "Review diagnostics referenced [redacted]"
        ]
        assert operator_payload["clarifyingQuestions"] == [
            "Retry with [redacted]; then ask?"
        ]
        assert "raw-review-token" not in serialized
        assert "opaque-review-token" not in serialized
        assert unsafe_path not in serialized
    finally:
        session.close()


def test_review_decision_id_stays_within_column_length_for_long_candidate_id() -> None:
    session = _session()
    try:
        _seed_source(session)
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )
        long_candidate_id = "candidate-" + ("x" * 245)
        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Compare approved vendor spend by vendor this quarter.",
                source_id="sap-approved-spend",
            ),
            authenticated_subject=subject,
            session=session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                request_id="preview-request-457",
                correlation_id="preview-request-457-correlation",
                user_subject="user:alice",
                session_id="preview-request-457-session",
                query_candidate_id=long_candidate_id,
                candidate_owner_subject="user:alice",
                auth_source="test-helper",
            ),
            sql_generation_adapter=_PreviewAdapter(),
        )
        audit_event = session.scalar(
            select(PreviewAuditEvent).where(
                PreviewAuditEvent.candidate_id == response.candidate.candidate_id,
                PreviewAuditEvent.event_type == "guard_evaluated",
            )
        )
        assert audit_event is not None

        review = parse_review_llm_adapter_output(_review_payload())
        review_decision_id = persist_review_decision(
            session,
            candidate_id=response.candidate.candidate_id,
            review=review,
            audit_event_id=audit_event.event_id,
            occurred_at=datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc),
        )

        persisted_review = session.scalar(select(PreviewReviewDecision))
        assert persisted_review is not None
        assert response.candidate.candidate_id == long_candidate_id
        assert len(f"review-{long_candidate_id}") > 255
        assert review_decision_id == persisted_review.review_decision_id
        assert review_decision_id == f"review-{persisted_review.preview_candidate_id}"
        assert len(review_decision_id) <= 255
    finally:
        session.close()


def test_preview_submission_persists_adapter_review_decision() -> None:
    session = _session()
    try:
        _seed_source(session)
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )
        review = parse_review_llm_adapter_output(_review_payload())

        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Compare approved vendor spend by vendor this quarter.",
                source_id="sap-approved-spend",
            ),
            authenticated_subject=subject,
            session=session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                request_id="preview-request-457",
                correlation_id="preview-request-457-correlation",
                user_subject="user:alice",
                session_id="preview-request-457-session",
                query_candidate_id="preview-candidate-457",
                candidate_owner_subject="user:alice",
                auth_source="test-helper",
            ),
            sql_generation_adapter=_PreviewAdapter(review_decision=review),
        )

        persisted_review = session.scalar(select(PreviewReviewDecision))
        guard_event = session.scalar(
            select(PreviewAuditEvent).where(
                PreviewAuditEvent.candidate_id == response.candidate.candidate_id,
                PreviewAuditEvent.event_type == "guard_evaluated",
            )
        )
        assert persisted_review is not None
        assert guard_event is not None
        assert persisted_review.candidate_id == response.candidate.candidate_id
        assert persisted_review.audit_event_id == guard_event.event_id
        assert persisted_review.review_status == "needs_clarification"

        candidate_history = next(
            item
            for item in get_operator_workflow_snapshot(session).history
            if item.item_type == "candidate"
            and item.record_id == response.candidate.candidate_id
        )
        assert [item.review_status for item in candidate_history.review_evidence] == [
            "needs_clarification"
        ]
    finally:
        session.close()


def test_review_decision_rejects_unbound_audit_anchor_without_partial_write() -> None:
    session = _session()
    try:
        _seed_source(session)
        subject = AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )
        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Compare approved vendor spend by vendor this quarter.",
                source_id="sap-approved-spend",
            ),
            authenticated_subject=subject,
            session=session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                request_id="preview-request-457",
                correlation_id="preview-request-457-correlation",
                user_subject="user:alice",
                session_id="preview-request-457-session",
                query_candidate_id="preview-candidate-457",
                candidate_owner_subject="user:alice",
                auth_source="test-helper",
            ),
            sql_generation_adapter=_PreviewAdapter(),
        )
        preview_candidate = session.scalar(
            select(PreviewCandidate).where(
                PreviewCandidate.candidate_id == response.candidate.candidate_id
            )
        )
        assert preview_candidate is not None
        unbound_event = PreviewAuditEvent(
            event_id=uuid4(),
            lifecycle_order=99,
            preview_request_id=preview_candidate.preview_request_id,
            preview_candidate_id=None,
            request_id=response.request.request_id,
            candidate_id=response.candidate.candidate_id,
            event_type="guard_evaluated",
            occurred_at=datetime(2026, 1, 2, 3, 4, 59, tzinfo=timezone.utc),
            correlation_id="preview-request-457-correlation",
            authenticated_subject_id="user:alice",
            session_id="preview-request-457-session",
            source_id=response.request.source_id,
            source_family=response.candidate.source_family,
            source_flavor=response.candidate.source_flavor,
            dataset_contract_version=response.candidate.dataset_contract_version,
            semantic_contract_version=response.candidate.semantic_contract_version,
            schema_snapshot_version=response.candidate.schema_snapshot_version,
            candidate_state="preview_ready",
            audit_payload={"event_type": "guard_evaluated"},
        )
        session.add(unbound_event)
        session.commit()

        with pytest.raises(
            PreviewSubmissionContractError,
            match="audit anchor must stay bound to the preview candidate",
        ):
            persist_review_decision(
                session,
                candidate_id=response.candidate.candidate_id,
                review=parse_review_llm_adapter_output(_review_payload()),
                audit_event_id=unbound_event.event_id,
                occurred_at=datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc),
            )

        assert session.scalars(select(PreviewReviewDecision)).all() == []
    finally:
        session.close()
