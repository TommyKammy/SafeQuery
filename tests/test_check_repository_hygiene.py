from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "ci" / "check_repository_hygiene.py"
)
SPEC = importlib.util.spec_from_file_location("check_repository_hygiene", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Failed to load module spec for {MODULE_PATH}")

MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CheckRepositoryHygienePatternTests(unittest.TestCase):
    def test_matches_unix_home_path(self) -> None:
        match = MODULE.find_local_path_match("workspace=/Users/tsinfra/project")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "/Users/tsinfra/")

    def test_matches_windows_single_backslash_path(self) -> None:
        match = MODULE.find_local_path_match(r"C:\Users\tsinfra\repo")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "C:\\Users\\tsinfra\\")

    def test_matches_windows_double_escaped_path(self) -> None:
        match = MODULE.find_local_path_match(r"C:\\Users\\tsinfra\\repo")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), r"C:\\Users\\tsinfra\\")

    def test_does_not_match_url_path_fragment(self) -> None:
        match = MODULE.find_local_path_match("https://example.com/Users/foo/bar")
        self.assertIsNone(match)

    def test_does_not_match_embedded_usr_home_fragment(self) -> None:
        match = MODULE.find_local_path_match("/usr/home/foo/bar")
        self.assertIsNone(match)


if __name__ == "__main__":
    unittest.main()
