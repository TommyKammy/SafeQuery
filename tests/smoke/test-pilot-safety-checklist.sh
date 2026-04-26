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
  "^## First-Run Productization Gate$"
  "^## Scope and Non-Requirements$"
  "^## Focused Sign-Off Commands$"
  "^## Epic K Readiness Evidence$"
  "^## Epic L Auth-Context Evidence$"
  "^## Source-Aware Checklist$"
  "^## Fail-Closed Negative Checks$"
  "^## Release Gate and Runtime Controls$"
  "^## Operator Sign-Off Workflow$"
  "first-run productization"
  "Epic K"
  "Epic L Auth-Context Evidence"
  "Epic L-P"
  "auth-source"
  "entitlement-decision"
  "non-developer evaluator"
  "migrations"
  "demo source visibility"
  "entitlement readiness"
  "first-run doctor"
  "backend health"
  "frontend health"
  "non-empty active source selector"
  "does not mean real LLM generation or real SQL execution is production-ready"
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
  "backend/tests/test_first_run_doctor.py"
  "backend/tests/test_demo_source_seed.py"
  "tests/smoke/test-pilot-safety-ui-api-workflow.sh"
  "tests/smoke/test-compose-operator-workflow-source-selector.sh"
  "source selection, preview, guard, execute, result, and audit"
  "inspection by combining the focused UI smoke"
  "placeholder SQL or placeholder result rows"
  "entitlement-denial"
  "execution-denial"
  "cancellation"
  "pilot baseline coverage"
  "optional search, analyst, and MLflow extension tracks are not required"
)

for pattern in "${required_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$checklist"; then
    echo "$checklist missing required checklist pattern: $pattern" >&2
    exit 1
  fi
done

if grep -Eqi "(postgresql.*approved[[:space:]]+follow-on|approved[[:space:]]+follow-on.*postgresql)" "$checklist"; then
  echo "$checklist must not describe PostgreSQL as follow-on for the 2-source core path" >&2
  exit 1
fi

dialect_matrix="docs/design/dialect-capability-matrix.md"
if ! grep -Eqi '^\| `postgresql` \|.*\| active baseline \|$' "$dialect_matrix"; then
  echo "$dialect_matrix must mark PostgreSQL as active baseline for the 2-source core path" >&2
  exit 1
fi

for entrypoint in docs/README.md docs/01_READING_ORDER.md; do
  if ! grep -Fq "pilot-safety-verification-checklist.md" "$entrypoint"; then
    echo "$entrypoint missing pilot-safety checklist link" >&2
    exit 1
  fi
done
