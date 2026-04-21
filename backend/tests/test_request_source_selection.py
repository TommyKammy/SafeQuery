import importlib
import os
import unittest

from fastapi.testclient import TestClient

from app.core.config import get_settings


class RequestSourceSelectionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        get_settings.cache_clear()
        main_module = importlib.import_module("app.main")
        self.app = main_module.create_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        os.environ.pop("SAFEQUERY_APP_POSTGRES_URL", None)
        get_settings.cache_clear()

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
            },
        )


if __name__ == "__main__":
    unittest.main()
