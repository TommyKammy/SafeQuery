from __future__ import annotations

import importlib
import os
import unittest
from datetime import datetime, timezone
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
from app.services.demo_source_seed import (
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
            )
        }
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        os.environ.pop("SAFEQUERY_ENVIRONMENT", None)
        os.environ.pop("SAFEQUERY_DEV_AUTH_ENABLED", None)
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

        response = self._client().post(
            "/requests/preview",
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

    def test_enabled_dev_auth_still_enforces_preview_entitlement(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "development"
        os.environ["SAFEQUERY_DEV_AUTH_ENABLED"] = "true"
        self._seed_restricted_source("restricted-business-postgres")

        response = self._client().post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "restricted-business-postgres",
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

    def test_production_default_dev_auth_blocks_preview_http_request(self) -> None:
        os.environ["SAFEQUERY_ENVIRONMENT"] = "production"

        response = self._client().post(
            "/requests/preview",
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
                    "code": "http_error",
                    "message": "Forbidden",
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
