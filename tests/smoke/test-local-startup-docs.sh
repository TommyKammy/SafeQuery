#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

doc_path="docs/local-development.md"

if [[ ! -f "$doc_path" ]]; then
  echo "missing local startup guide: $doc_path" >&2
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

exit "$missing"
