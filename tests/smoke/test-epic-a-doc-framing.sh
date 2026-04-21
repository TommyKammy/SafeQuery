#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

readme_path="README.md"
docs_index_path="docs/README.md"

for path in "$readme_path" "$docs_index_path"; do
  if [[ ! -f "$path" ]]; then
    echo "missing required doc: $path" >&2
    exit 1
  fi
done

readme_required_patterns=(
  "developer state demo"
  "not the intended production information architecture"
  "docs/design/operator-workflow-information-architecture.md"
  "next authoritative UI direction"
  "UX-1 workflow-first operator shell contract"
)

docs_index_required_patterns=(
  "developer state demo"
  "UX-1 workflow-first operator shell contract"
  "authoritative UI direction"
  "not the production information architecture"
  "docs/design/operator-workflow-information-architecture.md"
)

missing=0

for pattern in "${readme_required_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$readme_path"; then
    echo "README missing Epic A framing text: $pattern" >&2
    missing=1
  fi
done

for pattern in "${docs_index_required_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$docs_index_path"; then
    echo "docs/README missing Epic A framing text: $pattern" >&2
    missing=1
  fi
done

exit "$missing"
