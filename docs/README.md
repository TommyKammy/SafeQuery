# SafeQuery Documentation

This directory contains the initial documentation baseline for SafeQuery, a secure enterprise NL2SQL proof of concept.

The current Epic A repository shell should be read as a developer state demo, not the production information architecture. It helps contributors inspect baseline UI states and backend posture while the product-facing shell contract is still being established.

For future frontend structure and navigation work, the UX-1 workflow-first operator shell contract in `docs/design/operator-workflow-information-architecture.md` is the next authoritative UI direction. Do not treat the current top-level prototype shell as the production information architecture.

The docs are organized to make three things clear from the start:

- which architectural decisions are already fixed
- where the trusted control boundary lives
- which parts of the system are application-owned versus replaceable

## Source of Truth Hierarchy

SafeQuery uses this documentation hierarchy:

Brief -> Requirements -> ADR -> Design

Interpretation:

- the brief captures project intent, fixed scope, and non-goals
- requirements turn that intent into baseline product and control requirements
- ADRs record accepted architectural decisions within that baseline
- design docs explain how those decisions fit together operationally

If documents drift, do not silently let lower-level docs override upstream intent. Update the affected layer or layers intentionally so the set stays consistent end to end.

## Documentation Structure

### Repository Entry Points

- [00_BRIEF_SafeQuery_docs.md](./00_BRIEF_SafeQuery_docs.md): founding brief and initial architecture input retained as a repo document
- [01_READING_ORDER.md](./01_READING_ORDER.md): recommended reading sequence for engineers and reviewers
- [local-development.md](./local-development.md): contributor startup path for env setup, compose startup, migrations, and baseline troubleshooting

### Normative Baseline

- [requirements/requirements-baseline.md](./requirements/requirements-baseline.md): product and architectural requirements baseline
- [requirements/technology-stack.md](./requirements/technology-stack.md): fixed technology stack and implementation constraints
- [adr/ADR-0001-frontend-backend-split.md](./adr/ADR-0001-frontend-backend-split.md): frontend and backend separation
- [adr/ADR-0002-auth-bridge-with-saml-2-0.md](./adr/ADR-0002-auth-bridge-with-saml-2-0.md): enterprise auth via SAML bridge
- [adr/ADR-0003-sql-server-driver-strategy.md](./adr/ADR-0003-sql-server-driver-strategy.md): SQL Server driver strategy
- [adr/ADR-0004-postgresql-as-app-system-of-record.md](./adr/ADR-0004-postgresql-as-app-system-of-record.md): PostgreSQL as application system of record
- [adr/ADR-0005-pluggable-sql-generation-engine.md](./adr/ADR-0005-pluggable-sql-generation-engine.md): pluggable SQL generation boundary
- [adr/ADR-0006-query-approval-and-execution-integrity.md](./adr/ADR-0006-query-approval-and-execution-integrity.md): candidate-based approval and execution integrity
- [adr/ADR-0007-adapter-isolation-and-schema-context-supply.md](./adr/ADR-0007-adapter-isolation-and-schema-context-supply.md): adapter isolation and context supply
- [adr/ADR-0008-session-and-authorization-model.md](./adr/ADR-0008-session-and-authorization-model.md): session, CSRF, and authorization boundary
- [adr/ADR-0009-dataset-exposure-and-governance.md](./adr/ADR-0009-dataset-exposure-and-governance.md): dataset exposure and governance controls
- [design/system-context.md](./design/system-context.md): high-level system boundary and actors
- [design/container-view.md](./design/container-view.md): major runtime containers and responsibilities
- [design/runtime-flow.md](./design/runtime-flow.md): end-to-end request, guard, preview, and execution flow
- [design/sql-guard-spec.md](./design/sql-guard-spec.md): baseline SQL Guard behavior and deny rules
- [design/sql-guard-deny-catalog.md](./design/sql-guard-deny-catalog.md): machine-readable deny code catalog for SQL Guard
- [design/sql-guard-deny-corpus.md](./design/sql-guard-deny-corpus.md): representative deny scenarios required for guard testing
- [design/audit-event-model.md](./design/audit-event-model.md): audit event taxonomy and required fields

### UX Foundation

- [design/operator-workflow-information-architecture.md](./design/operator-workflow-information-architecture.md): operator-facing shell regions, workflow states, and screen-model contract
- [../DESIGN.md](../DESIGN.md): repo-root visual contract for the SafeQuery-owned operator shell, including surface hierarchy, spacing, typography, and interaction tone
- [design/query-lifecycle-state-machine.md](./design/query-lifecycle-state-machine.md): candidate state transitions and approval TTL that UI and backend surfaces must share

### Source-Aware and Evaluation Extensions

- [adr/ADR-0010-mlflow-observability-and-evaluation-plane.md](./adr/ADR-0010-mlflow-observability-and-evaluation-plane.md): MLflow as observability, evaluation, and model-lifecycle plane
- [design/search-and-analyst-capabilities.md](./design/search-and-analyst-capabilities.md): governed semantic retrieval and analyst-style orchestration
- [design/evaluation-harness.md](./design/evaluation-harness.md): evaluation goals, datasets, and scoring
- [security/threat-model.md](./security/threat-model.md): threat model and residual risk summary for the current baseline and later extensions

## Documentation Intent

These docs should be used as the baseline for:

- later requirements refinement
- architecture review
- ADR expansion
- GitHub issue decomposition
- implementation planning

They should not be interpreted as final production deployment guidance. The current set is intentionally optimized for a safe, narrow first-phase PoC.
