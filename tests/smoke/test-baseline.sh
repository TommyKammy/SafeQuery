#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

required_paths=(
  "DESIGN.md"
  "frontend/package.json"
  "frontend/app/page.tsx"
  "backend/pyproject.toml"
  "backend/app/main.py"
  "infra/docker-compose.yml"
  "README.md"
)

missing=0

for path in "${required_paths[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "missing required baseline path: $path" >&2
    missing=1
  fi
done

exit "$missing"
