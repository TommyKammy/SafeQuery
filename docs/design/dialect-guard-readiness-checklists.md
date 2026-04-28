# Dialect Guard Readiness Checklists

## Purpose

These checklists define the guard evidence required before a planned source
family or flavor can move toward connector activation. This is
checklist/evaluation planning only. No new guard profile is activated by this
document, and no connector dispatch is enabled for MySQL, MariaDB, Aurora, or
Oracle.

Every planned family must remain non-executable until backend-owned registry
state, dialect guard evidence, runtime controls, audit coverage, evaluation
outcomes, and release-gate reconstruction agree. The explicit blocker is
missing checklist evidence. Stale evidence or evidence inferred from adapter
output, labels, hostnames, connection strings, driver names, traces, or other
non-authoritative surfaces keeps the family fail-closed.

## Common Evidence Required

Each planned checklist item must be testable or reviewable before connector
activation. The minimum evidence package for a family or flavor is:

- Canonicalization fixtures proving single-statement normalization, identifier
  handling, row-bound placement, parser-failure behavior, and profile-version
  drift failure.
- Deny corpus fixtures mapping every denial to the SafeQuery-owned deny catalog
  and to a primary audit deny code.
- System catalog access fixtures for dialect catalog tables, information schema
  surfaces, metadata procedures, cross-database or cross-schema discovery, and
  equivalent engine-specific metadata access.
- Mutating statement fixtures for data writes, DDL, temp object mutation,
  transaction control, grants, session state mutation, and any statement shape
  that can change durable or session-visible state.
- Comment and hint fixtures for inline comments, block comments, optimizer
  hints, executable comments, and syntax that can hide or alter execution.
- Function and procedure fixtures for stored procedure execution, package or
  routine invocation, dynamic SQL, file or network access functions, sleep or
  delay functions, and extension-specific unsafe functions.
- Dialect-specific edge-case fixtures covering quoting, case handling,
  escaping, row bounds, unsupported syntax, engine-version drift, flavor
  inheritance, and connector or dialect profile mismatch.
- Release-gate reconstruction evidence showing positive, guard-deny,
  unsupported-binding, stale-policy, lifecycle, audit, and operator-history
  scenarios are reconstructed from SafeQuery-owned evaluation outcomes and
  source-aware audit events.

The evidence package must include expected allow or reject decisions, source
family, optional source flavor, connector profile version, dialect profile
version, guard version, dataset contract, schema snapshot, execution policy,
primary deny code, and the audit fields needed to prove which backend-selected
profile was used.

## MySQL Guard Readiness Checklist

MySQL remains planned metadata only until this checklist is complete and
reviewed with the activation gate.

- Canonicalization: prove MySQL-aware single-statement canonicalization,
  backtick identifier normalization, string escaping, comment stripping,
  parser-failure denial, and profile-version drift rejection.
- `sql_mode`: reject unsafe or unknown `sql_mode` assumptions, and include
  fixtures for quoting, ANSI mode, backslash escaping, and version drift.
- Deny corpus: include writes, DDL, transaction control, grants, multi-statement
  SQL, temporary table mutation, stored procedure execution, dynamic SQL,
  `LOAD DATA`, file access, sleep or benchmark functions, and unsupported
  syntax.
- System catalogs: deny unsafe access to `information_schema`, `mysql`, and
  `performance_schema` unless a later approved dataset contract explicitly
  exposes a reviewed view.
- Row bounds: prove exactly one effective policy-bounded `LIMIT`; `OFFSET` is
  allowed only with an explicit bounded `LIMIT`; conflicting or hidden limits
  are rejected before preview and execution.
- Comments and hints: include inline comments, block comments, version comments,
  optimizer hints, and comment-wrapped deny patterns.
- Evidence: provide MySQL positive, deny, row-bounding, connector-selection,
  lifecycle, audit, operator-history, and release-gate reconstruction scenarios
  before any source can leave non-executable planned state.

## MariaDB Guard Readiness Checklist

MariaDB is a distinct planned `source_family=mariadb` profile. It may reuse
MySQL-family expectations only where an approved backend profile says so; it
must not silently inherit the MySQL guard profile.

- Canonicalization: prove MariaDB mode and version-specific canonicalization
  drift, identifier quoting, string escaping, parser-failure denial, and
  profile-version drift rejection.
- Deny corpus: include writes, DDL, transaction control, grants, multi-statement
  SQL, temporary object mutation, stored routine execution, dynamic SQL, file
  access, sleep or benchmark functions, and unsupported syntax.
- System catalogs: deny unsafe `information_schema`, `mysql`,
  `performance_schema`, and MariaDB-specific catalog or status surfaces unless
  explicitly exposed by an approved dataset contract.
- Comments and hints: include optimizer hints, executable comments, versioned
  comments, and comment-obfuscated deny patterns.
- Row bounds: prove one policy-bounded `LIMIT`, safe `OFFSET` behavior only
  with an explicit bounded `LIMIT`, and fail-closed handling for hidden or
  conflicting row bounds after MariaDB delta review.
