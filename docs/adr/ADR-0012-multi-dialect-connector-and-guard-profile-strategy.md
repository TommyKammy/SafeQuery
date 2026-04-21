# ADR-0012: Multi-Dialect Connector and Guard Profile Strategy

## Status

Accepted

## Date

2026-04-21

## Owner

SafeQuery architecture

## Decision Drivers

- expand beyond a single SQL dialect without redesigning the trusted control plane
- keep SQL Guard fail-closed while multiple business source families are introduced
- separate product-level source support from per-family connector and dialect implementation details

## Supersedes

None

## Related Docs

- [../requirements/technology-stack.md](../requirements/technology-stack.md)
- [../design/sql-guard-spec.md](../design/sql-guard-spec.md)
- [../design/dialect-capability-matrix.md](../design/dialect-capability-matrix.md)
- [./ADR-0011-target-source-registry-and-single-source-execution-model.md](./ADR-0011-target-source-registry-and-single-source-execution-model.md)

## Context

SafeQuery started from a SQL Server-first baseline. Follow-on product scope now needs a structured way to add more business source families without turning connector logic, canonicalization rules, and guard behavior into one large special case.

The application must stay responsible for:

- source registration
- connector selection
- dialect-aware canonicalization
- guard profile selection
- execution policy enforcement

## Decision

SafeQuery will distinguish between source family and source flavor.

Source families define the primary dialect and control behavior. The approved families for follow-on planning are:

- `mssql`
- `postgresql`
- `mysql`
- `mariadb`
- `oracle`

Source flavors refine deployment or connector posture without becoming a new top-level family. The initial approved examples are:

- `aurora-postgresql`
- `aurora-mysql`

Each registered source uses:

- a connector profile chosen by the trusted backend
- a dialect profile used for canonicalization and guard behavior

The connector profile defines how the application reaches the source safely.

The dialect profile defines:

- canonicalization expectations
- row-bounding strategy
- guard parsing and deny behavior
- timeout and cancellation posture

Future onboarding must happen by adding or approving profiles, not by redesigning the core SafeQuery control plane.

## Consequences

Positive outcomes:

- future family onboarding becomes explicit and reviewable
- connector behavior and guard behavior can evolve separately
- Aurora and similar variants stay modeled as flavors instead of creating needless top-level families

Tradeoffs:

- SafeQuery must maintain profile metadata and rollout state
- guard and evaluation coverage must expand with every new family
- profile drift becomes an operational concern that must be audited and invalidated safely

## Rejected Alternatives

- one hard-coded driver and guard implementation for every source
- treating Aurora as a separate SQL family
- allowing the adapter to infer dialect support independently from backend policy
