import os
import unittest

from pydantic import ValidationError

from app.core.config import Settings, get_settings


class ApplicationPostgresGuardTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("SAFEQUERY_APP_POSTGRES_URL", None)
        os.environ.pop("SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL", None)
        get_settings.cache_clear()

    def test_unsafe_postgres_role_reuse_fails_during_settings_validation(self) -> None:
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

    def test_safe_postgres_role_separation_remains_valid(self) -> None:
        settings = Settings(
            app_postgres_url="postgresql://safequery:safequery@db:5432/safequery",
            business_postgres_source_url=(
                "postgresql://safequery_source:read-only@pg-source:5432/business"
            ),
            _env_file=None,
            _env_prefix="SAFEQUERY_",
        )

        self.assertEqual(
            str(settings.app_postgres_url),
            "postgresql://safequery:safequery@db:5432/safequery",
        )
        self.assertEqual(
            str(settings.business_postgres_source_url),
            "postgresql://safequery_source:read-only@pg-source:5432/business",
        )

    def test_startup_settings_cache_fails_closed_for_unsafe_env(self) -> None:
        os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )
        os.environ["SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL"] = (
            "postgresql://safequery:safequery@db:5432/safequery"
        )

        with self.assertRaisesRegex(
            ValidationError,
            "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse "
            "SAFEQUERY_APP_POSTGRES_URL",
        ):
            get_settings()


if __name__ == "__main__":
    unittest.main()
