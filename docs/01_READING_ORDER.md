# SafeQuery Reading Order

This reading order is intended to help new contributors understand SafeQuery from first principles without losing the trust boundary or replaceability model that anchor the current source-aware and UX-foundation baseline.

## Recommended Sequence

### 1. Baseline Orientation

1. [00_BRIEF_SafeQuery_docs.md](./00_BRIEF_SafeQuery_docs.md)
   Read the founding brief first to understand scope, non-goals, and fixed stack decisions.
2. [requirements/requirements-baseline.md](./requirements/requirements-baseline.md)
   Read next to understand the product and control-plane requirements the implementation must satisfy.
3. [requirements/technology-stack.md](./requirements/technology-stack.md)
   Use this to understand the current baseline stack and the constraints on implementation choices.

### 2. Architecture and Trust Decisions

4. [adr/ADR-0001-frontend-backend-split.md](./adr/ADR-0001-frontend-backend-split.md)
   Start the ADR set with the application shape and trust boundary split.
5. [adr/ADR-0002-auth-bridge-with-saml-2-0.md](./adr/ADR-0002-auth-bridge-with-saml-2-0.md)
   Review how enterprise authentication is integrated without pulling raw SAML complexity into the core app.
6. [adr/ADR-0003-sql-server-driver-strategy.md](./adr/ADR-0003-sql-server-driver-strategy.md)
   Understand the current SQL Server connectivity baseline and future evaluation path.
7. [adr/ADR-0004-postgresql-as-app-system-of-record.md](./adr/ADR-0004-postgresql-as-app-system-of-record.md)
   Confirm where application-owned records live and why.
8. [adr/ADR-0005-pluggable-sql-generation-engine.md](./adr/ADR-0005-pluggable-sql-generation-engine.md)
   Review the replaceability boundary around SQL generation.
9. [adr/ADR-0006-query-approval-and-execution-integrity.md](./adr/ADR-0006-query-approval-and-execution-integrity.md)
   Read how previewed SQL is bound to execution through candidate IDs, SQL hashes, and TTL-bound approval.
10. [adr/ADR-0007-adapter-isolation-and-schema-context-supply.md](./adr/ADR-0007-adapter-isolation-and-schema-context-supply.md)
    Review how the SQL generation adapter is isolated from production SQL Server credentials.
11. [adr/ADR-0008-session-and-authorization-model.md](./adr/ADR-0008-session-and-authorization-model.md)
    Review how session handling, CSRF, and default-deny authorization are assigned to the trusted backend.
12. [adr/ADR-0009-dataset-exposure-and-governance.md](./adr/ADR-0009-dataset-exposure-and-governance.md)
    Review how allow-listed data exposure, approved views, and schema governance work in the pilot.
13. [design/system-context.md](./design/system-context.md)
    Move from decisions to architecture views.
14. [design/container-view.md](./design/container-view.md)
    Review how the major runtime parts collaborate.
15. [design/runtime-flow.md](./design/runtime-flow.md)
    Finish the baseline architecture pass with the end-to-end request lifecycle and execution control flow.
16. [design/sql-guard-spec.md](./design/sql-guard-spec.md)
    Use this as the baseline spec for T-SQL validation and deny behavior.
17. [design/sql-guard-deny-catalog.md](./design/sql-guard-deny-catalog.md)
    Review the deny code taxonomy before implementing guard outcomes or audit mappings.
18. [design/sql-guard-deny-corpus.md](./design/sql-guard-deny-corpus.md)
    Use this to understand the minimum deny scenarios the pilot must continue to block.
19. [design/audit-event-model.md](./design/audit-event-model.md)
    Read this before implementing persistence, replay, or operational diagnostics.

### 3. UX Foundation

20. [design/operator-workflow-information-architecture.md](./design/operator-workflow-information-architecture.md)
    Read the operator shell contract before changing navigation, composition, preview, or result surfaces in the current baseline.
21. [../DESIGN.md](../DESIGN.md)
    Read the visual design contract after the workflow contract so shell hierarchy, typography, spacing, and interaction posture stay aligned.
22. [design/query-lifecycle-state-machine.md](./design/query-lifecycle-state-machine.md)
    Read the lifecycle state model before implementing UI states or backend transitions that must share the same authoritative vocabulary.

### 4. Source-Aware and Evaluation Baseline

23. [adr/ADR-0010-mlflow-observability-and-evaluation-plane.md](./adr/ADR-0010-mlflow-observability-and-evaluation-plane.md)
    Review why MLflow is used for tracing, evaluation, and model-lifecycle support without becoming the trusted control plane in the current baseline.
24. [design/search-and-analyst-capabilities.md](./design/search-and-analyst-capabilities.md)
    Review how the current source-aware baseline adds governed search and analyst-style capabilities without moving trust boundaries out of the application.
25. [design/evaluation-harness.md](./design/evaluation-harness.md)
    Use this to understand how NL2SQL quality should be measured safely in the current source-aware baseline.

### 5. Approved Follow-on Direction

26. [adr/ADR-0011-target-source-registry-and-single-source-execution-model.md](./adr/ADR-0011-target-source-registry-and-single-source-execution-model.md)
    Read first in this section to understand how SafeQuery expands beyond one hard-coded business source while keeping request, candidate, and execution paths single-source.
27. [adr/ADR-0012-multi-dialect-connector-and-guard-profile-strategy.md](./adr/ADR-0012-multi-dialect-connector-and-guard-profile-strategy.md)
    Review how source families, flavors, connector profiles, and guard profiles are separated so future onboarding does not redesign the control plane.
28. [design/target-source-registry.md](./design/target-source-registry.md)
    Use this to understand the concrete registry model, source lifecycle expectations, and application PostgreSQL separation guardrails.
29. [design/dialect-capability-matrix.md](./design/dialect-capability-matrix.md)
    Review the family and flavor rollout matrix before planning connector, guard, or evaluation work for additional sources.
30. [adr/ADR-0013-operator-workflow-and-ui-foundation.md](./adr/ADR-0013-operator-workflow-and-ui-foundation.md)
    Read this to understand why the product shell is workflow-first and why the Epic A shell remains a developer state demo.
31. [adr/ADR-0014-ui-implementation-stack-and-oss-adoption-boundaries.md](./adr/ADR-0014-ui-implementation-stack-and-oss-adoption-boundaries.md)
    Review how SafeQuery may borrow OSS ergonomics without turning the product into a generic chat shell or moving trust boundaries.
32. [implementation-roadmap.md](./implementation-roadmap.md)
    Finish this section with the current implementation sequence so roadmap work stays aligned with the reviewed docs direction.

### 6. Local Setup and Threat Review

33. [local-development.md](./local-development.md)
    Use this once the document set is clear so local startup follows the reviewed topology and role split.
34. [security/threat-model.md](./security/threat-model.md)
    Finish with the threat model and residual risks for the current source-aware and UX-foundation baseline before pilot readiness review.

## Source Hierarchy

The repository follows this source hierarchy:

Brief -> Requirements -> ADR -> Design

Treat that chain as intentional derivation, not as a license for drift. If a lower-level document no longer matches an upstream decision, update the affected set together.

## When to Use Which Document

- Use the brief when validating whether a proposed change still fits the PoC.
- Use requirements docs when writing issues or acceptance criteria.
- Use ADRs when a change challenges an already-fixed design choice.
- Use design docs when discussing interfaces, boundaries, and sequence flow.

## Important Lens

When reading any SafeQuery doc, keep this question in mind:

What is trusted and application-owned, and what is replaceable or supplemental?

That distinction is the core organizing principle across the documentation set.
