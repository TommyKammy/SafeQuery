import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.features.auth.context import AuthenticatedSubject, require_authenticated_subject
from app.services.request_preview import (
    PHASE1_REGISTERED_SOURCES,
    _phase1_registered_source,
)


class RequestSourceSelectionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        get_settings.cache_clear()
        main_module = importlib.import_module("app.main")
        self.app = main_module.create_app()
        self.app.dependency_overrides[require_authenticated_subject] = lambda: AuthenticatedSubject(
            subject_id="user:alice",
            governance_bindings=frozenset({"group:finance-analysts"}),
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        os.environ.pop("SAFEQUERY_APP_POSTGRES_URL", None)
        get_settings.cache_clear()
        self.app.dependency_overrides.clear()

    def test_preview_submission_rejects_missing_authenticated_subject_context(self) -> None:
        self.app.dependency_overrides.clear()

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
        with patch.dict(
            PHASE1_REGISTERED_SOURCES,
            {
                "broken-source": _phase1_registered_source(
                    source_id="broken-source",
                    display_label="Broken source",
                    activation_posture="bogus",
                )
            },
            clear=False,
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
        response = self.client.post(
            "/requests/preview",
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "request": {
                    "question": "Show approved vendors by quarterly spend",
                    "source_id": "sap-approved-spend",
                    "state": "submitted",
                },
                "candidate": {
                    "source_id": "sap-approved-spend",
                    "state": "preview_ready",
                },
                "audit": {
                    "source_id": "sap-approved-spend",
                    "state": "recorded",
                },
                "evaluation": {
                    "source_id": "sap-approved-spend",
                    "state": "pending",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
