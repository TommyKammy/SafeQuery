#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

doc_path="docs/local-development.md"
readme_path="README.md"

if [[ ! -f "$doc_path" ]]; then
  echo "missing local startup guide: $doc_path" >&2
  exit 1
fi

if [[ ! -f "$readme_path" ]]; then
  echo "missing onboarding entrypoint: $readme_path" >&2
  exit 1
fi

required_patterns=(
  "README.md"
  ".env.example"
  "frontend/.env.local.example"
  "backend/.env.example"
  "infra/docker-compose.yml"
  "docker-compose --env-file .env -f infra/docker-compose.yml up --build -d"
  "curl http://localhost:8000/health"
  "alembic upgrade head"
  "alembic current"
)

missing=0

for pattern in "${required_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$doc_path"; then
    echo "missing required startup-doc detail: $pattern" >&2
    missing=1
  fi
done

local_doc_hardening_patterns=(
  "application PostgreSQL"
  "business PostgreSQL source"
  "business MSSQL source"
  "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse SAFEQUERY_APP_POSTGRES_URL"
  "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must be configured before the business MSSQL execution source can be used."
  "test_application_postgres_guard.py"
  "test_source_foundation_smoke.py"
  "tests/smoke/test-local-topology-roles.sh"
  "source_posture"
  "configured_source_count"
  "source_roles"
)

for pattern in "${local_doc_hardening_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$doc_path"; then
    echo "missing hardened local-doc detail: $pattern" >&2
    missing=1
  fi
done

readme_hardening_patterns=(
  "application PostgreSQL"
  "business PostgreSQL source"
  "business MSSQL source"
  "does not make the application database a business target"
  "test_application_postgres_guard.py"
  "test_source_foundation_smoke.py"
  "tests/smoke/test-local-topology-roles.sh"
  "source_posture"
)

for pattern in "${readme_hardening_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$readme_path"; then
    echo "missing hardened README detail: $pattern" >&2
    missing=1
  fi
done

exit "$missing"
