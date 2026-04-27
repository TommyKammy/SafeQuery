#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root/backend"

echo "pilot-safety-api-execute: candidate-only execute, result inspection, cancellation, and audit history contract"
python3 -m pytest \
  tests/test_candidate_execute_api.py::CandidateExecuteApiTestCase::test_execute_candidate_api_runs_only_approved_candidate_identifier \
  tests/test_candidate_execute_api.py::CandidateExecuteApiTestCase::test_execute_candidate_api_rejects_source_switch_without_consuming_approval \
  tests/test_candidate_execute_api.py::CandidateExecuteApiTestCase::test_execute_candidate_api_applies_candidate_bound_operator_cancellation_without_consuming_approval \
  tests/test_operator_workflow_history.py::test_operator_workflow_history_includes_execution_run_records \
  tests/test_operator_workflow_history.py::test_operator_workflow_history_surfaces_safe_audit_evidence_and_citations
