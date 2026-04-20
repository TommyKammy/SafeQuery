# SafeQuery Reading Order

This reading order is intended to help new contributors understand SafeQuery from first principles without losing the trust boundary or replaceability model.

## Recommended Sequence

1. [00_BRIEF_SafeQuery_docs.md](./00_BRIEF_SafeQuery_docs.md)
   Read the founding brief first to understand scope, non-goals, and fixed stack decisions.
2. [requirements/requirements-baseline.md](./requirements/requirements-baseline.md)
   Read next to understand the product and control-plane requirements the implementation must satisfy.
3. [requirements/technology-stack.md](./requirements/technology-stack.md)
   Use this to understand the current baseline stack and the constraints on implementation choices.
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
13. [adr/ADR-0010-mlflow-observability-and-evaluation-plane.md](./adr/ADR-0010-mlflow-observability-and-evaluation-plane.md)
    Review why MLflow is used for tracing, evaluation, and model-lifecycle support without becoming the trusted control plane.
14. [design/system-context.md](./design/system-context.md)
   Move from decisions to architecture views.
15. [design/container-view.md](./design/container-view.md)
    Review how the major runtime parts collaborate.
16. [design/runtime-flow.md](./design/runtime-flow.md)
    Finish with the end-to-end request lifecycle and execution control flow.
17. [design/search-and-analyst-capabilities.md](./design/search-and-analyst-capabilities.md)
    Review how SafeQuery can add Cortex Search and Analyst-like capabilities without moving trust boundaries out of the application.
18. [design/query-lifecycle-state-machine.md](./design/query-lifecycle-state-machine.md)
    Read the explicit lifecycle states before implementing generation, approval, or execution APIs.
19. [design/sql-guard-spec.md](./design/sql-guard-spec.md)
    Use this as the baseline spec for T-SQL validation and deny behavior.
20. [design/sql-guard-deny-catalog.md](./design/sql-guard-deny-catalog.md)
    Review the deny code taxonomy before implementing guard outcomes or audit mappings.
21. [design/sql-guard-deny-corpus.md](./design/sql-guard-deny-corpus.md)
    Use this to understand the minimum deny scenarios the pilot must continue to block.
22. [design/audit-event-model.md](./design/audit-event-model.md)
    Read this before implementing persistence, replay, or operational diagnostics.
23. [design/evaluation-harness.md](./design/evaluation-harness.md)
    Use this to understand how NL2SQL quality should be measured safely.
24. [security/threat-model.md](./security/threat-model.md)
    Finish with the threat model and residual risks before pilot readiness review.

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
