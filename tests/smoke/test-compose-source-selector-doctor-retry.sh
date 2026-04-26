#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

SAFEQUERY_SMOKE_SOURCE_ONLY=1 source tests/smoke/test-compose-operator-workflow-source-selector.sh

tmp_dir="$(mktemp -d)"
response_file="$tmp_dir/response.json"
curl_error_file="$tmp_dir/curl.err"
stderr_file="$tmp_dir/stderr.txt"

cleanup_retry_test() {
  rm -rf "$tmp_dir"
}

trap cleanup_retry_test EXIT

smoke_sleep() {
  :
}

passing_doctor_payload() {
  printf '%s\n' '{
    "status": "pass",
    "checks": [
      {"name": "database", "status": "pass", "message": "Application database connectivity is ready."},
      {"name": "migrations", "status": "pass", "message": "Alembic migration posture is current."},
      {"name": "source_registry", "status": "pass", "message": "Active demo source registry record is present."},
      {"name": "dataset_contract", "status": "pass", "message": "Demo source dataset contract linkage is ready."},
      {"name": "schema_snapshot", "status": "pass", "message": "Demo source schema snapshot is approved."},
      {"name": "entitlement_seed", "status": "pass", "message": "Dev/local entitlement seed is present."},
      {"name": "execution_connector", "status": "pass", "message": "Demo source execution connector binding is ready."},
      {"name": "backend", "status": "pass", "message": "Backend health endpoint is reachable and healthy."},
      {"name": "frontend", "status": "pass", "message": "Frontend app surface is reachable."}
    ]
  }'
}

doctor_attempts=0
curl() {
  doctor_attempts=$((doctor_attempts + 1))
  if [[ "$doctor_attempts" -eq 1 ]]; then
    printf '%s\n' '{"status":"fail","checks":[{"name":"frontend","status":"fail","message":"Frontend app surface is not reachable yet."}]}'
    return 0
  fi

  passing_doctor_payload
}

if ! wait_for_first_run_doctor "http://backend.example/doctor/first-run" 3; then
  echo "doctor retry test failed: first-run doctor did not recover after a transient failing payload" >&2
  exit 1
fi

if [[ "$doctor_attempts" -ne 2 ]]; then
  echo "doctor retry test failed: expected 2 attempts for transient failure, got $doctor_attempts" >&2
  exit 1
fi

doctor_attempts=0
curl() {
  doctor_attempts=$((doctor_attempts + 1))
  printf '%s\n' '{"status":"fail","checks":[{"name":"frontend","status":"fail","message":"Frontend app surface is not reachable yet."},{"name":"migrations","status":"pass","message":"Database migrations are current."}]}'
}

if wait_for_first_run_doctor "http://backend.example/doctor/first-run" 2 2>"$stderr_file"; then
  echo "doctor retry test failed: persistent failing payload unexpectedly passed" >&2
  exit 1
fi

if [[ "$doctor_attempts" -ne 2 ]]; then
  echo "doctor retry test failed: expected 2 attempts for persistent failure, got $doctor_attempts" >&2
  exit 1
fi

for expected in "frontend" "fail" "Frontend app surface is not reachable yet."; do
  if ! grep -Fq "$expected" "$stderr_file"; then
    echo "doctor retry test failed: persistent failure output missing $expected" >&2
    exit 1
  fi
done

echo "doctor retry test passed"
