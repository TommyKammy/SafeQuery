#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

adr="docs/adr/ADR-0015-semantic-contract-and-sql-guard-responsibility.md"
docs_index="docs/README.md"
reading_order="docs/01_READING_ORDER.md"

if [[ ! -f "$adr" ]]; then
  echo "missing Semantic Contract vs SQL Guard ADR: $adr" >&2
  exit 1
fi

required_adr_patterns=(
  "^# ADR-0015: Semantic Contract and SQL Guard Responsibility$"
  "Semantic Contract cannot bypass SQL Guard"
  "SQL Guard cannot prove business intent correctness"
  "old answers bind to old contract versions"
  "semantic allow plus SQL deny"
  "semantic missing prevents Level 2 claims"
  "unsupported business intent"
  "unsafe executable SQL"
  "forward-only contract versioning"
  "historical audit"
  "../design/sql-guard-spec.md"
  "../design/evaluation-harness.md"
  "../implementation-roadmap.md"
)

for pattern in "${required_adr_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$adr" && ! grep -Eq "$pattern" "$adr"; then
    echo "$adr missing required semantic-contract ADR text: $pattern" >&2
    exit 1
  fi
done

for entrypoint in "$docs_index" "$reading_order"; do
  if ! grep -Fq "adr/ADR-0015-semantic-contract-and-sql-guard-responsibility.md" "$entrypoint"; then
    echo "$entrypoint missing ADR-0015 entrypoint link" >&2
    exit 1
  fi
done
