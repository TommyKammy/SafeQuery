#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

target_doc="docs/design/operator-workflow-information-architecture.md"

if [[ ! -f "$target_doc" ]]; then
  echo "missing operator workflow IA contract: $target_doc" >&2
  exit 1
fi

required_regex_patterns=(
  "^# Operator Workflow Information Architecture$"
  "^## Purpose$"
  "^## Workflow Principles$"
  "^## Screen Regions$"
  "^## Primary Workflow$"
  "^## Screen Model by State$"
  "^## UX Issue Contract$"
)

required_literal_patterns=(
  "The operator shell is workflow-first, not transcript-first."
  "Left rail history"
  "Source identity"
  "Question composition"
  "SQL preview"
  "Guard review"
  "Result inspection"
  "Do not collapse the shell into a generic chat transcript layout."
  "This document defines the shell contract for later UX-1 issues."
)

for pattern in "${required_regex_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$target_doc"; then
    echo "$target_doc missing required pattern: $pattern" >&2
    exit 1
  fi
done

for pattern in "${required_literal_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$target_doc"; then
    echo "$target_doc missing required text: $pattern" >&2
    exit 1
  fi
done
