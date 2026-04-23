import importlib
import os
import unittest
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.db.session import require_preview_submission_session
from app.features.auth.context import AuthenticatedSubject, require_authenticated_subject


class RequestSourceSelectionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        get_settings.cache_clear()
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        main_module = importlib.import_module("app.main")
        self.app = main_module.create_app()
        self.app.dependency_overrides[require_authenticated_subject] = lambda: AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )
        self.app.dependency_overrides[require_preview_submission_session] = (
            lambda: self.session
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        os.environ.pop("SAFEQUERY_APP_POSTGRES_URL", None)
        get_settings.cache_clear()
        self.app.dependency_overrides.clear()

    def _seed_authoritative_source_governance(
        self,
        *,
        source_id: str,
        source_posture: SourceActivationPosture,
        snapshot_status: SchemaSnapshotReviewStatus = SchemaSnapshotReviewStatus.APPROVED,
        owner_binding: str = "group:finance-analysts",
        security_review_binding: Optional[str] = None,
        exception_policy_binding: Optional[str] = None,
    ) -> None:
        source = RegisteredSource(
            id=uuid4(),
            source_id=source_id,
            display_label=f"{source_id} display",
            source_family="postgresql",
            source_flavor="warehouse",
            activation_posture=source_posture,
            connector_profile_id=None,
            dialect_profile_id=None,
            dataset_contract_id=None,
            schema_snapshot_id=None,
            execution_policy_id=None,
            connection_reference=f"vault:{source_id}",
        )
        self.session.add(source)
        self.session.flush()

        snapshot = SchemaSnapshot(
            id=uuid4(),
            registered_source_id=source.id,
            snapshot_version=1,
            review_status=snapshot_status,
            reviewed_at=datetime.now(timezone.utc),
        )
        self.session.add(snapshot)
        self.session.flush()

        contract = DatasetContract(
            id=uuid4(),
            registered_source_id=source.id,
            schema_snapshot_id=snapshot.id,
            contract_version=1,
            display_name=f"{source_id} contract",
            owner_binding=owner_binding,
            security_review_binding=security_review_binding,
            exception_policy_binding=exception_policy_binding,
        )
        self.session.add(contract)
        self.session.flush()

        source.dataset_contract_id = contract.id
        source.schema_snapshot_id = snapshot.id
        self.session.commit()

    def test_preview_submission_rejects_missing_authenticated_subject_context(self) -> None:
        self.app.dependency_overrides.clear()
        self.app.dependency_overrides[require_preview_submission_session] = (
            lambda: self.session
        )

        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "http_error",
                    "message": "Forbidden",
                }
            },
        )

    def test_preview_submission_requires_explicit_source_id(self) -> None:
        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                }
            },
        )

    def test_preview_submission_rejects_unknown_source_id(self) -> None:
        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "unregistered-source",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                }
            },
        )

    def test_preview_submission_rejects_non_executable_source_id(self) -> None:
        self._seed_authoritative_source_governance(
            source_id="legacy-finance-archive",
            source_posture=SourceActivationPosture.PAUSED,
        )

        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "legacy-finance-archive",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                }
            },
        )

    def test_preview_submission_rejects_malformed_source_posture(self) -> None:
        source_id = uuid4()
        malformed_source = RegisteredSource(
            id=source_id,
            source_id="broken-source",
            display_label="Broken source",
            source_family="postgresql",
            source_flavor="warehouse",
            activation_posture="bogus",
            connector_profile_id=None,
            dialect_profile_id=None,
            dataset_contract_id=uuid4(),
            schema_snapshot_id=uuid4(),
            execution_policy_id=None,
            connection_reference="vault:broken-source",
        )
        malformed_contract = DatasetContract(
            id=malformed_source.dataset_contract_id,
            registered_source_id=source_id,
            schema_snapshot_id=malformed_source.schema_snapshot_id,
            contract_version=1,
            display_name="Broken contract",
            owner_binding="group:finance-analysts",
            security_review_binding=None,
            exception_policy_binding=None,
        )
        malformed_snapshot = SchemaSnapshot(
            id=malformed_source.schema_snapshot_id,
            registered_source_id=source_id,
            snapshot_version=1,
            review_status=SchemaSnapshotReviewStatus.APPROVED,
            reviewed_at=datetime.now(timezone.utc),
        )

        with patch(
            "app.services.request_preview._resolve_authoritative_source_governance",
            return_value=(malformed_source, malformed_contract, malformed_snapshot),
        ):
            response = self.client.post(
                "/requests/preview",
                json={
                    "question": "Show approved vendors by quarterly spend",
                    "source_id": "broken-source",
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                }
            },
        )

    def test_preview_submission_accepts_registered_executable_source_id(self) -> None:
        self._seed_authoritative_source_governance(
            source_id="sap-approved-spend",
            source_posture=SourceActivationPosture.ACTIVE,
        )

        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        self.assertEqual(response.status_code, 200)
        response_body = response.json()
        self.assertEqual(
            response_body["request"],
            {
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
                "state": "submitted",
            },
        )
        self.assertEqual(
            response_body["candidate"],
            {
                "source_id": "sap-approved-spend",
                "source_family": "postgresql",
                "source_flavor": "warehouse",
                "dataset_contract_version": 1,
                "schema_snapshot_version": 1,
                "state": "preview_ready",
            },
        )
        self.assertEqual(
            response_body["evaluation"],
            {
                "source_id": "sap-approved-spend",
                "state": "pending",
            },
        )

        audit = response_body["audit"]
        self.assertEqual(audit["source_id"], "sap-approved-spend")
        self.assertEqual(audit["state"], "recorded")
        self.assertEqual(
            [event["event_type"] for event in audit["events"]],
            [
                "query_submitted",
                "generation_requested",
                "generation_completed",
                "guard_evaluated",
            ],
        )
        self.assertEqual(
            audit["events"][0]["request_id"],
            response.headers["X-Request-ID"],
        )

        first_event = audit["events"][0]
        self.assertTrue(first_event["correlation_id"])
        self.assertTrue(first_event["session_id"])

        for event in audit["events"]:
            self.assertEqual(event["request_id"], response.headers["X-Request-ID"])
            self.assertEqual(event["correlation_id"], first_event["correlation_id"])
            self.assertEqual(event["user_subject"], "user:alice")
            self.assertEqual(event["session_id"], first_event["session_id"])
            self.assertEqual(event["source_id"], "sap-approved-spend")
            self.assertEqual(event["source_family"], "postgresql")
            self.assertEqual(event["source_flavor"], "warehouse")
            self.assertEqual(event["dataset_contract_version"], 1)
            self.assertEqual(event["schema_snapshot_version"], 1)
            self.assertEqual(event["application_version"], "safequery-api/0.1.0")

        self.assertIsNone(audit["events"][0]["query_candidate_id"])
        self.assertIsNone(audit["events"][1]["query_candidate_id"])
        self.assertIsNotNone(audit["events"][2]["query_candidate_id"])
        self.assertIsNotNone(audit["events"][3]["query_candidate_id"])
        self.assertEqual(
            audit["events"][2]["query_candidate_id"],
            audit["events"][3]["query_candidate_id"],
        )
        self.assertEqual(audit["events"][2]["candidate_owner_subject"], "user:alice")
        self.assertEqual(audit["events"][3]["candidate_owner_subject"], "user:alice")
        self.assertEqual(audit["events"][3]["candidate_state"], "preview_ready")

    def test_preview_submission_rejects_subject_matching_only_security_review_binding(self) -> None:
        self.app.dependency_overrides[require_authenticated_subject] = lambda: AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:security-reviewers"}),
        )
        self._seed_authoritative_source_governance(
            source_id="sap-approved-spend",
            source_posture=SourceActivationPosture.ACTIVE,
            owner_binding="group:finance-analysts",
            security_review_binding="group:security-reviewers",
        )

        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                }
            },
        )

    def test_preview_submission_rejects_subject_matching_only_exception_policy_binding(self) -> None:
        self.app.dependency_overrides[require_authenticated_subject] = lambda: AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:exception-approvers"}),
        )
        self._seed_authoritative_source_governance(
            source_id="sap-approved-spend",
            source_posture=SourceActivationPosture.ACTIVE,
            owner_binding="group:finance-analysts",
            exception_policy_binding="group:exception-approvers",
        )

        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed.",
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
