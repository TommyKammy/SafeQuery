import re
import unittest
from importlib.metadata import metadata, requires


def _dependency_names(requirements: list[str]) -> set[str]:
    names: set[str] = set()
    for requirement in requirements:
        match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
        if match:
            names.add(match.group(1).lower().replace("_", "-"))
    return names


class BackendPackagingTestCase(unittest.TestCase):
    def test_test_extra_declares_pytest_dependencies_without_runtime_bloat(
        self,
    ) -> None:
        package_metadata = metadata("safequery-backend")
        provided_extras = set(package_metadata.get_all("Provides-Extra") or [])

        self.assertIn("test", provided_extras)

        package_requirements = list(requires("safequery-backend") or [])
        test_requirements = [
            requirement
            for requirement in package_requirements
            if "extra == 'test'" in requirement or 'extra == "test"' in requirement
        ]
        runtime_requirements = [
            requirement
            for requirement in package_requirements
            if "extra ==" not in requirement
        ]

        test_dependency_names = _dependency_names(test_requirements)
        runtime_dependency_names = _dependency_names(runtime_requirements)

        self.assertIn("pytest", test_dependency_names)
        self.assertIn("httpx", test_dependency_names)
        self.assertNotIn("pytest", runtime_dependency_names)
        self.assertNotIn("httpx", runtime_dependency_names)
