#!/usr/bin/env python3

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DISALLOWED_TRACKED_PATHS = (
    ".DS_Store",
)
DISALLOWED_TRACKED_SEGMENTS = (
    ".codex-supervisor/",
)
USER_DIRECTORY_FRAGMENT = r"[A-Za-z0-9._-]+"
UNIX_HOME_ROOTS = (
    "Users",
    "home",
)


def build_local_path_patterns() -> tuple[re.Pattern[str], ...]:
    unix_prefix = r"(?<![A-Za-z0-9./_-])"
    unix_patterns = tuple(
        re.compile(
            unix_prefix + "/" + root + "/" + USER_DIRECTORY_FRAGMENT + "/"
        )
        for root in UNIX_HOME_ROOTS
    )
    windows_pattern = re.compile(
        r"(?<![A-Za-z0-9])"
        + r"[A-Za-z]:\\+Users\\+"
        + USER_DIRECTORY_FRAGMENT
        + r"\\+"
    )
    return unix_patterns + (windows_pattern,)


LOCAL_PATH_PATTERNS = build_local_path_patterns()


def git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def is_binary(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError as exc:
        print(f"failed to read tracked file {path}: {exc}", file=sys.stderr)
        return True
    return b"\0" in data


def main() -> int:
    tracked_files = git_ls_files()
    violations: list[str] = []

    for relative_path in tracked_files:
        normalized = relative_path.replace("\\", "/")
        if any(normalized.endswith(bad) for bad in DISALLOWED_TRACKED_PATHS):
            violations.append(
                f"{relative_path}: tracked file should not be committed"
            )
        if any(segment in normalized for segment in DISALLOWED_TRACKED_SEGMENTS):
            violations.append(
                f"{relative_path}: workstation-local supervisor state should not be tracked"
            )

        absolute_path = ROOT / relative_path
        if not absolute_path.is_file() or is_binary(absolute_path):
            continue

        try:
            content = absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            for pattern in LOCAL_PATH_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                violations.append(
                    f"{relative_path}:{line_number}: contains workstation-local path '{match.group(0)}'"
                )

    if violations:
        print("repository hygiene check failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1

    print("repository hygiene check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
