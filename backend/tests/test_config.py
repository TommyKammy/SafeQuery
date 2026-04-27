import os
import secrets
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
                    "Pwd=safequery-test-credential-001;"
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
            sql_generation_timeout_seconds=17,
            sql_generation_retry_count=2,
            sql_generation_circuit_breaker_failure_threshold=4,
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
        self.assertEqual(settings.sql_generation.timeout_seconds, 17)
        self.assertEqual(settings.sql_generation.retry_count, 2)
        self.assertEqual(settings.sql_generation.circuit_breaker_failure_threshold, 4)
        dumped = settings.sql_generation.model_dump(mode="json", exclude_none=True)
        self.assertNotIn("business_postgres_source_url", dumped)
        self.assertNotIn("business_mssql_source_connection_string", dumped)

    def test_sql_generation_retry_policy_settings_are_bounded(self) -> None:
        for field, value in (
            ("sql_generation_timeout_seconds", 0),
            ("sql_generation_timeout_seconds", 301),
            ("sql_generation_retry_count", -1),
            ("sql_generation_retry_count", 4),
            ("sql_generation_circuit_breaker_failure_threshold", 0),
            ("sql_generation_circuit_breaker_failure_threshold", 11),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError):
                    Settings(
                        app_postgres_url=(
                            "postgresql://safequery:safequery@db:5432/safequery"
                        ),
                        _env_file=None,
                        _env_prefix="SAFEQUERY_",
                        **{field: value},
                    )

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

    def test_business_postgres_source_rejects_placeholder_password(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must come from a trusted "
            "credential source",
        ) as exc_info:
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                business_postgres_source_url=(
                    "postgresql://source_reader:change-me@pg-source:5432/business"
                ),
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

        self.assertNotIn("source_reader:change-me", str(exc_info.exception))

    def test_business_postgres_source_rejects_blank_or_absent_password(self) -> None:
        for source_url in (
            "postgresql://source_reader:@pg-source:5432/business",
            "postgresql://source_reader@pg-source:5432/business",
        ):
            with self.subTest(source_url=source_url):
                with self.assertRaisesRegex(
                    ValidationError,
                    "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must include a "
                    "non-empty password",
                ) as exc_info:
                    Settings(
                        app_postgres_url=(
                            "postgresql://safequery:safequery@db:5432/safequery"
                        ),
                        business_postgres_source_url=source_url,
                        _env_file=None,
                        _env_prefix="SAFEQUERY_",
                    )

                error_text = str(exc_info.exception)
                self.assertIn("SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL", error_text)
                self.assertNotIn(source_url, error_text)
                self.assertNotIn("source_reader:", error_text)
                self.assertNotIn("pg-source", error_text)

    def test_business_mssql_source_rejects_placeholder_password(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must come from a "
            "trusted credential source",
        ) as exc_info:
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                business_mssql_source_connection_string=(
                    "Driver={ODBC Driver 18 for SQL Server};"
                    "Server=tcp:mssql-source,1433;"
                    "Database=business;"
                    "Uid=safequery_reader;"
                    "Pwd=change-me;"
                    "Encrypt=yes;"
                    "TrustServerCertificate=no"
                ),
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

        self.assertNotIn("Pwd=change-me", str(exc_info.exception))

    def test_business_mssql_source_rejects_empty_password_values(self) -> None:
        for password_kv in ("Pwd=", "Pwd=   ", "Password=", "Password=   "):
            with self.subTest(password_kv=password_kv):
                with self.assertRaisesRegex(
                    ValidationError,
                    "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must "
                    "include a non-empty password",
                ) as exc_info:
                    Settings(
                        app_postgres_url=(
                            "postgresql://safequery:safequery@db:5432/safequery"
                        ),
                        business_mssql_source_connection_string=(
                            "Driver={ODBC Driver 18 for SQL Server};"
                            "Server=tcp:mssql-source,1433;"
                            "Database=business;"
                            "Uid=safequery_reader;"
                            f"{password_kv};"
                            "Encrypt=yes;"
                            "TrustServerCertificate=no"
                        ),
                        _env_file=None,
                        _env_prefix="SAFEQUERY_",
                    )

                self.assertNotIn(f"{password_kv};", str(exc_info.exception))

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

    def test_production_identity_bridge_is_default_deny_and_separate_from_dev_auth(
        self,
    ) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            dev_auth_enabled=True,
            environment="development",
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        self.assertFalse(settings.production_identity_bridge.enabled)
        with self.assertRaisesRegex(
            RuntimeError,
            "SAFEQUERY_PRODUCTION_IDENTITY_BRIDGE_ENABLED",
        ):
            settings.require_production_identity_bridge()

    def test_enabled_production_identity_bridge_requires_trust_anchors(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_PRODUCTION_IDENTITY_BRIDGE_TRUSTED_ISSUER",
        ):
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                production_identity_bridge_enabled=True,
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

    def test_production_identity_bridge_rejects_placeholder_shared_secret(self) -> None:
        placeholder_bridge_value = "-".join(("change", "me"))

        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_PRODUCTION_IDENTITY_BRIDGE_SHARED_SECRET",
        ):
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                production_identity_bridge_enabled=True,
                production_identity_bridge_trusted_issuer="https://idp.example.test",
                production_identity_bridge_trusted_source="saml-oidc-bridge",
                production_identity_bridge_shared_secret=placeholder_bridge_value,
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

    def test_production_identity_bridge_rejects_blank_shared_secret(self) -> None:
        blank_bridge_value = "".join((" ", " ", " "))

        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_PRODUCTION_IDENTITY_BRIDGE_SHARED_SECRET",
        ):
            Settings(
                app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
                production_identity_bridge_enabled=True,
                production_identity_bridge_trusted_issuer="https://idp.example.test",
                production_identity_bridge_trusted_source="saml-oidc-bridge",
                production_identity_bridge_shared_secret=blank_bridge_value,
                _env_file=None,
                _env_prefix="SAFEQUERY_",
            )

    def test_enabled_production_identity_bridge_is_configured_without_dev_auth(
        self,
    ) -> None:
        generated_bridge_value = secrets.token_urlsafe(32)

        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            environment="production",
            production_identity_bridge_enabled=True,
            production_identity_bridge_trusted_issuer="https://idp.example.test",
            production_identity_bridge_trusted_source="saml-oidc-bridge",
            production_identity_bridge_shared_secret=generated_bridge_value,
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        bridge_settings = settings.require_production_identity_bridge()

        self.assertFalse(settings.dev_auth_enabled)
        self.assertTrue(bridge_settings.enabled)
        self.assertEqual(
            str(bridge_settings.trusted_issuer),
            "https://idp.example.test/",
        )
        self.assertEqual(
            bridge_settings.trusted_source,
            "saml-oidc-bridge",
        )


if __name__ == "__main__":
    unittest.main()
