#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

required_paths=(
  "backend/alembic.ini"
  "backend/alembic/env.py"
  "backend/alembic/script.py.mako"
  "backend/alembic/versions"
)

missing=0

for path in "${required_paths[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "missing migration scaffold path: $path" >&2
    missing=1
  fi
done

exit "$missing"
