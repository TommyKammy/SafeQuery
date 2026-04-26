import importlib
import json
import os
import sys
import unittest
from io import StringIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.logging import JsonLogFormatter, configure_logging, get_logger


class SourceFoundationSmokeTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        for name in (
            "SAFEQUERY_APP_POSTGRES_URL",
            "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
            "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING",
        ):
            os.environ.pop(name, None)
        get_settings.cache_clear()

    def _reload_main_module(self):
        get_settings.cache_clear()
        if "app.main" in sys.modules:
            return importlib.reload(sys.modules["app.main"])
        return importlib.import_module("app.main")

    def test_compose_real_source_execution_smoke_is_candidate_bound_and_skippable(
        self,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        script_path = (
            repo_root / "tests" / "smoke" / "test-compose-real-source-execution.sh"
        )
        script = script_path.read_text()
        compose = (repo_root / "infra" / "docker-compose.yml").read_text()
        readme = (repo_root / "README.md").read_text()

        self.assertIn("smoke_not_run", script)
        self.assertIn("docker info", script)
        self.assertIn("exit 125", script)
        self.assertIn("/candidates/candidate-compose-postgres-real-source/execute", script)
        self.assertIn("/candidates/candidate-compose-mssql-real-source/execute", script)
        self.assertIn('"canonical_sql":"SELECT 1"', script)
        self.assertIn('"selected_source_id":"demo-business-mssql"', script)
        self.assertIn("execution_completed", script)
        self.assertIn("PreviewAuditEvent", script)
        self.assertIn("SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL", compose)
        self.assertIn(
            "bash tests/smoke/test-compose-real-source-execution.sh",
            readme,
        )

    def test_safe_source_posture_reports_explicit_roles(self) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            business_postgres_source_url=(
                "postgresql://source_reader:read-only@pg-source:5432/business"
            ),
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        telemetry = settings.source_posture_telemetry()

        self.assertEqual(telemetry.source_posture, "coherent")
        self.assertEqual(telemetry.configured_source_count, 2)
        self.assertEqual(
            telemetry.source_roles.model_dump(),
            {
                "application_postgres_persistence": "configured",
                "business_postgres_source_generation": "configured",
                "business_mssql_source_execution": "unconfigured",
            },
        )

    def test_ambiguous_source_configuration_fails_closed(self) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            business_mssql_source_connection_string="  \t  ",
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must not be "
            "whitespace-only",
        ):
            settings.source_posture_telemetry()

    def test_startup_logs_source_role_posture(self) -> None:
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        stream = StringIO()
        configure_logging()
        handler = get_logger().handlers[0].__class__(stream)
        handler.setFormatter(JsonLogFormatter())
        get_logger().addHandler(handler)

        try:
            main_module = self._reload_main_module()
            with TestClient(main_module.app):
                pass
        finally:
            get_logger().removeHandler(handler)

        lines = [line for line in stream.getvalue().splitlines() if line.strip()]
        startup_events = [
            json.loads(line)
            for line in lines
            if json.loads(line).get("event") == "app.startup"
        ]

        self.assertTrue(startup_events)
        startup_event = startup_events[-1]
        self.assertEqual(startup_event["source_posture"], "coherent")
        self.assertEqual(startup_event["configured_source_count"], 1)
        self.assertEqual(
            startup_event["source_roles"],
            {
                "application_postgres_persistence": "configured",
                "business_postgres_source_generation": "unconfigured",
                "business_mssql_source_execution": "unconfigured",
            },
        )


if __name__ == "__main__":
    unittest.main()
