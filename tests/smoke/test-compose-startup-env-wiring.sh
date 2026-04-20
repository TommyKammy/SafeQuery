#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

compose_file="infra/docker-compose.yml"
dockerfile="frontend/Dockerfile"

required_compose_patterns=(
  "API_INTERNAL_BASE_URL: \${API_INTERNAL_BASE_URL:?Missing API_INTERNAL_BASE_URL. Copy .env.example to .env.}"
  "NEXT_PUBLIC_API_BASE_URL: \${NEXT_PUBLIC_API_BASE_URL:?Missing NEXT_PUBLIC_API_BASE_URL. Copy .env.example to .env.}"
  "args:"
  "API_INTERNAL_BASE_URL: \${API_INTERNAL_BASE_URL:?Missing API_INTERNAL_BASE_URL. Copy .env.example to .env.}"
  "NEXT_PUBLIC_API_BASE_URL: \${NEXT_PUBLIC_API_BASE_URL:?Missing NEXT_PUBLIC_API_BASE_URL. Copy .env.example to .env.}"
)

required_dockerfile_patterns=(
  "ARG API_INTERNAL_BASE_URL"
  "ARG NEXT_PUBLIC_API_BASE_URL"
  'ENV API_INTERNAL_BASE_URL=${API_INTERNAL_BASE_URL}'
  'ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}'
  "RUN npm run build"
)

missing=0

for pattern in "${required_compose_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$compose_file"; then
    echo "missing frontend compose build env wiring: $pattern" >&2
    missing=1
  fi
done

for pattern in "${required_dockerfile_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$dockerfile"; then
    echo "missing frontend docker build env wiring: $pattern" >&2
    missing=1
  fi
done

exit "$missing"
