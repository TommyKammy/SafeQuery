#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ ! -f "DESIGN.md" ]]; then
  echo "missing design contract: DESIGN.md" >&2
  exit 1
fi

required_regex_patterns=(
  "^# SafeQuery Design Contract$"
  "^## Color System$"
  "^## Typography$"
  "^## Spacing and Rhythm$"
  "^## Surface Hierarchy$"
  "^## Component Treatment$"
  "^## Responsive Behavior$"
)

required_literal_patterns=(
  "Source inspiration: https://getdesign.md/playstation/design-md"
  "inspired by the PlayStation direction and is not an official PlayStation design system"
  "Vanna-provided UI surfaces are out of scope"
)

for pattern in "${required_regex_patterns[@]}"; do
  if ! grep -Eq "$pattern" "DESIGN.md"; then
    echo "DESIGN.md missing required pattern: $pattern" >&2
    exit 1
  fi
done

for pattern in "${required_literal_patterns[@]}"; do
  if ! grep -Fq "$pattern" "DESIGN.md"; then
    echo "DESIGN.md missing required text: $pattern" >&2
    exit 1
  fi
done
