#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ ! -x frontend/node_modules/.bin/vitest ]]; then
  echo "frontend dependencies are missing; run 'cd frontend && npm ci' before this smoke" >&2
  exit 1
fi

echo "pilot-safety-ui: source selection, source-bound preview, execution posture, result, and audit surfaces"
(
  cd frontend
  npm test -- app/pilot-safety-smoke.test.tsx
)
