#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

compose_file="infra/docker-compose.yml"
dockerfile="frontend/Dockerfile"

required_frontend_build_args=(
  "API_INTERNAL_BASE_URL: \${API_INTERNAL_BASE_URL:?Missing API_INTERNAL_BASE_URL. Copy .env.example to .env.}"
  "NEXT_PUBLIC_API_BASE_URL: \${NEXT_PUBLIC_API_BASE_URL:?Missing NEXT_PUBLIC_API_BASE_URL. Copy .env.example to .env.}"
)

required_frontend_environment=(
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

frontend_service_has_binding() {
  local section_header="$1"
  local variable_line="$2"

  awk -v section_header="$section_header" -v variable_line="$variable_line" '
    /^  frontend:/ { in_frontend=1; next }
    in_frontend && /^[^[:space:]]/ { in_frontend=0 }
    !in_frontend { next }

    $0 == section_header { in_target=1; next }
    in_target && /^    [A-Za-z0-9_-]+:/ { in_target=0 }
    in_target && index($0, variable_line) { found=1 }

    END { exit(found ? 0 : 1) }
  ' "$compose_file"
}

for pattern in "${required_frontend_build_args[@]}"; do
  if ! frontend_service_has_binding "      args:" "$pattern"; then
    echo "missing frontend compose build.args wiring: $pattern" >&2
    missing=1
  fi
done

for pattern in "${required_frontend_environment[@]}"; do
  if ! frontend_service_has_binding "    environment:" "$pattern"; then
    echo "missing frontend compose runtime environment wiring: $pattern" >&2
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
