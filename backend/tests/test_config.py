import os
import tempfile
import unittest

from pydantic import ValidationError

from app.core.config import Settings


class SettingsTestCase(unittest.TestCase):
    def test_missing_required_database_url_raises(self) -> None:
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
                    "SAFEQUERY_DATABASE_URL="
                    "postgresql://safequery:safequery@db:5432/safequery\n"
                )

            settings = Settings(
                _env_file=env_path,
                _env_prefix="SAFEQUERY_",
            )

        self.assertEqual(
            str(settings.database_url),
            "postgresql://safequery:safequery@db:5432/safequery",
        )
        self.assertEqual(settings.app_name, "SafeQuery API")
        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.cors_origins, ["http://localhost:3000"])


if __name__ == "__main__":
    unittest.main()
