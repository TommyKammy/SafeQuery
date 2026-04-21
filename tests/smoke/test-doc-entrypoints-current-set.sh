#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

docs_index="docs/README.md"
reading_order="docs/01_READING_ORDER.md"

for path in "$docs_index" "$reading_order"; do
  if [[ ! -f "$path" ]]; then
    echo "missing required doc entrypoint: $path" >&2
    exit 1
  fi
done

docs_index_required_patterns=(
  "^### Repository Entry Points$"
  "^### Normative Baseline$"
  "^### UX Foundation$"
  "^### Source-Aware and Evaluation Extensions$"
  "design/operator-workflow-information-architecture.md"
  "../DESIGN.md"
  "adr/ADR-0010-mlflow-observability-and-evaluation-plane.md"
  "design/search-and-analyst-capabilities.md"
  "design/query-lifecycle-state-machine.md"
  "design/evaluation-harness.md"
)

reading_order_required_patterns=(
  "^### 1\\. Baseline Orientation$"
  "^### 2\\. Architecture and Trust Decisions$"
  "^### 3\\. UX Foundation$"
  "^### 4\\. Source-Aware and Evaluation Extensions$"
  "^### 5\\. Local Setup and Threat Review$"
  "local-development.md"
  "design/operator-workflow-information-architecture.md"
  "../DESIGN.md"
  "adr/ADR-0010-mlflow-observability-and-evaluation-plane.md"
  "design/search-and-analyst-capabilities.md"
  "design/evaluation-harness.md"
)

for pattern in "${docs_index_required_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$docs_index"; then
    echo "$docs_index missing required entrypoint pattern: $pattern" >&2
    exit 1
  fi
done

for pattern in "${reading_order_required_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$reading_order"; then
    echo "$reading_order missing required reading-order pattern: $pattern" >&2
    exit 1
  fi
done
