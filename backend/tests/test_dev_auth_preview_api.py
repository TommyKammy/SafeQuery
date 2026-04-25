from __future__ import annotations

import importlib
import os
import unittest
from datetime import datetime, timedelta, timezone
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
from app.features.auth.dev import build_dev_authenticated_subject
from app.features.auth.context import AuthenticatedSubject
from app.features.auth.session import (
    APPLICATION_SESSION_COOKIE,
    create_test_application_session,
)
from app.services.demo_source_seed import (
    DEMO_DEV_GOVERNANCE_BINDING,
    DEMO_DEV_SUBJECT_ID,
    DEMO_SOURCE_ID,
    seed_demo_source_governance,
)


class DevAuthPreviewApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_env = {
            name: os.environ.get(name)
            for name in (
                "SAFEQUERY_APP_POSTGRES_URL",
                "SAFEQUERY_ENVIRONMENT",
                "SAFEQUERY_DEV_AUTH_ENABLED",
                "SAFEQUERY_SESSION_SIGNING_KEY",
            )
        }
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        os.environ.pop("SAFEQUERY_ENVIRONMENT", None)
        os.environ.pop("SAFEQUERY_DEV_AUTH_ENABLED", None)
        os.environ.pop("SAFEQUERY_SESSION_SIGNING_KEY", None)
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        seed_demo_source_governance(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()
        for name, value in self._previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()

    def _client(self) -> TestClient:
        get_settings.cache_clear()
        main_module = importlib.import_module("app.main")
        app = main_module.create_app()
        app.dependency_overrides[require_preview_submission_session] = (
            lambda: self.session
        )
        return TestClient(app)

    def _seed_restricted_source(self, source_id: str) -> None:
        source = RegisteredSource(
            id=uuid4(),
            source_id=source_id,
            display_label="Restricted source",
            source_family="postgresql",
            source_flavor="warehouse",
            activation_posture=SourceActivationPosture.ACTIVE,
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
            review_status=SchemaSnapshotReviewStatus.APPROVED,
            reviewed_at=datetime.now(timezone.utc),
        )
        self.session.add(snapshot)
        self.session.flush()

        contract = DatasetContract(
            id=uuid4(),
            registered_source_id=source.id,
            schema_snapshot_id=snapshot.id,
            contract_version=1,
            display_name="Restricted source contract",
            owner_binding="group:other-operators",
            security_review_binding=None,
            exception_policy_binding=None,
        )
        self.session.add(contract)
        self.session.flush()

        source.dataset_contract_id = contract.id
        source.schema_snapshot_id = snapshot.id
        self.session.commit()

    def test_enabled_development_dev_auth_allows_demo_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"
        app_session = create_test_application_session(build_dev_authenticated_subject())

        response = self._client().post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["request"]["source_id"], DEMO_SOURCE_ID)
        self.assertEqual(payload["candidate"]["source_id"], DEMO_SOURCE_ID)
        self.assertEqual(
            payload["audit"]["events"][0]["user_subject"],
            DEMO_DEV_SUBJECT_ID,
        )
        self.assertEqual(
            payload["audit"]["events"][0]["session_id"],
            "application-session-redacted",
        )
        self.assertEqual(payload["audit"]["events"][0]["auth_source"], "test-helper")
        self.assertEqual(
            payload["audit"]["events"][0]["governance_bindings"],
            [DEMO_DEV_GOVERNANCE_BINDING],
        )
        self.assertEqual(
            payload["audit"]["events"][0]["entitlement_decision"],
            "allow",
        )
        self.assertNotIn(app_session.csrf_token, response.text)
        self.assertNotIn(app_session.cookie_value, response.text)

    def test_enabled_dev_auth_without_session_or_csrf_blocks_preview_http_request(
        self,
    ) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"

        response = self._client().post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "session_invalid",
                    "message": "Sign in again before submitting preview requests.",
                }
            },
        )

    def test_malformed_application_session_blocks_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"

        response = self._client().post(
            "/requests/preview",
            headers={"x-safequery-csrf": "csrf-token"},
            cookies={APPLICATION_SESSION_COOKIE: "malformed-session"},
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "session_invalid",
                    "message": "Sign in again before submitting preview requests.",
                }
            },
        )

    def test_mismatched_csrf_blocks_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"
        app_session = create_test_application_session(build_dev_authenticated_subject())

        response = self._client().post(
            "/requests/preview",
            headers={"x-safequery-csrf": "different-csrf-token"},
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "csrf_failed",
                    "message": "Refresh the page before submitting preview requests.",
                }
            },
        )

    def test_mismatched_session_subject_blocks_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"
        app_session = create_test_application_session(
            AuthenticatedSubject(
                subject_id="user:different-local-operator",
                governance_bindings=frozenset({DEMO_DEV_GOVERNANCE_BINDING}),
            )
        )

        response = self._client().post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "session_invalid",
                    "message": "Sign in again before submitting preview requests.",
                }
            },
        )

    def test_expired_application_session_blocks_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"
        app_session = create_test_application_session(
            build_dev_authenticated_subject(),
            now=datetime.now(timezone.utc) - timedelta(hours=2),
            ttl=timedelta(minutes=5),
        )

        response = self._client().post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "session_invalid",
                    "message": "Sign in again before submitting preview requests.",
                }
            },
        )

    def test_disabled_dev_auth_blocks_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "false"

        response = self._client().post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "unauthenticated",
                    "message": "Sign in before submitting preview requests.",
                }
            },
        )

    def test_enabled_dev_auth_still_enforces_preview_entitlement(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"
        app_session = create_test_application_session(build_dev_authenticated_subject())
        self._seed_restricted_source("restricted-business-postgres")

        response = self._client().post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "restricted-business-postgres",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "entitlement_denied",
                    "message": "The signed-in operator is not entitled to use that source.",
                }
            },
        )

    def test_production_default_dev_auth_blocks_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "production"

        response = self._client().post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": DEMO_SOURCE_ID,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "unauthenticated",
                    "message": "Sign in before submitting preview requests.",
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
