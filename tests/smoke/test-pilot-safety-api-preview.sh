#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root/backend"

echo "pilot-safety-api-preview: preview persistence, source entitlement denial, and guard audit contract"
python3 -m pytest \
  tests/test_preview_persistence.py::test_http_preview_submission_persists_request_and_candidate_records \
  tests/test_preview_persistence.py::test_http_preview_entitlement_denial_persists_audit_event_without_secrets
