import unittest

from scripts.ci.check_repository_hygiene import LOCAL_PATH_PATTERNS


def find_matches(line: str) -> list[str]:
    return [
        match.group(0)
        for pattern in LOCAL_PATH_PATTERNS
        for match in [pattern.search(line)]
        if match is not None
    ]


class RepositoryHygienePatternTestCase(unittest.TestCase):
    def test_matches_real_workstation_local_paths(self) -> None:
        self.assertEqual(find_matches("/Users/alice/project/"), ["/Users/alice/"])
        self.assertEqual(find_matches("/home/alice/project/"), ["/home/alice/"])
        self.assertEqual(
            find_matches(r"C:\\Users\\alice\\project\\"),
            [r"C:\\Users\\alice\\"],
        )

    def test_avoids_url_and_embedded_path_false_positives(self) -> None:
        self.assertEqual(
            find_matches("https://example.com/Users/alice/project/"),
            [],
        )
        self.assertEqual(find_matches("/usr/home/alice/project/"), [])


if __name__ == "__main__":
    unittest.main()
