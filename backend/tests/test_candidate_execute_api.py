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
    PreviewRequest,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.db.session import require_preview_submission_session
from app.features.auth.dev import build_dev_authenticated_subject
from app.features.auth.session import create_test_application_session
from app.services.candidate_lifecycle import (
    CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY,
)


class CandidateExecuteApiTestCase(unittest.TestCase):
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

    def _client(self, query_runner) -> TestClient:
        main_module = importlib.import_module("app.main")
        app = main_module.create_app()
        app.dependency_overrides[require_preview_submission_session] = (
            lambda: self.session
        )
        app.state.execution_query_runner = query_runner
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

    def test_execute_candidate_api_persists_source_aware_execution_audit_events(
        self,
    ) -> None:
        def query_runner(*, canonical_sql: str, **_: object) -> list[dict[str, object]]:
            return [{"vendor_name": f"Vendor {index}"} for index in range(225)]

        app_session = create_test_application_session(build_dev_authenticated_subject())
        response = self._client(query_runner).post(
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


if __name__ == "__main__":
    unittest.main()
