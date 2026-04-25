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

        self.assertEqual(settings.sql_generation.provider, "disabled")

        with self.assertRaisesRegex(
            RuntimeError, "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL"
        ):
            settings.require_business_postgres_source()

        with self.assertRaisesRegex(
            RuntimeError, "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING"
        ):
            settings.require_business_mssql_source()

    def test_sql_generation_provider_settings_select_local_llm_without_source_credentials(
        self,
    ) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            sql_generation_provider="local_llm",
            sql_generation_local_llm_base_url="http://local-llm:8080",
            sql_generation_local_llm_model="safequery-local-sql",
            business_postgres_source_url=(
                "postgresql://source_reader:read-only@pg-source:5432/business"
            ),
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        self.assertEqual(settings.sql_generation.provider, "local_llm")
        self.assertEqual(
            str(settings.sql_generation.local_llm_base_url),
            "http://local-llm:8080/",
        )
        self.assertEqual(
            settings.sql_generation.local_llm_model,
            "safequery-local-sql",
        )
        dumped = settings.sql_generation.model_dump(mode="json", exclude_none=True)
        self.assertNotIn("business_postgres_source_url", dumped)
        self.assertNotIn("business_mssql_source_connection_string", dumped)

    def test_sql_generation_provider_fails_closed_when_selected_without_endpoint(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_SQL_GENERATION_LOCAL_LLM_BASE_URL must be configured",
        ):
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                sql_generation_provider="local_llm",
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

    def test_sql_generation_vanna_provider_requires_endpoint(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_SQL_GENERATION_VANNA_BASE_URL must be configured",
        ):
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                sql_generation_provider="vanna",
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

    def test_business_postgres_source_must_not_reuse_app_postgres_url(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse "
            "SAFEQUERY_APP_POSTGRES_URL",
        ):
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                business_postgres_source_url=(
                    "postgresql://safequery:safequery@db:5432/safequery"
                ),
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

    def test_business_mssql_source_whitespace_only_fails_closed(self) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            business_mssql_source_connection_string="   \t  ",
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        with self.assertRaisesRegex(
            RuntimeError, "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING"
        ):
            settings.require_business_mssql_source()

    def test_business_mssql_source_trims_outer_whitespace(self) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            business_mssql_source_connection_string=(
                "  Driver={ODBC Driver 18 for SQL Server};Server=tcp:mssql,1433  "
            ),
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        self.assertEqual(
            settings.require_business_mssql_source().connection_string,
            "Driver={ODBC Driver 18 for SQL Server};Server=tcp:mssql,1433",
        )

    def test_dev_auth_is_disabled_by_default_and_can_enable_for_development(self) -> None:
        default_settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )
        development_settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            dev_auth_enabled=True,
            environment="development",
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        self.assertFalse(default_settings.dev_auth_enabled)
        self.assertTrue(development_settings.dev_auth_enabled)

    def test_dev_auth_cannot_enable_for_production_or_staging(self) -> None:
        for environment in ("production", "staging"):
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(
                    ValidationError,
                    "SAFEQUERY_DEV_AUTH_ENABLED is only allowed",
                ):
                    Settings(
                        app_postgres_url=(
                            "postgresql://safequery:safequery@db:5432/safequery"
                        ),
                        dev_auth_enabled=True,
                        environment=environment,
                        _env_file=None,
                        _env_prefix="SAFEQUERY_",
                    )


if __name__ == "__main__":
    unittest.main()