- Evidence: provide a separate MariaDB positive, deny, row-bounding,
  timeout/cancellation, audit, operator-history, and release-gate reconstruction
  corpus, even when cases overlap MySQL.

## Aurora PostgreSQL Guard Readiness Checklist

Aurora PostgreSQL is a planned flavor selected only from backend registry
metadata as `source_family=postgresql` and `source_flavor=aurora-postgresql`.
It is not a top-level family and is not activated by labels, hostnames,
connection URLs, driver names, adapter hints, or generated SQL text.

- Inheritance: prove the source uses the PostgreSQL guard profile,
  canonicalization rules, deny corpus, and row-bounding behavior unless an
  approved flavor delta explicitly overrides a rule.
- Flavor deltas: review cluster or instance endpoint identity, engine version,
  TLS posture, timeout behavior, cancellation behavior, and source-unavailable
  classification without trusting client-supplied metadata.
- Deny corpus: run PostgreSQL system catalog, mutating statement, function,
  comment, row-bound, unsupported syntax, stale-policy, and profile mismatch
  denies against the Aurora flavor.
- Evidence: provide flavor regression cases that prove release-gate
  reconstruction records source id, family, flavor, connector profile, dialect
  profile, guard version, dataset contract, schema snapshot, execution policy,
  and primary deny code.

## Aurora MySQL Guard Readiness Checklist

Aurora MySQL is a planned flavor selected only from backend registry metadata as
`source_family=mysql` and `source_flavor=aurora-mysql`. Because the underlying
MySQL family remains planned, Aurora MySQL also remains non-executable until
the MySQL guard, connector, audit, and evaluation evidence is approved.

- Inheritance: prove the source uses the approved MySQL guard profile,
  canonicalization rules, deny corpus, and row-bounding behavior unless an
  approved flavor delta explicitly overrides a rule.
- Flavor deltas: review cluster or instance endpoint identity, engine version,
  TLS posture, timeout behavior, cancellation behavior, and source-unavailable
  classification without trusting client-supplied metadata.
- Deny corpus: run MySQL system catalog, mutating statement, stored procedure,
  dynamic SQL, comment, hint, row-bound, unsupported syntax, stale-policy, and
  profile mismatch denies against the Aurora flavor.
- Evidence: provide flavor regression cases that prove release-gate
  reconstruction records source id, family, flavor, connector profile, dialect
  profile, guard version, dataset contract, schema snapshot, execution policy,
  and primary deny code.

## Oracle Guard Readiness Checklist

Oracle remains long-range planned metadata only until this checklist is complete
and reviewed with the activation gate.

- Canonicalization: prove Oracle-aware single-statement canonicalization,
  quoted identifier case preservation, schema qualification rules,
  parser-failure denial, and profile-version drift rejection.
- Row bounds: approve one policy-bounded shape, such as `FETCH FIRST` or
  `ROWNUM`, before guard, preview, and execution; reject conflicting, hidden,
  or post-filter row bounds.
- Deny corpus: include writes, DDL, transaction control, grants, multi-statement
  SQL, PL/SQL blocks, procedure execution, dynamic SQL, database link access,
  package state mutation, session mutation, external file or network access,
  unsafe functions, and unsupported syntax.
- System catalogs: deny unsafe access to Oracle data dictionary and dynamic
  performance views unless an approved dataset contract explicitly exposes a
  reviewed view.
- Comments and hints: include inline comments, block comments, optimizer hints,
  hint-obfuscated deny patterns, and mixed-case quoted identifiers.
- Evidence: provide Oracle positive, deny, identifier and quoting,
  row-bounding, timeout/cancellation, audit, operator-history, and release-gate
  reconstruction scenarios before any active connector work begins.

## Activation Boundary

The checklists are prerequisites for later activation review, not activation
approval. A planned family or flavor cannot dispatch connector code, appear in
active execution coverage, or be reported as runtime-capable unless the
activation gate has authoritative evidence for guard readiness, runtime
readiness, secrets readiness, audit readiness, evaluation readiness,
dataset-contract readiness, and row-bounds readiness. If any evidence is
missing, malformed, partial, stale, or inferred from a derived surface, the
family must remain non-executable and fail closed.

Runtime readiness evidence is connector-specific. MySQL and Aurora MySQL require
an approved `mysqlclient` or `PyMySQL` backend driver check, MariaDB requires an
approved MariaDB connector or reviewed `PyMySQL` compatibility check, Aurora
PostgreSQL requires `psycopg`, and Oracle requires `python-oracledb` plus Oracle
client or wallet prerequisites when that deployment shape requires them.

Secrets readiness evidence must prove backend-owned secret indirection for the
planned source profile. Blank secrets, TODO/sample credentials, raw connection
strings, application PostgreSQL credentials, and client-supplied connection
material are activation blockers. First-run doctor and support-bundle output may
name dependency and readiness states, but any connection string, endpoint
credential, or secret-bearing diagnostic must be redacted before logs, exports,
or support bundles are emitted.
