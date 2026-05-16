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

    observed_answer_artifacts: tuple[Any, ...] = ()
    if args.observed_answer_artifacts is not None:
        try:
            payload = json.loads(args.observed_answer_artifacts.read_text(encoding="utf-8"))
            observed_answer_artifacts = _observed_answer_artifacts_from_payload(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            parser.error(str(exc))

    report = build_release_gate_assurance_report(
        fixture_set_path=args.fixture_set,
        observed_answer_artifacts=observed_answer_artifacts,
    )
    print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
    if report.status == "fail":
        raise SystemExit(1)


def _observed_answer_artifacts_from_payload(payload: Any) -> tuple[Any, ...]:
    if isinstance(payload, list):
        return tuple(payload)
    if isinstance(payload, dict):
        if "observed_answer_artifacts" not in payload:
            raise ValueError(
                "Observed answer artifact envelope must include "
                "'observed_answer_artifacts'."
            )
        artifacts = payload["observed_answer_artifacts"]
        if not isinstance(artifacts, list):
            raise ValueError("'observed_answer_artifacts' must be a JSON array.")
        return tuple(artifacts)
    raise ValueError(
        "Observed answer artifacts JSON must be an array or an object envelope."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
