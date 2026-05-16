from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.features.evaluation import build_release_gate_assurance_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the SafeQuery governed-answer assurance release gate."
    )
    parser.add_argument(
        "--fixture-set",
        type=Path,
        default=(
            Path(__file__).resolve().parents[2]
            / "tests"
            / "fixtures"
            / "governed_answer_vendor_spend_fixtures.json"
        ),
        help="Path to a governed_answer_assurance.v1 fixture set.",
    )
    parser.add_argument(
        "--observed-answer-artifacts",
        type=Path,
        help="Optional JSON file containing observed governed-answer artifacts.",
    )
    args = parser.parse_args()

    observed_answer_artifacts: tuple[dict[str, Any], ...] = ()
    if args.observed_answer_artifacts is not None:
        payload = json.loads(args.observed_answer_artifacts.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("observed_answer_artifacts", ())
        observed_answer_artifacts = tuple(payload)

    report = build_release_gate_assurance_report(
        fixture_set_path=args.fixture_set,
        observed_answer_artifacts=observed_answer_artifacts,
    )
    print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
    if report.status == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
