from __future__ import annotations

import importlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import (
    PreviewAuditEvent,
    PreviewCandidate,
    PreviewCandidateApproval,
    PreviewReviewDecision,
    PreviewRequest,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.db.session import require_preview_submission_session
from app.features.auth.dev import build_dev_authenticated_subject
from app.features.auth.session import create_test_application_session
from app.features.result_validation import ResultValidationContract
from app.services.candidate_lifecycle import (
    CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY,
)


class _BlankRequestId:
    def __str__(self) -> str:
        return " "


class CandidateExecuteApiTestCase(unittest.TestCase):
    """Lower-level execute revalidation tests seed approved candidates directly."""

    def setUp(self) -> None:
        self._previous_env = {
            name: os.environ.get(name)
            for name in (
                "SAFEQUERY_APP_POSTGRES_URL",
                "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
                "SAFEQUERY_ENVIRONMENT",
                "SAFEQUERY_DEV_AUTH_ENABLED",
                "SAFEQUERY_SESSION_SIGNING_KEY",
            )
        }
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@app-postgres:5432/safequery"
        )
        os.environ["SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL"] = (
            "postgresql://safequery_exec:secret@business-postgres-source:5432/business"
        )
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"
        os.environ.pop("SAFEQUERY_SESSION_SIGNING_KEY", None)
        get_settings.cache_clear()

        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self._seed_approved_candidate()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        for name, value in self._previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()

    def _client(
        self,
        query_runner,
        *,
        result_validation_contract: ResultValidationContract | None = None,
        result_validation_contracts: dict[str, ResultValidationContract] | None = None,
    ) -> TestClient:
        main_module = importlib.import_module("app.main")
        app = main_module.create_app()
        app.dependency_overrides[require_preview_submission_session] = (
            lambda: self.session
        )
        app.state.execution_query_runner = query_runner
        if result_validation_contract is not None:
            app.state.result_validation_contract = result_validation_contract
        if result_validation_contracts is not None:
            app.state.result_validation_contracts = result_validation_contracts
        return TestClient(app)

    def _seed_approved_candidate(self) -> None:
        source = RegisteredSource(
            id=uuid4(),
            source_id="demo-business-postgres",
            display_label="Demo business PostgreSQL",
            source_family="postgresql",
            source_flavor="warehouse",
            activation_posture=SourceActivationPosture.ACTIVE,
            connector_profile_id=None,
            dialect_profile_id=None,
            dataset_contract_id=None,
            schema_snapshot_id=None,
            execution_policy_id=None,
            connection_reference="env:SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        )
        self.session.add(source)
        self.session.flush()

        snapshot = SchemaSnapshot(
            id=uuid4(),
            registered_source_id=source.id,
            snapshot_version=7,
            review_status=SchemaSnapshotReviewStatus.APPROVED,
            reviewed_at=datetime.now(timezone.utc),
        )
        self.session.add(snapshot)
        self.session.flush()

        contract = DatasetContract(
            id=uuid4(),
            registered_source_id=source.id,
            schema_snapshot_id=snapshot.id,
            contract_version=3,
            semantic_contract_version="approved_vendor_spend.v1",
            display_name="Demo business contract",
            owner_binding="group:safequery-demo-local-operators",
            security_review_binding=None,
            exception_policy_binding=None,
        )
        self.session.add(contract)
        self.session.flush()

        source.dataset_contract_id = contract.id
        source.schema_snapshot_id = snapshot.id

        request = PreviewRequest(
            id=uuid4(),
            request_id="request-123",
            registered_source_id=source.id,
            source_id=source.source_id,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
            dataset_contract_id=contract.id,
            dataset_contract_version=contract.contract_version,
            semantic_contract_version=contract.semantic_contract_version,
            schema_snapshot_id=snapshot.id,
            schema_snapshot_version=snapshot.snapshot_version,
            authenticated_subject_id="user:demo-local-operator",
            auth_source="test-helper",
            session_id="session-123",
            governance_bindings="group:safequery-demo-local-operators",
            entitlement_decision="allow",
            request_text="Show approved spend",
            request_state="previewed",
        )
        self.session.add(request)
        self.session.flush()

        candidate = PreviewCandidate(
            id=uuid4(),
            candidate_id="candidate-123",
            preview_request_id=request.id,
            request_id=request.request_id,
            registered_source_id=source.id,
            source_id=source.source_id,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
            dataset_contract_id=contract.id,
            dataset_contract_version=contract.contract_version,
            semantic_contract_version=contract.semantic_contract_version,
            schema_snapshot_id=snapshot.id,
            schema_snapshot_version=snapshot.snapshot_version,
            authenticated_subject_id="user:demo-local-operator",
            candidate_sql="SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1",
            guard_status="allow",
            candidate_state="preview_ready",
        )
        self.session.add(candidate)
        self.session.flush()

        now = datetime.now(timezone.utc)
        self.session.add(
            PreviewCandidateApproval(
                id=uuid4(),
                approval_id="approval-candidate-123",
                preview_candidate_id=candidate.id,
                candidate_id=candidate.candidate_id,
                request_id=request.request_id,
                registered_source_id=source.id,
                source_id=source.source_id,
                source_family=source.source_family,
                source_flavor=source.source_flavor,
                dataset_contract_version=contract.contract_version,
                schema_snapshot_version=snapshot.snapshot_version,
                execution_policy_version=CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY[
                    source.source_family
                ],
                approved_sql=(
                    "SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"
                ),
                owner_subject_id="user:demo-local-operator",
                session_id="session-123",
                approved_at=now - timedelta(minutes=1),
                approval_expires_at=now + timedelta(minutes=10),
                approval_state="approved",
            )
        )
        self.session.commit()

    def _seed_review_decision(
        self,
        review_status: str,
        *,
        assumptions: list[str] | None = None,
    ) -> None:
        candidate = (
            self.session.query(PreviewCandidate)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        audit_event = PreviewAuditEvent(
            id=uuid4(),
            event_id=uuid4(),
            lifecycle_order=1,
            preview_request_id=candidate.preview_request_id,
            preview_candidate_id=candidate.id,
            request_id=candidate.request_id,
            candidate_id=candidate.candidate_id,
            event_type="guard_evaluated",
            occurred_at=datetime.now(timezone.utc),
            correlation_id="review-correlation-123",
            causation_event_id=None,
            authenticated_subject_id=candidate.authenticated_subject_id,
            session_id="session-123",
            auth_source="test-helper",
            governance_bindings="group:safequery-demo-local-operators",
            entitlement_decision="allow",
            entitlement_source_bindings="demo-business-postgres",
            adapter_provider="test",
            adapter_model="safequery-test-review",
            adapter_version="test.review.v1",
            adapter_run_id=None,
            prompt_version="test-review-prompt.v1",
            prompt_fingerprint=None,
            application_version="safequery-api/test",
            source_id=candidate.source_id,
            source_family=candidate.source_family,
            source_flavor=candidate.source_flavor,
            dataset_contract_version=candidate.dataset_contract_version,
            schema_snapshot_version=candidate.schema_snapshot_version,
            primary_deny_code=None,
            denial_cause=None,
            candidate_state=candidate.candidate_state,
            audit_payload={"event_type": "guard_evaluated"},
        )
        self.session.add(audit_event)
        self.session.flush()
        self.session.add(
            PreviewReviewDecision(
                id=uuid4(),
                review_decision_id=f"review-candidate-123-{review_status}",
                preview_candidate_id=candidate.id,
                candidate_id=candidate.candidate_id,
                request_id=candidate.request_id,
                audit_event_id=audit_event.event_id,
                registered_source_id=candidate.registered_source_id,
                source_id=candidate.source_id,
                source_family=candidate.source_family,
                source_flavor=candidate.source_flavor,
                dataset_contract_version=candidate.dataset_contract_version,
                semantic_contract_version=candidate.semantic_contract_version,
                schema_snapshot_version=candidate.schema_snapshot_version,
                review_contract_version="review_llm_adapter_output.v1",
                review_status=review_status,
                review_confidence="high",
                assumptions=list(assumptions or []),
                risk_flags=[],
                clarifying_questions=[],
                review_payload={"status": review_status},
                occurred_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

    def test_execute_candidate_api_runs_only_approved_candidate_identifier(self) -> None:
        calls: list[str] = []

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            calls.append(canonical_sql)
            return [{"vendor_name": "Acme"}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(query_runner).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["candidate_id"], "candidate-123")
        self.assertEqual(payload["source_id"], "demo-business-postgres")
        self.assertEqual(payload["connector_id"], "postgresql_readonly")
        self.assertEqual(payload["rows"], [{"vendor_name": "Acme"}])
        self.assertEqual(
            {
                "source_id": payload["metadata"]["source_id"],
                "source_family": payload["metadata"]["source_family"],
                "source_flavor": payload["metadata"]["source_flavor"],
                "candidate_id": payload["metadata"]["candidate_id"],
                "row_count": payload["metadata"]["row_count"],
                "row_limit": payload["metadata"]["row_limit"],
                "result_truncated": payload["metadata"]["result_truncated"],
            },
            {
                "source_id": "demo-business-postgres",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
                "candidate_id": "candidate-123",
                "row_count": 1,
                "row_limit": 200,
                "result_truncated": False,
            },
        )
        self.assertIn("execution_run_id", payload["metadata"])
        self.assertLessEqual(
            payload["metadata"]["payload_bytes"],
            payload["metadata"]["payload_limit_bytes"],
        )
        self.assertEqual(
            payload["audit"]["events"][-1]["execution_row_count"],
            payload["metadata"]["row_count"],
        )
        self.assertEqual(
            payload["audit"]["events"][-1]["result_truncated"],
            payload["metadata"]["result_truncated"],
        )
        self.assertEqual(
            calls,
            ["SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"],
        )

    def test_execute_candidate_api_attaches_result_validation_metadata(self) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [{"vendor_name": "Acme", "approved_spend": 1200}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        validation = response.json()["metadata"]["result_validation"]

        self.assertEqual(validation["status"], "pass")
        self.assertEqual(
            validation["semantic_contract_version"],
            "approved_vendor_spend.v1",
        )
        self.assertEqual(validation["candidate_id"], "candidate-123")
        self.assertEqual(
            validation["execution_run_id"],
            response.json()["metadata"]["execution_run_id"],
        )
        self.assertEqual(
            validation["evidence"]["expected_columns"],
            ["vendor_name", "approved_spend"],
        )
        self.assertEqual(validation["evidence"]["row_count"], 1)
        answer_summary = response.json()["metadata"]["answer_summary"]
        self.assertEqual(answer_summary["contract_version"], "mvp_answer_summary.v1")
        self.assertEqual(answer_summary["validation_status"], "pass")
        self.assertEqual(answer_summary["truncation_status"], "not_truncated")
        self.assertEqual(answer_summary["redaction_status"], "not_required")
        self.assertEqual(answer_summary["rows_used"], 1)
        self.assertIn(
            "Approved vendor spend rows from 1 returned row: "
            "1. Acme (unspecified period) - 1200.",
            answer_summary["answer_text"],
        )
        persisted_events = (
            self.session.query(PreviewAuditEvent)
            .order_by(PreviewAuditEvent.lifecycle_order)
            .all()
        )
        answer_evidence = persisted_events[-1].audit_payload["answer_evidence"]
        self.assertEqual(answer_evidence["answer_state"], "answered")
        self.assertEqual(answer_evidence["validation_status"], "pass")
        self.assertEqual(answer_evidence["redaction_status"], "not_required")
        self.assertEqual(answer_evidence["summary_strategy"], "mvp_answer_summary.v1")
        self.assertEqual(answer_evidence["bounded_metadata"]["row_count"], 1)
        self.assertEqual(answer_evidence["bounded_metadata"]["rows_used"], 1)
        self.assertNotIn("rows", answer_evidence)
        self.assertNotIn("Acme", str(answer_evidence))

    def test_execute_candidate_api_attaches_review_assumptions_to_answer_summary(
        self,
    ) -> None:
        self._seed_review_decision(
            "ready",
            assumptions=["Rows are sorted by approved spend descending."],
        )

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [{"vendor_name": "Acme", "approved_spend": 1200}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        answer_summary = response.json()["metadata"]["answer_summary"]
        self.assertEqual(
            answer_summary["assumptions"],
            ["Rows are sorted by approved spend descending."],
        )
        self.assertIn(
            "Assumptions: Rows are sorted by approved spend descending.",
            answer_summary["answer_text"],
        )

    def test_execute_candidate_api_bounds_review_assumptions_in_answer_summary(
        self,
    ) -> None:
        long_assumption = "Rows are sorted by " + ("approved spend " * 40)
        self._seed_review_decision("ready", assumptions=[long_assumption])

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [{"vendor_name": "Acme", "approved_spend": 1200}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        answer_summary = response.json()["metadata"]["answer_summary"]
        self.assertNotIn(long_assumption, answer_summary["answer_text"])
        displayed_assumption = answer_summary["assumptions"][0]
        self.assertTrue(displayed_assumption.endswith("... [truncated]"))
        self.assertEqual(len(displayed_assumption), 160)
        self.assertIn(
            f"Assumptions: {displayed_assumption}.",
            answer_summary["answer_text"],
        )

    def test_execute_candidate_api_redacts_sensitive_columns_before_result_rows(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [
                {
                    "vendor_name": "Acme",
                    "vendor_email": "buyer@example.test",
                    "approved_spend": 1200,
                }
            ]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
                redaction_required=True,
                column_sensitivity={
                    "vendor_name": "public",
                    "vendor_email": "sensitive",
                    "approved_spend": "public",
                },
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["rows"],
            [{"vendor_name": "Acme", "approved_spend": 1200}],
        )
        self.assertNotIn("buyer@example.test", response.text)
        validation = payload["metadata"]["result_validation"]
        self.assertEqual(validation["status"], "pass")
        self.assertEqual(validation["evidence"]["redaction_status"], "applied")
        self.assertEqual(validation["evidence"]["redacted_columns"], ["vendor_email"])
        self.assertEqual(validation["evidence"]["unclassified_columns"], [])

    def test_execute_candidate_api_applies_payload_limit_after_redaction(
        self,
    ) -> None:
        sensitive_note = "private-note-" + ("x" * 70_000)

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [
                {
                    "vendor_name": "Acme",
                    "analyst_note": sensitive_note,
                },
                {
                    "vendor_name": "Beta",
                    "analyst_note": sensitive_note,
                },
            ]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name",),
                required_columns=("vendor_name",),
                redaction_required=True,
                column_sensitivity={
                    "vendor_name": "public",
                    "analyst_note": "sensitive",
                },
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["rows"],
            [{"vendor_name": "Acme"}, {"vendor_name": "Beta"}],
        )
        self.assertEqual(payload["metadata"]["row_count"], 2)
        self.assertLess(payload["metadata"]["payload_bytes"], 64 * 1024)
        self.assertIs(payload["metadata"]["result_truncated"], False)
        self.assertNotIn("truncation_reason", payload["metadata"])
        self.assertNotIn("private-note-", response.text)

    def test_execute_candidate_api_summary_preserves_payload_truncation_reason(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [
                {
                    "vendor_name": f"Vendor {index} " + ("x" * 4096),
                    "approved_spend": index,
                }
                for index in range(200)
            ]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIs(payload["metadata"]["result_truncated"], True)
        self.assertEqual(payload["metadata"]["truncation_reason"], "payload_limit")
        answer_summary = payload["metadata"]["answer_summary"]
        self.assertEqual(answer_summary["answer_state"], "insufficient_evidence")
        self.assertEqual(
            answer_summary["insufficient_evidence_reason"],
            "unsafe_truncation",
        )
        self.assertEqual(
            answer_summary["next_action"],
            "rerun_with_trusted_top_n_or_higher_limit",
        )
        self.assertIn(
            "result was truncated before the top set could be trusted",
            answer_summary["answer_text"],
        )

    def test_execute_candidate_api_validates_returned_rows_after_redaction_and_capping(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            rows: list[dict[str, object]] = [
                {
                    "vendor_name": f"Vendor {index}",
                    "approved_spend": index,
                    "analyst_note": f"private-note-{index}",
                }
                for index in range(200)
            ]
            rows.append(
                {
                    "vendor_name": "Vendor 0",
                    "approved_spend": 999,
                    "analyst_note": "excluded-private-note",
                }
            )
            return rows

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
                aggregate_columns=("approved_spend",),
                redaction_required=True,
                column_sensitivity={
                    "vendor_name": "public",
                    "approved_spend": "public",
                    "analyst_note": "sensitive",
                },
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["metadata"]["row_count"], 200)
        self.assertIs(payload["metadata"]["result_truncated"], True)
        self.assertEqual(payload["metadata"]["truncation_reason"], "row_limit")
        self.assertNotIn("private-note-", response.text)
        self.assertNotIn("excluded-private-note", response.text)
        validation = payload["metadata"]["result_validation"]
        self.assertEqual(validation["status"], "warn")
        self.assertEqual(validation["reason_codes"], ["result_truncated"])
        self.assertEqual(validation["evidence"]["aggregation_shape"], "valid")
        self.assertEqual(validation["evidence"]["redaction_status"], "applied")
        self.assertEqual(validation["evidence"]["redacted_columns"], ["analyst_note"])

    def test_execute_candidate_api_fails_closed_when_redaction_metadata_is_missing(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [
                {
                    "vendor_name": "Acme",
                    "vendor_email": "buyer@example.test",
                    "approved_spend": 1200,
                }
            ]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("vendor_name", "approved_spend"),
                redaction_required=True,
                column_sensitivity={
                    "vendor_name": "public",
                    "approved_spend": "public",
                },
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertNotIn("buyer@example.test", response.text)
        self.assertEqual(
            payload["audit"]["events"][-1]["primary_deny_code"],
            "DENY_RESULT_VALIDATION_FAILED",
        )
        self.assertEqual(
            payload["audit"]["events"][-1]["denial_reason"],
            "column_sensitivity_metadata_missing",
        )

    def test_execute_candidate_api_returns_insufficient_evidence_when_required_column_is_redacted(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [
                {
                    "vendor_name": "Acme",
                    "vendor_email": "buyer@example.test",
                    "approved_spend": 1200,
                }
            ]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "vendor_email", "approved_spend"),
                required_columns=("vendor_name", "vendor_email", "approved_spend"),
                redaction_required=True,
                column_sensitivity={
                    "vendor_name": "public",
                    "vendor_email": "sensitive",
                    "approved_spend": "public",
                },
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn("buyer@example.test", response.text)
        answer_summary = payload["metadata"]["answer_summary"]
        self.assertEqual(
            answer_summary["answer_state"],
            "insufficient_evidence",
        )
        self.assertEqual(
            answer_summary["insufficient_evidence_reason"],
            "missing_columns",
        )
        self.assertEqual(
            answer_summary["next_action"],
            "revise_query_or_semantic_contract_columns",
        )
        self.assertEqual(
            payload["metadata"]["result_validation"]["reason_codes"],
            ["missing_expected_columns", "missing_required_columns"],
        )
        self.assertEqual(payload["audit"]["events"][-1]["execution_row_count"], 1)
        self.assertIs(payload["audit"]["events"][-1]["result_truncated"], False)

    def test_execute_candidate_api_selects_validation_contract_by_semantic_version(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [{"vendor_name": "Acme"}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contracts={
                "other_contract.v1": ResultValidationContract(
                    semantic_contract_version="other_contract.v1",
                    expected_columns=("missing_column",),
                    required_columns=("missing_column",),
                ),
                "approved_vendor_spend.v1": ResultValidationContract(
                    semantic_contract_version="approved_vendor_spend.v1",
                    expected_columns=("vendor_name",),
                    required_columns=("vendor_name",),
                ),
            },
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        validation = response.json()["metadata"]["result_validation"]
        self.assertEqual(validation["status"], "pass")
        self.assertEqual(
            validation["semantic_contract_version"],
            "approved_vendor_spend.v1",
        )
        self.assertEqual(validation["evidence"]["expected_columns"], ["vendor_name"])

    def test_execute_candidate_api_rejects_missing_semantic_version_before_runner(
        self,
    ) -> None:
        calls: list[str] = []
        candidate = (
            self.session.query(PreviewCandidate)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        candidate.semantic_contract_version = None
        self.session.commit()

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            lambda **_: calls.append("called"),
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name",),
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_POLICY_VERSION_STALE",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_returns_insufficient_evidence_for_missing_columns(
        self,
    ) -> None:
        calls: list[str] = []

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            calls.append(canonical_sql)
            return [{"vendor_name": "Acme"}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        client = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name", "approved_spend"),
                required_columns=("approved_spend",),
            ),
        )
        response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [event["event_type"] for event in payload["audit"]["events"]],
            ["execution_requested", "execution_started", "execution_completed"],
        )
        validation = payload["metadata"]["result_validation"]
        self.assertEqual(validation["status"], "fail")
        self.assertEqual(
            validation["reason_codes"],
            ["missing_expected_columns", "missing_required_columns"],
        )
        answer_summary = payload["metadata"]["answer_summary"]
        self.assertEqual(answer_summary["answer_state"], "insufficient_evidence")
        self.assertEqual(
            answer_summary["insufficient_evidence_reason"],
            "missing_columns",
        )
        self.assertEqual(
            answer_summary["next_action"],
            "revise_query_or_semantic_contract_columns",
        )
        self.assertNotIn("Acme", answer_summary["answer_text"])
        self.assertEqual(payload["audit"]["events"][-1]["execution_row_count"], 1)
        self.assertIs(payload["audit"]["events"][-1]["result_truncated"], False)
        self.assertEqual(
            calls,
            ["SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"],
        )
        persisted_events = (
            self.session.query(PreviewAuditEvent)
            .order_by(PreviewAuditEvent.lifecycle_order)
            .all()
        )
        self.assertEqual(
            [event.event_type for event in persisted_events],
            ["execution_requested", "execution_started", "execution_completed"],
        )
        self.assertEqual(
            persisted_events[-1].audit_payload["execution_row_count"],
            1,
        )
        self.assertIs(
            persisted_events[-1].audit_payload["result_truncated"],
            False,
        )
        self.assertEqual(
            persisted_events[-1].audit_payload["answer_state"],
            "insufficient_evidence",
        )
        self.assertEqual(
            persisted_events[-1].audit_payload["insufficient_evidence_reason"],
            "missing_columns",
        )
        self.assertEqual(
            persisted_events[-1].audit_payload["next_action"],
            "revise_query_or_semantic_contract_columns",
        )
        self.assertIn(
            "expected result columns were missing",
            persisted_events[-1].audit_payload["answer_text"],
        )
        answer_evidence = persisted_events[-1].audit_payload["answer_evidence"]
        self.assertEqual(
            answer_evidence["answer_id"],
            str(persisted_events[-1].event_id),
        )
        self.assertEqual(answer_evidence["request_id"], "request-123")
        self.assertEqual(answer_evidence["candidate_id"], "candidate-123")
        self.assertEqual(
            answer_evidence["execution_run_id"],
            payload["metadata"]["execution_run_id"],
        )
        self.assertEqual(answer_evidence["validation_status"], "fail")
        self.assertEqual(answer_evidence["redaction_status"], "not_required")
        self.assertEqual(
            answer_evidence["summary_strategy"],
            "mvp_answer_summary.v1",
        )
        self.assertEqual(answer_evidence["answer_state"], "insufficient_evidence")
        self.assertEqual(
            answer_evidence["insufficient_evidence_reason"],
            "missing_columns",
        )
        self.assertEqual(
            answer_evidence["audit_event_id"],
            str(persisted_events[-1].event_id),
        )
        self.assertIn("result_hash", answer_evidence)
        self.assertEqual(
            answer_evidence["bounded_metadata"]["reason_codes"],
            ["missing_expected_columns", "missing_required_columns"],
        )
        self.assertNotIn("rows", answer_evidence)
        self.assertNotIn("Acme", str(answer_evidence))

        workflow_response = client.get(
            "/operator/workflow",
            headers=app_session.headers,
            cookies=app_session.cookies,
        )
        self.assertEqual(workflow_response.status_code, 200)
        workflow_payload = workflow_response.json()
        run_history = [
            item
            for item in workflow_payload["history"]
            if item["itemType"] == "run"
            and item["recordId"] == payload["metadata"]["execution_run_id"]
        ]
        self.assertEqual(len(run_history), 1)
        self.assertEqual(run_history[0]["runState"], "insufficient_evidence")
        self.assertEqual(
            run_history[0]["lifecycleState"],
            "insufficient_evidence",
        )
        self.assertEqual(
            run_history[0]["insufficientEvidence"],
            {
                "answerText": persisted_events[-1].audit_payload["answer_text"],
                "nextAction": "revise_query_or_semantic_contract_columns",
                "reason": "missing_columns",
            },
        )
        self.assertEqual(run_history[0]["rowCount"], 1)
        self.assertIs(run_history[0]["resultTruncated"], False)

    def test_execute_candidate_api_rejects_malformed_validation_contract_before_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())
        client = self._client(lambda **_: calls.append("called"))
        client.app.state.result_validation_contract = {
            "expected_columns": ["vendor_name"],
        }

        response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "execution_unavailable")
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_persists_source_aware_execution_audit_events(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [{"vendor_name": f"Vendor {index}"} for index in range(225)]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(
            query_runner,
            result_validation_contract=ResultValidationContract(
                semantic_contract_version="approved_vendor_spend.v1",
                expected_columns=("vendor_name",),
                required_columns=("vendor_name",),
            ),
        ).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        persisted_events = (
            self.session.query(PreviewAuditEvent)
            .order_by(PreviewAuditEvent.lifecycle_order)
            .all()
        )

        self.assertEqual(
            [event.event_type for event in persisted_events],
            [
                "execution_requested",
                "execution_started",
                "execution_completed",
            ],
        )
        self.assertEqual(
            [event.causation_event_id for event in persisted_events],
            [
                None,
                persisted_events[0].event_id,
                persisted_events[1].event_id,
            ],
        )
        self.assertEqual(
            str(persisted_events[-1].event_id),
            payload["metadata"]["execution_run_id"],
        )
        self.assertEqual(
            persisted_events[-1].audit_payload["execution_row_count"],
            200,
        )
        self.assertIs(
            persisted_events[-1].audit_payload["result_truncated"],
            True,
        )
        self.assertEqual(payload["metadata"]["row_count"], 200)
        self.assertIs(payload["metadata"]["result_truncated"], True)
        self.assertEqual(payload["metadata"]["truncation_reason"], "row_limit")
        for event in persisted_events:
            self.assertEqual(event.request_id, "request-123")
            self.assertEqual(event.candidate_id, "candidate-123")
            self.assertEqual(event.source_id, "demo-business-postgres")
            self.assertEqual(event.source_family, "postgresql")
            self.assertEqual(event.source_flavor, "warehouse")
            self.assertEqual(event.dataset_contract_version, 3)
            self.assertEqual(event.schema_snapshot_version, 7)
            self.assertEqual(event.audit_payload["execution_policy_version"], 3)
            self.assertNotIn("safequery_exec:secret", str(event.audit_payload))
            self.assertNotIn("business-postgres-source", str(event.audit_payload))

        answer_evidence = persisted_events[-1].audit_payload["answer_evidence"]
        self.assertEqual(answer_evidence["answer_state"], "insufficient_evidence")
        self.assertEqual(answer_evidence["validation_status"], "warn")
        self.assertEqual(answer_evidence["redaction_status"], "not_required")
        self.assertEqual(
            answer_evidence["insufficient_evidence_reason"],
            "unsafe_truncation",
        )
        self.assertEqual(answer_evidence["bounded_metadata"]["row_count"], 200)
        self.assertIs(answer_evidence["bounded_metadata"]["result_truncated"], True)
        self.assertEqual(
            answer_evidence["bounded_metadata"]["truncation_reason"],
            "row_limit",
        )
        self.assertNotIn("rows", answer_evidence)
        self.assertNotIn("Vendor 0", str(answer_evidence))

    def test_execute_candidate_missing_request_id_uses_controlled_fail_closed_error(
        self,
    ) -> None:
        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())
        main_module = importlib.import_module("app.main")

        with patch.object(main_module, "uuid4", return_value=_BlankRequestId()):
            response = self._client(lambda **_: calls.append("called")).post(
                "/candidates/candidate-123/execute",
                headers=app_session.headers,
                cookies=app_session.cookies,
                json={"selected_source_id": "demo-business-postgres"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "request_context_unavailable",
                    "message": "Request processing context is unavailable.",
                },
                "audit": {
                    "events": [
                        {
                            "event_type": "request_context_unavailable",
                            "operation": "execute",
                            "candidate_id": "candidate-123",
                            "denial_cause": "missing_request_audit_context",
                        }
                    ]
                },
            },
        )
        self.assertEqual(calls, [])
        self.assertNotIn("Request audit context is unavailable", response.text)
        self.assertNotIn("Traceback", response.text)
        self.assertEqual(self.session.query(PreviewAuditEvent).count(), 0)

    def test_execute_candidate_api_runs_approved_snapshot_after_preview_row_drift(
        self,
    ) -> None:
        calls: list[str] = []
        candidate = (
            self.session.query(PreviewCandidate)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        candidate.candidate_sql = "SELECT unapproved_column FROM drifted_preview"
        self.session.commit()

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            calls.append(canonical_sql)
            return [{"vendor_name": "Acme"}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(query_runner).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            calls,
            ["SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"],
        )

    def test_execute_candidate_api_uses_snapshot_returned_by_lifecycle_revalidation(
        self,
    ) -> None:
        calls: list[str] = []
        main_module = importlib.import_module("app.main")
        original_revalidate = main_module.revalidate_authoritative_candidate_approval

        def revalidate_after_approval_refresh(**kwargs: object) -> object:
            approval = (
                self.session.query(PreviewCandidateApproval)
                .filter_by(candidate_id="candidate-123")
                .one()
            )
            approval.approved_sql = (
                "SELECT vendor_name FROM finance.approved_vendor_spend "
                "WHERE vendor_name = 'Revalidated' LIMIT 1"
            )
            self.session.commit()
            return original_revalidate(**kwargs)

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            calls.append(canonical_sql)
            return [{"vendor_name": "Revalidated"}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        with patch.object(
            main_module,
            "revalidate_authoritative_candidate_approval",
            side_effect=revalidate_after_approval_refresh,
        ):
            response = self._client(query_runner).post(
                "/candidates/candidate-123/execute",
                headers=app_session.headers,
                cookies=app_session.cookies,
                json={"selected_source_id": "demo-business-postgres"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            calls,
            [
                "SELECT vendor_name FROM finance.approved_vendor_spend "
                "WHERE vendor_name = 'Revalidated' LIMIT 1"
            ],
        )

    def test_execute_candidate_api_rejects_missing_approved_snapshot_before_runner(
        self,
    ) -> None:
        calls: list[str] = []
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        approval.approved_sql = None
        self.session.commit()

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "execution_denied")
        self.assertEqual(calls, [])
        self.session.refresh(approval)
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_rejects_review_blocked_without_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        self._seed_review_decision("blocked")

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_REVIEW_BLOCKED",
        )
        self.assertEqual(
            payload["audit"]["events"][0]["denial_cause"],
            "review_blocked",
        )
        persisted_event = self.session.query(PreviewAuditEvent).filter_by(
            event_type="execution_denied"
        ).one()
        self.assertEqual(persisted_event.primary_deny_code, "DENY_REVIEW_BLOCKED")
        self.assertEqual(persisted_event.denial_cause, "review_blocked")
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_rejects_review_needs_clarification_without_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        self._seed_review_decision("needs_clarification")

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_REVIEW_NEEDS_CLARIFICATION",
        )
        self.assertEqual(
            payload["audit"]["events"][0]["denial_cause"],
            "review_needs_clarification",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_review_ready_does_not_override_guard_denied(
        self,
    ) -> None:
        calls: list[str] = []
        candidate = (
            self.session.query(PreviewCandidate)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        candidate.guard_status = "reject"
        self.session.commit()
        self._seed_review_decision("ready")

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_CANDIDATE_NOT_APPROVED",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_review_ready_does_not_override_missing_approval(
        self,
    ) -> None:
        calls: list[str] = []
        self._seed_review_decision("ready")
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.session.delete(approval)
        self.session.commit()

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_CANDIDATE_NOT_APPROVED",
        )
        self.assertEqual(calls, [])
        self.assertEqual(
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .count(),
            0,
        )

    def test_execute_candidate_api_rejects_missing_connector_config_without_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        os.environ.pop("SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL", None)
        get_settings.cache_clear()

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "execution_unavailable")
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_persists_runtime_failure_audit_events(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            raise RuntimeError(
                "driver failed for safequery_exec:secret@business-postgres-source"
            )

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(query_runner).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "execution_unavailable")
        persisted_events = (
            self.session.query(PreviewAuditEvent)
            .order_by(PreviewAuditEvent.lifecycle_order)
            .all()
        )
        self.assertEqual(
            [event.event_type for event in persisted_events],
            [
                "execution_requested",
                "execution_started",
                "execution_failed",
            ],
        )
        self.assertEqual(persisted_events[-1].candidate_state, "failed")
        self.assertEqual(
            [event.causation_event_id for event in persisted_events],
            [
                None,
                persisted_events[0].event_id,
                persisted_events[1].event_id,
            ],
        )
        serialized_events = str([event.audit_payload for event in persisted_events])
        self.assertNotIn("safequery_exec:secret", serialized_events)
        self.assertNotIn("business-postgres-source", serialized_events)
        self.assertNotIn("safequery_exec:secret", response.text)
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "executed")
        self.assertIsNotNone(approval.executed_at)

    def test_execute_candidate_api_rejects_raw_sql_before_runner_invocation(self) -> None:
        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "selected_source_id": "demo-business-postgres",
                "canonical_sql": "SELECT 1",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertEqual(calls, [])

    def test_execute_candidate_api_rejects_source_switch_without_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "another-business-source"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_SOURCE_BINDING_MISMATCH",
        )
        self.assertEqual(
            payload["audit"]["events"][0]["query_candidate_id"],
            "candidate-123",
        )
        persisted_event = self.session.query(PreviewAuditEvent).one()
        self.assertEqual(persisted_event.event_type, "execution_denied")
        self.assertEqual(persisted_event.request_id, "request-123")
        self.assertEqual(persisted_event.candidate_id, "candidate-123")
        self.assertEqual(persisted_event.source_id, "demo-business-postgres")
        self.assertEqual(
            persisted_event.primary_deny_code,
            "DENY_SOURCE_BINDING_MISMATCH",
        )
        self.assertEqual(
            persisted_event.audit_payload["denial_cause"],
            "source_binding_mismatch",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_rejects_blocked_source_posture_without_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        source = (
            self.session.query(RegisteredSource)
            .filter_by(source_id="demo-business-postgres")
            .one()
        )
        source.activation_posture = SourceActivationPosture.BLOCKED
        self.session.commit()

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(lambda **_: calls.append("called")).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_SOURCE_ACTIVATION_POSTURE",
        )
        persisted_event = self.session.query(PreviewAuditEvent).one()
        self.assertEqual(persisted_event.event_type, "execution_denied")
        self.assertEqual(
            persisted_event.primary_deny_code,
            "DENY_SOURCE_ACTIVATION_POSTURE",
        )
        self.assertEqual(
            persisted_event.audit_payload["denial_cause"],
            "source_activation_posture",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_rejects_application_postgres_connection_reference_without_leaking_secret(
        self,
    ) -> None:
        calls: list[str] = []
        source = (
            self.session.query(RegisteredSource)
            .filter_by(source_id="demo-business-postgres")
            .one()
        )
        source.connection_reference = "env:SAFEQUERY_APP_POSTGRES_URL"
        self.session.commit()

        def query_runner(**_: object) -> list[dict[str, object]]:
            calls.append("called")
            return []

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(query_runner).post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_SOURCE_BINDING_MISMATCH",
        )
        self.assertNotIn("safequery_exec:secret", response.text)
        self.assertNotIn(os.environ["SAFEQUERY_APP_POSTGRES_URL"], response.text)
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_rejects_unknown_connector_without_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        main_module = importlib.import_module("app.main")
        unexpected_selection = main_module.ExecutionConnectorSelection(
            source_id="demo-business-postgres",
            source_family="postgresql",
            source_flavor="warehouse",
            connector_id="postgresql_readonly_shadow",
            ownership="backend",
        )

        def query_runner(**_: object) -> list[dict[str, object]]:
            calls.append("called")
            return []

        app_session = create_test_application_session(build_dev_authenticated_subject())
        with patch.object(
            main_module,
            "select_execution_connector",
            return_value=unexpected_selection,
        ):
            response = self._client(query_runner).post(
                "/candidates/candidate-123/execute",
                headers=app_session.headers,
                cookies=app_session.cookies,
                json={"selected_source_id": "demo-business-postgres"},
            )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][0]["primary_deny_code"],
            "DENY_SOURCE_BINDING_MISMATCH",
        )
        self.assertEqual(
            payload["audit"]["events"][0]["query_candidate_id"],
            "candidate-123",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_applies_operator_runtime_kill_switch_without_consuming_approval(
        self,
    ) -> None:
        from app.features.execution.runtime import ExecutionRuntimeSafetyState

        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())

        def query_runner(**_: object) -> list[dict[str, object]]:
            calls.append("called")
            return []

        client = self._client(query_runner)
        client.app.state.execution_runtime_safety_state = ExecutionRuntimeSafetyState(
            disabled_source_ids=frozenset({"demo-business-postgres"})
        )

        response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_denied")
        self.assertEqual(
            payload["audit"]["events"][-1]["primary_deny_code"],
            "DENY_RUNTIME_KILL_SWITCH",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_applies_candidate_bound_operator_cancellation_without_consuming_approval(
        self,
    ) -> None:
        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())

        def query_runner(**_: object) -> list[dict[str, object]]:
            calls.append("called")
            return []

        client = self._client(query_runner)
        client.app.state.execution_cancelled_candidate_ids = frozenset({"candidate-123"})

        response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_unavailable")
        self.assertEqual(
            payload["audit"]["events"][-1]["candidate_state"],
            "canceled",
        )
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_rejects_malformed_operator_cancellation_state(
        self,
    ) -> None:
        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())

        client = self._client(lambda **_: calls.append("called"))
        client.app.state.execution_cancelled_candidate_ids = ["candidate-123", None]

        response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "execution_unavailable")
        self.assertEqual(calls, [])
        approval = (
            self.session.query(PreviewCandidateApproval)
            .filter_by(candidate_id="candidate-123")
            .one()
        )
        self.assertEqual(approval.approval_state, "approved")
        self.assertIsNone(approval.executed_at)

    def test_execute_candidate_api_cancellation_probe_reads_operator_state_updates(
        self,
    ) -> None:
        from app.features.execution.runtime import ExecutionRuntimeCancelledError

        calls: list[str] = []
        app_session = create_test_application_session(build_dev_authenticated_subject())

        def query_runner(*, runtime_controls, **_: object) -> list[dict[str, object]]:
            calls.append("started")
            client.app.state.execution_cancelled_candidate_ids = frozenset(
                {"candidate-123"}
            )
            if runtime_controls.cancellation_probe is not None:
                cancellation_requested = runtime_controls.cancellation_probe()
                calls.append(f"cancelled={cancellation_requested}")
                if cancellation_requested:
                    raise ExecutionRuntimeCancelledError(
                        "Execution canceled before the PostgreSQL result set was read."
                    )
            return []

        client = self._client(query_runner)

        response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "execution_unavailable")
        self.assertEqual(
            payload["audit"]["events"][-1]["candidate_state"],
            "canceled",
        )
        self.assertEqual(calls, ["started", "cancelled=True"])

    def test_execute_candidate_api_replay_fails_before_runner_invocation(self) -> None:
        calls: list[str] = []

        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            calls.append(canonical_sql)
            return [{"vendor_name": "Acme"}]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        client = self._client(query_runner)
        first_response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )
        second_response = client.post(
            "/candidates/candidate-123/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "demo-business-postgres"},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 403)
        self.assertEqual(second_response.json()["error"]["code"], "execution_denied")
        self.assertEqual(
            calls,
            ["SELECT vendor_name FROM finance.approved_vendor_spend LIMIT 1"],
        )


def test_execution_denial_serializer_preserves_release_gate_metadata(
    monkeypatch,
) -> None:
    from app.features.audit.event_model import SourceAwareAuditEvent

    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:safequery@app-postgres:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_ENVIRONMENT", "development")
    monkeypatch.setenv("SAFEQUERY_DEV_AUTH_ENABLED", "true")
    monkeypatch.delenv("SAFEQUERY_SESSION_SIGNING_KEY", raising=False)
    get_settings.cache_clear()
    from app.main import _serialize_execution_audit_events

    event_id = uuid4()
    guard_event_id = uuid4()
    event = SourceAwareAuditEvent(
        event_id=event_id,
        event_type="execution_denied",
        occurred_at=datetime.now(timezone.utc),
        request_id="request-123",
        correlation_id="correlation-123",
        user_subject="user:demo-local-operator",
        session_id="session-123",
        query_candidate_id="candidate-123",
        candidate_owner_subject="user:demo-local-operator",
        source_id="business-postgres-source",
        source_family="postgresql",
        source_flavor="warehouse",
        dataset_contract_version=4,
        semantic_contract_version="approved_vendor_spend.v1",
        schema_snapshot_version=9,
        execution_policy_version=3,
        connector_profile_version=1,
        release_gate_scenario={
            "scenario_id": "postgresql-positive-approved-vendor-spend-top-vendors",
            "source_id": "business-postgres-source",
            "candidate_id": "candidate-123",
            "guard_decision": "allow",
            "guard_audit_event_id": guard_event_id,
            "execution_run_id": event_id,
            "execution_audit_event_id": event_id,
        },
        primary_deny_code="DENY_RESULT_VALIDATION_FAILED",
        denial_cause="result_validation_failed",
        denial_reason="row_count_mismatch",
        candidate_state="denied",
    )

    serialized = _serialize_execution_audit_events([event])

    assert serialized[0]["semantic_contract_version"] == "approved_vendor_spend.v1"
    assert serialized[0]["release_gate_scenario"] == {
        "scenario_id": "postgresql-positive-approved-vendor-spend-top-vendors",
        "source_id": "business-postgres-source",
        "candidate_id": "candidate-123",
        "guard_decision": "allow",
        "guard_audit_event_id": str(guard_event_id),
        "execution_run_id": str(event_id),
        "execution_audit_event_id": str(event_id),
    }


if __name__ == "__main__":
    unittest.main()
