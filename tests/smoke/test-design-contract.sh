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
  "^## Workflow-First Shell Posture$"
  "^## Color System$"
  "^## Typography$"
  "^## Spacing and Rhythm$"
  "^## Surface Hierarchy$"
  "^## Component Treatment$"
  "^## Tone and Interaction Emphasis$"
  "^## Responsive Behavior$"
)

required_literal_patterns=(
  "Source inspiration: https://getdesign.md/playstation/design-md"
  "inspired by the PlayStation direction and is not an official PlayStation design system"
  "Vanna-provided UI surfaces are out of scope"
  "The left rail history is persistent workflow memory, not a transcript surface."
  "Source identity must stay visible in the frame or support surfaces across every workflow state."
  "Execute or run actions must stay unavailable until the operator is reviewing a trusted preview state backed by the server-owned candidate record."
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
