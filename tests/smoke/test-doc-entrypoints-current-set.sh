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
  "^### Source-Aware and Evaluation Baseline$"
  "current source-aware and UX-foundation baseline"
  "current baseline for SafeQuery contributors"
)

reading_order_required_patterns=(
  "^### 1\\. Baseline Orientation$"
  "^### 2\\. Architecture and Trust Decisions$"
  "^### 3\\. UX Foundation$"
  "^### 4\\. Source-Aware and Evaluation Baseline$"
  "^### 5\\. Local Setup and Threat Review$"
  "current source-aware and UX-foundation baseline"
)

docs_index_required_links=(
  "00_BRIEF_SafeQuery_docs.md"
  "01_READING_ORDER.md"
  "../README.md"
  "local-development.md"
  "requirements/requirements-baseline.md"
  "requirements/technology-stack.md"
  "adr/ADR-0001-frontend-backend-split.md"
  "adr/ADR-0002-auth-bridge-with-saml-2-0.md"
  "adr/ADR-0003-sql-server-driver-strategy.md"
  "adr/ADR-0004-postgresql-as-app-system-of-record.md"
  "adr/ADR-0005-pluggable-sql-generation-engine.md"
  "adr/ADR-0006-query-approval-and-execution-integrity.md"
  "adr/ADR-0007-adapter-isolation-and-schema-context-supply.md"
  "adr/ADR-0008-session-and-authorization-model.md"
  "adr/ADR-0009-dataset-exposure-and-governance.md"
  "design/system-context.md"
  "design/container-view.md"
  "design/runtime-flow.md"
  "design/sql-guard-spec.md"
  "design/sql-guard-deny-catalog.md"
  "design/sql-guard-deny-corpus.md"
  "design/audit-event-model.md"
  "design/operator-workflow-information-architecture.md"
  "../DESIGN.md"
  "design/query-lifecycle-state-machine.md"
  "adr/ADR-0010-mlflow-observability-and-evaluation-plane.md"
  "design/search-and-analyst-capabilities.md"
  "design/evaluation-harness.md"
  "security/threat-model.md"
)

reading_order_required_links=(
  "00_BRIEF_SafeQuery_docs.md"
  "requirements/requirements-baseline.md"
  "requirements/technology-stack.md"
  "adr/ADR-0001-frontend-backend-split.md"
  "adr/ADR-0002-auth-bridge-with-saml-2-0.md"
  "adr/ADR-0003-sql-server-driver-strategy.md"
  "adr/ADR-0004-postgresql-as-app-system-of-record.md"
  "adr/ADR-0005-pluggable-sql-generation-engine.md"
  "adr/ADR-0006-query-approval-and-execution-integrity.md"
  "adr/ADR-0007-adapter-isolation-and-schema-context-supply.md"
  "adr/ADR-0008-session-and-authorization-model.md"
  "adr/ADR-0009-dataset-exposure-and-governance.md"
  "design/system-context.md"
  "design/container-view.md"
  "design/runtime-flow.md"
  "design/sql-guard-spec.md"
  "design/sql-guard-deny-catalog.md"
  "design/sql-guard-deny-corpus.md"
  "design/audit-event-model.md"
  "design/operator-workflow-information-architecture.md"
  "../DESIGN.md"
  "design/query-lifecycle-state-machine.md"
  "adr/ADR-0010-mlflow-observability-and-evaluation-plane.md"
  "design/search-and-analyst-capabilities.md"
  "design/evaluation-harness.md"
  "local-development.md"
  "security/threat-model.md"
)

for pattern in "${docs_index_required_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$docs_index"; then
    echo "$docs_index missing required entrypoint pattern: $pattern" >&2
    exit 1
  fi
done

for link in "${docs_index_required_links[@]}"; do
  if ! grep -Fq "$link" "$docs_index"; then
    echo "$docs_index missing required entrypoint link: $link" >&2
    exit 1
  fi
done

for pattern in "${reading_order_required_patterns[@]}"; do
  if ! grep -Eq "$pattern" "$reading_order"; then
    echo "$reading_order missing required reading-order pattern: $pattern" >&2
    exit 1
  fi
done

for link in "${reading_order_required_links[@]}"; do
  if ! grep -Fq "$link" "$reading_order"; then
    echo "$reading_order missing required reading-order link: $link" >&2
    exit 1
  fi
done
