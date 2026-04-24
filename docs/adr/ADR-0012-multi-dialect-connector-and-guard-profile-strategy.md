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

### Planned MySQL Family Requirements

MySQL is approved as planned source-family metadata only. Listing the family does
not activate execution, connector selection, runtime defaults, or release-gate
coverage.

A MySQL source profile must be registered by the backend with explicit values
for:

- `source_id`
- `source_family=mysql`
- `source_flavor`, such as `mysql-8` or `aurora-mysql`
- `dataset_contract_version`
- `schema_snapshot_version`
- `execution_policy_version`
- `connector_profile_version`
- `dialect_profile_version`

The adapter and client must not infer MySQL eligibility from a driver name,
hostname, connection URL, request hint, source label, or generated SQL text.
Connector selection remains backend-owned and source-registry governed.

The planned MySQL connector profile must require:

- read-only database identity and privileges
- backend-owned secret indirection such as `safequery/business/mysql/<source_id>/reader`
- explicit connection identity fields for host, port, database, username, and TLS posture
- connect timeout, statement timeout, and cancellation probe support
- separation from application PostgreSQL credentials, service identity, and endpoint

The planned MySQL dialect and guard profile must require:

- single-statement canonical SQL before preview, guard, and execution
- MySQL-aware keyword and identifier normalization
- backtick identifier quoting by default, with unsafe `sql_mode` assumptions rejected
- one effective policy-bounded `LIMIT`; `OFFSET` is allowed only with an explicit bounded `LIMIT`
- a read-only statement allowlist for `SELECT` and `WITH`-leading SELECT queries
- fail-closed denies for writes, multi-statement SQL, procedure execution, dynamic SQL,
  external data access, system catalog access, cross-database references, temporary
  object mutation, unsafe row bounds, and unsupported syntax

Audit, operator-history, and release-gate reconstruction for MySQL must preserve
the source and profile fields needed to prove which backend-selected profile was
used: `source_id`, `source_family`, `source_flavor`, dataset contract version,
schema snapshot version, execution policy version, connector profile version,
dialect profile version, guard version, and primary deny code.

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
