import os
import tempfile
import unittest

from pydantic import ValidationError

from app.core.config import Settings


class SettingsTestCase(unittest.TestCase):
    def test_missing_required_app_postgres_url_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                with self.assertRaises(ValidationError):
                    Settings(
                        _env_file=None,
                        _env_prefix="SAFEQUERY_",
                    )
            finally:
                os.chdir(previous_cwd)

    def test_env_file_loads_database_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, ".env")
            with open(env_path, "w", encoding="utf-8") as env_file:
                env_file.write(
                    "SAFEQUERY_APP_POSTGRES_URL="
                    "postgresql://safequery:safequery@db:5432/safequery\n"
                    "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL="
                    "postgresql://safequery_source:read-only@pg-source:5432/business\n"
                    "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING="
                    "Driver={ODBC Driver 18 for SQL Server};"
                    "Server=tcp:mssql-source,1433;"
                    "Database=business;"
                    "Uid=safequery_reader;"
                    "Pwd=change-me;"
                    "Encrypt=yes;"
                    "TrustServerCertificate=no\n"
                )

            settings = Settings(
                _env_file=env_path,
                _env_prefix="SAFEQUERY_",
            )

        self.assertEqual(
            str(settings.app_postgres_url),
            "postgresql://safequery:safequery@db:5432/safequery",
        )
        self.assertEqual(
            settings.app_postgres_identity,
            "application_postgres_persistence",
        )
        self.assertEqual(
            str(settings.require_business_postgres_source().url),
            "postgresql://safequery_source:read-only@pg-source:5432/business",
        )
        self.assertEqual(
            settings.require_business_postgres_source().identity,
            "business_postgres_source_generation",
        )
        self.assertIn(
            "Driver={ODBC Driver 18 for SQL Server}",
            settings.require_business_mssql_source().connection_string,
        )
        self.assertEqual(
            settings.require_business_mssql_source().identity,
            "business_mssql_source_execution",
        )
        self.assertEqual(settings.app_name, "SafeQuery API")
        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.cors_origins, ["http://localhost:3000"])

    def test_missing_business_source_configuration_fails_closed_when_requested(self) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        with self.assertRaisesRegex(
            RuntimeError, "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL"
        ):
            settings.require_business_postgres_source()

        with self.assertRaisesRegex(
            RuntimeError, "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING"
        ):
            settings.require_business_mssql_source()


if __name__ == "__main__":
    unittest.main()
