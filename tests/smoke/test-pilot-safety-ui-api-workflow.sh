#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ ! -x frontend/node_modules/.bin/vitest ]]; then
  echo "frontend dependencies are missing; run 'cd frontend && npm ci' before this smoke" >&2
  exit 1
fi

bash tests/smoke/test-pilot-safety-checklist.sh

(
  cd frontend
  npm test -- app/pilot-safety-smoke.test.tsx
)

(
  cd backend
  python3 -m pytest \
    tests/test_preview_persistence.py::test_http_preview_submission_persists_request_and_candidate_records \
    tests/test_preview_persistence.py::test_http_preview_entitlement_denial_persists_audit_event_without_secrets \
    tests/test_operator_workflow_history.py::test_operator_workflow_history_includes_execution_run_records \
    tests/test_operator_workflow_history.py::test_operator_workflow_history_surfaces_safe_audit_evidence_and_citations \
    tests/test_candidate_execute_api.py::CandidateExecuteApiTestCase::test_execute_candidate_api_runs_only_approved_candidate_identifier \
    tests/test_candidate_execute_api.py::CandidateExecuteApiTestCase::test_execute_candidate_api_rejects_source_switch_without_consuming_approval \
    tests/test_candidate_execute_api.py::CandidateExecuteApiTestCase::test_execute_candidate_api_applies_candidate_bound_operator_cancellation_without_consuming_approval
)
