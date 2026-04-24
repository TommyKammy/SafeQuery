#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

checklist="docs/pilot-safety-verification-checklist.md"

if [[ ! -f "$checklist" ]]; then
  echo "missing pilot-safety checklist: $checklist" >&2
  exit 1
fi

required_patterns=(
  "^# 2-Source Core Path Pilot-Safety Verification Checklist$"
  "^## Scope and Non-Requirements$"
  "^## Focused Sign-Off Commands$"
  "^## Source-Aware Checklist$"
  "^## Fail-Closed Negative Checks$"
  "^## Release Gate and Runtime Controls$"
  "^## Operator Sign-Off Workflow$"
  "MSSQL"
  "business PostgreSQL"
  "auth"
  "explicit source selection"
  "generation"
  "guard"
  "preview"
  "candidate-only execute"
  "audit"
  "evaluation"
  "release gate"
  "runtime controls"
  "cross-source execution"
  "application PostgreSQL reuse"
  "stale candidates"
  "owner mismatch"
  "unsupported source binding"
  "missing audit coverage"
  "backend/tests/test_release_gate.py"
  "backend/tests/test_source_bound_execute_path.py"
  "backend/tests/test_execution_runtime_controls.py"
  "backend/tests/test_mssql_execution_connector.py"
  "backend/tests/test_postgresql_execution_connector.py"
  "optional search, analyst, and MLflow extension tracks are not required"
)

for pattern in "${required_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$checklist"; then
    echo "$checklist missing required checklist pattern: $pattern" >&2
    exit 1
  fi
done

for entrypoint in docs/README.md docs/01_READING_ORDER.md; do
  if ! grep -Fq "pilot-safety-verification-checklist.md" "$entrypoint"; then
    echo "$entrypoint missing pilot-safety checklist link" >&2
    exit 1
  fi
done
