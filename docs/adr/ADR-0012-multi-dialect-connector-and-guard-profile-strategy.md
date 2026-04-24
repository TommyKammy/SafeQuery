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
- `activation_posture`
- `connection_reference`

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

### Planned MariaDB Delta Profile

MariaDB is classified as a planned MySQL-delta profile, not an active MySQL
flavor and not an adapter-inferred alias. SafeQuery may share the MySQL-family
baseline for read-only connector posture, single-statement canonicalization,
policy-bounded `LIMIT` handling, timeout and cancellation controls, audit
fields, and release-gate reconstruction fields, but MariaDB remains a distinct
backend-owned `source_family=mariadb` registry decision.

A MariaDB source profile must be registered by the backend with the same core
contract fields required for MySQL: `source_id`, `source_family`, `source_flavor`,
dataset contract version, schema snapshot version, execution policy version,
connector profile version, dialect profile version, activation posture, and
connection reference. Its planned connector profile is
`mariadb.readonly.planned.v1`, with backend-owned secret indirection such as
`safequery/business/mariadb/<source_id>/reader`.

The MariaDB delta profile must not reuse the MySQL guard profile silently. Before
activation, the approved profile must explicitly cover:

- MariaDB mode and version-specific canonicalization drift
- unsafe `sql_mode` assumptions
- information schema and system catalog deny fixtures
- optimizer hints and executable comments
- timeout, cancellation, and read-only credential behavior
- a separate MariaDB release-gate corpus, even when scenarios overlap MySQL

MariaDB execution remains disabled until the registry profile, connector
profile, dialect profile, guard profile, deny fixtures, audit mapping,
operator-history reconstruction, and release-gate corpus are approved together.
Client-supplied hints, driver names, connection URLs, hostnames, labels, or
generated SQL text must not promote a source into MariaDB support.

### Planned Aurora Flavor Profiles

Aurora PostgreSQL and Aurora MySQL are planned source flavors, not source
families. They must be selected from backend-owned source registry metadata and
must never be supplied by a client, adapter, driver name, hostname, connection
URL, source label, or generated SQL text.

An Aurora PostgreSQL source profile must preserve:

- `source_family=postgresql`
- `source_flavor=aurora-postgresql`
- the PostgreSQL generation profile
- PostgreSQL canonicalization and identifier rules
- the PostgreSQL fail-closed guard profile and deny corpus
- PostgreSQL row-bounding behavior
- audit fields for source id, family, flavor, dataset contract, schema snapshot,
  execution policy, connector profile, dialect profile, guard version, and
  primary deny code

Aurora PostgreSQL overrides only the flavor-specific connector and operational
posture: cluster or instance endpoint identity, backend-owned secret
indirection, TLS posture, engine version, timeout behavior, cancellation probe
behavior, and release-gate regressions that prove the Aurora flavor still
behaves under the PostgreSQL family controls.

An Aurora MySQL source profile must preserve:

- `source_family=mysql`
- `source_flavor=aurora-mysql`
- the planned MySQL generation profile
- MySQL canonicalization and identifier rules
- the planned MySQL fail-closed guard profile and deny corpus
- MySQL policy-bounded `LIMIT` behavior
- audit fields for source id, family, flavor, dataset contract, schema snapshot,
  execution policy, connector profile, dialect profile, guard version, and
  primary deny code

Aurora MySQL overrides only the flavor-specific connector and operational
posture: cluster or instance endpoint identity, backend-owned secret
indirection, TLS posture, engine version, timeout behavior, cancellation probe
behavior, and release-gate regressions that prove the Aurora flavor still
behaves under the MySQL family controls. Because MySQL is still planned
metadata only, Aurora MySQL must not activate execution until the underlying
MySQL family connector, guard, audit, and evaluation profiles are approved.

### Long-Range Oracle Family Requirements

Oracle is approved as long-range planned source-family metadata only. Listing
the family does not activate execution, connector selection, runtime defaults,
guard behavior, local startup services, release-gate coverage, or adapter
support.

An Oracle source profile must be registered by the backend with explicit values
for:

- `source_id`
- `source_family=oracle`
- `source_flavor`, such as `oracle-19c` or `oracle-23ai`
- `dataset_contract_version`
- `schema_snapshot_version`
- `execution_policy_version`
- `connector_profile_version`
- `dialect_profile_version`
- `activation_posture`
- `connection_reference`

The adapter, client, analyst artifacts, MLflow traces, driver name, connection
descriptor, hostname, source label, request hint, or generated SQL text must not
infer Oracle eligibility. Connector and dialect profile selection remains
backend-owned and source-registry governed.

The long-range Oracle connector profile must require:

- read-only database identity and privileges
- backend-owned secret indirection such as `safequery/business/oracle/<source_id>/reader`
- explicit connection identity fields for connect descriptor, service name,
  username, wallet reference, and TLS posture
- connect timeout, statement timeout, and cancellation probe support
- separation from application PostgreSQL credentials, service identity, and endpoint

The long-range Oracle dialect and guard profile must require:

- single-statement canonical SQL before preview, guard, and execution
- Oracle-aware keyword, schema, and identifier normalization
- preservation of double-quoted identifier case where quoting is required
- explicit selection of one canonical policy-bounded row limit shape, such as
  approved `FETCH FIRST` or `ROWNUM` handling, before guard evaluation
- a read-only statement allowlist for `SELECT` and `WITH`-leading SELECT queries
- fail-closed denies for writes, multi-statement SQL, PL/SQL blocks, procedure
  execution, dynamic SQL, external data access, system catalog access, database
  links, session or package state mutation, unsafe row bounds, and unsupported syntax

Audit, operator-history, candidate lifecycle, entitlement, and release-gate
reconstruction for Oracle must preserve the source and profile fields needed to
prove which backend-selected profile was used: `source_id`, `source_family`,
`source_flavor`, dataset contract version, schema snapshot version, execution
policy version, connector profile version, dialect profile version, guard
version, and primary deny code. Oracle activation requires a distinct positive,
deny, identifier and quoting, row-bounding, timeout, cancellation, and
release-gate reconstruction corpus before any active connector work begins.

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
