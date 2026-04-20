import importlib
import json
import os
import unittest
from io import StringIO

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.logging import JsonLogFormatter, get_logger


class ApiErrorHandlingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["SAFEQUERY_DATABASE_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        get_settings.cache_clear()
        main_module = importlib.import_module("app.main")
        self.app = main_module.create_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        os.environ.pop("SAFEQUERY_DATABASE_URL", None)
        get_settings.cache_clear()

    def test_method_not_allowed_uses_common_error_shape(self) -> None:
        response = self.client.post("/")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "method_not_allowed",
                    "message": "Method not allowed.",
                }
            },
        )

    def test_unhandled_errors_and_logs_do_not_leak_secrets(self) -> None:
        secret = "super-secret-password"
        stream = StringIO()
        handler = get_logger().handlers[0].__class__(stream)
        handler.setFormatter(JsonLogFormatter())
        get_logger().addHandler(handler)

        @self.app.get("/_test/error")
        def raise_secret_error() -> None:
            raise RuntimeError(f"database password={secret}")

        try:
            with TestClient(self.app, raise_server_exceptions=False) as client:
                response = client.get("/_test/error")
        finally:
            get_logger().removeHandler(handler)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "internal_server_error",
                    "message": "Internal server error.",
                }
            },
        )
        self.assertNotIn(secret, response.text)

        lines = [line for line in stream.getvalue().splitlines() if line.strip()]
        events = [json.loads(line) for line in lines]
        event_names = {event["event"] for event in events}

        self.assertIn("app.startup", event_names)
        self.assertIn("request.started", event_names)
        self.assertIn("request.unhandled_exception", event_names)

        for line in lines:
            self.assertNotIn(secret, line)


if __name__ == "__main__":
    unittest.main()
