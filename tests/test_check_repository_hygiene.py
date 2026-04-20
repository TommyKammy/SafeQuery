import unittest

from scripts.ci.check_repository_hygiene import find_local_path_match


def build_unix_home_path(user: str, tail: str) -> str:
    return "workspace=" + "/" + "Users" + "/" + user + "/" + tail


def build_linux_home_path(user: str, tail: str) -> str:
    return "workspace=" + "/" + "home" + "/" + user + "/" + tail


def build_windows_home_path(user: str, tail: str, *, doubled: bool = False) -> str:
    slash = "\\\\" if doubled else "\\"
    return "C:" + slash + "Users" + slash + user + slash + tail


class RepositoryHygienePatternTestCase(unittest.TestCase):
    def test_matches_real_workstation_local_paths(self) -> None:
        match = find_local_path_match(build_unix_home_path("alice", "project"))
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "/" + "Users" + "/" + "alice" + "/")

        match = find_local_path_match(build_linux_home_path("alice", "project"))
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "/" + "home" + "/" + "alice" + "/")

        match = find_local_path_match(build_windows_home_path("alice", "project"))
        self.assertIsNotNone(match)
        self.assertEqual(
            match.group(0),
            build_windows_home_path("alice", ""),
        )

        match = find_local_path_match(
            build_windows_home_path("alice", "project", doubled=True)
        )
        self.assertIsNotNone(match)
        self.assertEqual(
            match.group(0),
            build_windows_home_path("alice", "", doubled=True),
        )

    def test_avoids_url_and_embedded_path_false_positives(self) -> None:
        self.assertIsNone(
            find_local_path_match("https://example.com/Users/alice/project/")
        )
        self.assertIsNone(find_local_path_match("/usr/home/alice/project/"))


if __name__ == "__main__":
    unittest.main()
