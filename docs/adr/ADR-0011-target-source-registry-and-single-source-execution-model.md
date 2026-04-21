# ADR-0011: Target Source Registry and Single-Source Execution Model

## Status

Accepted

## Date

2026-04-21

## Owner

SafeQuery architecture

## Decision Drivers

- extend SafeQuery beyond one hard-coded business source without moving the trusted control boundary
- preserve preview-before-execute and candidate-based execution integrity while multiple business sources are introduced
- prevent cross-source ambiguity, auto-routing drift, and federated-query scope creep in the first expansion step

## Supersedes

None

## Related Docs

- [../requirements/requirements-baseline.md](../requirements/requirements-baseline.md)
- [../design/runtime-flow.md](../design/runtime-flow.md)
- [../design/query-lifecycle-state-machine.md](../design/query-lifecycle-state-machine.md)
- [../design/target-source-registry.md](../design/target-source-registry.md)
- [./ADR-0006-query-approval-and-execution-integrity.md](./ADR-0006-query-approval-and-execution-integrity.md)

## Context

The current SafeQuery baseline executes approved read-only SQL against a constrained business data source through an application-owned control path.

Follow-on work expands that posture so the product can support more than one approved business source family without changing the core trust model. That expansion must not weaken:

- application-owned authorization and execution control
- preview-before-execute
- candidate-only execution
- replay protection
- audit reconstruction

The expansion also must not encourage cross-source execution before the application has explicit source-aware governance, guard, and execution controls.

## Decision

SafeQuery will introduce an application-owned target source registry.

The registry is the authoritative place where the trusted backend resolves source metadata such as:

- `source_id`
- source family
- optional source flavor
- connector profile
- dialect profile
- dataset contract linkage
- schema snapshot linkage
- source activation state

SafeQuery will use a single-source execution model.

In that model:

- every SQL-backed request binds to exactly one `source_id`
- every stored candidate remains valid only for the `source_id` recorded with that candidate
- every execution attempt uses the `source_id` already bound to the candidate
- execution does not re-select a source at execute time

Phase 1 source selection must be explicit and application-owned.

The initial expansion does not allow:

- cross-source joins
- federated queries
- fan-out execution across multiple sources
- implicit source auto-routing

## Consequences

Positive outcomes:

- multiple business sources can be onboarded without redesigning candidate integrity
- the operator can understand and verify source identity before preview and execution
- audit, evaluation, and policy checks can reason about one authoritative `source_id` per request path

Tradeoffs:

- the application must own source registration and lifecycle management
- source-aware authorization, schema supply, and invalidation logic become required follow-on work
- new source families must be onboarded deliberately instead of being inferred from the adapter

## Rejected Alternatives

- treating source selection as an adapter concern
- allowing execute-time source switching after preview
- supporting federated or auto-routed execution in the first expansion phase
