# Target Source Registry

## Purpose

This document defines the application-owned target source registry used by SafeQuery follow-on work to introduce multiple business sources without changing the trusted control boundary.

## Registry Role

The registry is the trusted backend's authoritative inventory of business sources that SafeQuery may target.

It exists to answer these questions safely:

- which `source_id` values are valid
- which source family and optional source flavor each source uses
- which connector profile and dialect profile apply
- which dataset contract and schema snapshot are active
- whether the source is active, paused, or blocked for execution

The registry does not give the adapter direct execution authority.

## Minimum Registry Fields

Each source record should include at least:

- `source_id`
- source family
- optional source flavor
- connector profile identifier
- dialect profile identifier
- dataset contract version or reference
- schema snapshot version or reference
- execution policy version or reference
- activation state
- secret or connection indirection reference owned by the backend
- operator-facing display label

## Capability Flags

The registry may also carry capability flags such as:

- supports preview and execution
- supports cancellation
- supports row-bounding rewrite
- supports governed search evidence labeling
- supports analyst-style executed evidence labeling

Capability flags are advisory backend configuration, not a substitute for execution-time checks.

## Secrets and Connection Indirection

The registry must never expose raw business-source credentials to the adapter or frontend.

The registry points to backend-owned secret material indirectly, for example through:

- secret names
- vault keys
- environment-backed secret handles

The trusted backend resolves those references only for execution or health-check code paths that are already authorized to use them.

## Activation and Deactivation

The registry should support at least these source states:

- active
- paused
- blocked
- retired

When a source changes to a non-executable state, SafeQuery should treat previously stored candidates for that source as stale and either:

- invalidate them proactively
- deny execution with an explicit stale-policy or invalidation outcome

## Future Source-Family Activation Gate

Future source families and flavors must move through explicit activation states
before they can become executable. The gate applies to MySQL, MariaDB, Aurora,
Oracle, and later families without implying that any connector work starts in
this document.

Activation states:

- `planned`: product or architecture intent exists, but the family is metadata
  only and cannot be selected for execution.
- `unsupported`: the family is intentionally rejected even if a request, adapter
  hint, source label, driver name, or connection shape claims it is available.
- `activation-candidate`: all required evidence has been assembled for review,
  but connector dispatch remains disabled until the gate is approved.
- `active-baseline`: the backend-owned registry, connector, guard, audit,
  evaluation, dataset, and runtime controls are approved together and covered by
  release-gate reconstruction.

Required readiness evidence before `active-baseline`:

- Guard readiness: the family has an approved dialect profile, canonicalization
  behavior, deny catalog mapping, deny corpus, parser-failure behavior, and
  profile-version drift test. The explicit blocker is missing guard readiness.
- Runtime readiness: the family has backend-owned connector selection, driver
  availability checks, timeout handling, cancellation behavior, source
  unavailable classification, rate or concurrency limits where applicable, and
  no path that trusts adapter or client-supplied runtime hints. The explicit
  blocker is missing runtime readiness.
- Secrets readiness: the registry points only to backend-owned secret
  indirection, health checks prove the secret reference can be resolved by the
  trusted backend, and placeholder credentials, sample credentials, raw
  connection strings, or client-supplied connection material are rejected.
  The explicit blocker is missing secrets readiness.
- Audit readiness: source id, source family, optional source flavor, dataset
  contract, schema snapshot, execution policy, connector profile, dialect
  profile, guard version, deny code, row count, truncation state, request id,
  candidate id, approval id, and correlation id are present in source-aware
  audit events where applicable. The explicit blocker is missing audit
  readiness.
- Evaluation readiness: positive, safety-deny, connector-selection, lifecycle,
  runtime-control, audit reconstruction, release-gate reconstruction, and
  operator-history scenarios exist as SafeQuery-owned evaluation artifacts for
  the family or explicitly approved flavor inheritance. The explicit blocker is
  missing evaluation readiness.
- Dataset-contract readiness: the family has an approved dataset contract,
  schema snapshot linkage, entitlement posture, row-level or view-level exposure
  scope where applicable, and stale-contract denial behavior.
- Row-bounds readiness: the family has one approved bounded-read strategy that
  runs before guard, preview, and execution, with tests for unbounded reads,
  conflicting limits, offset behavior, truncation metadata, and audit
  reconstruction.

No planned or unsupported family may dispatch connector code, appear in active
execution coverage, or be treated as runtime-capable because it appears in a
roadmap, matrix, sample config, adapter output, analyst artifact, MLflow trace,
or operator-facing label. `activation-candidate` is also non-executable until
the gate is approved. If any required guard, runtime, secrets, audit, or
evaluation evidence is missing, malformed, stale, or only inferred from a
non-authoritative surface, SafeQuery must reject activation and keep the family
non-executable.

## Health Checks

Registry-aware health checks should verify the backend can still resolve:

- connector profile
- dialect profile
- secret indirection
- dataset contract reference
- schema snapshot reference

Health checks should not expand into unrestricted schema crawling or adapter-owned introspection.

## Application PostgreSQL Separation

Application PostgreSQL is not implicitly a registered business source.

If business PostgreSQL support is added, it must appear as an explicit business `source_id` with:

- separate connection identity
- separate connector profile
- separate policy and dataset contract

This prevents the application system of record from becoming a default execution target inadvertently.

## Planned MySQL Source Profile

MySQL onboarding must use the same registry boundary as the active MSSQL and
business PostgreSQL baselines. A MySQL source is not executable until the
registry contains an approved backend-owned source profile and the active
runtime code has an approved connector, dialect, guard, audit, and evaluation
profile for that source family.

Minimum MySQL profile fields:

- `source_id`
- `source_family=mysql`
- `source_flavor`, for example `mysql-8` or `aurora-mysql`
- `dataset_contract_version`
- `schema_snapshot_version`
- `execution_policy_version`
- `connector_profile_version`
- `dialect_profile_version`
- `activation_posture`
- `connection_reference`

The `connection_reference` must be a secret indirection such as
`safequery/business/mysql/<source_id>/reader`. It must not contain raw
credentials, placeholder credentials treated as valid, or client-supplied
connection material. MySQL connection identity must include the backend-resolved
host, port, database, username, and TLS posture so audit reconstruction can
prove the execution target without exposing the secret value.

The planned MySQL source profile must remain distinct from application
PostgreSQL. MySQL connector profiles must not reuse application PostgreSQL
credentials, service identities, endpoints, or migration settings.

MySQL capability flags are advisory until activation. Runtime allow decisions
must come from the authoritative registry record plus the approved connector and
guard profiles, not from adapter hints, request metadata, source labels,
connection string shape, or generated SQL.

## Planned Aurora Flavor Profiles

Aurora source onboarding must preserve the source-family boundary:

- Aurora PostgreSQL registry records use `source_family=postgresql` and
  `source_flavor=aurora-postgresql`.
- Aurora MySQL registry records use `source_family=mysql` and
  `source_flavor=aurora-mysql`.

The flavor value is authoritative only when it is stored on the backend-owned
registry record. SafeQuery must reject any attempt to derive Aurora support from
client request fields, adapter hints, driver names, connection URLs, hostnames,
source labels, or generated SQL text.

Aurora PostgreSQL inherits PostgreSQL generation, canonicalization, SQL Guard,
row-bounding, and deny-corpus behavior. Its profile-specific deltas are the
Aurora PostgreSQL connector identity, cluster or instance endpoint posture, TLS
posture, engine version, timeout and cancellation verification, and flavor
regression coverage.

Aurora MySQL inherits the planned MySQL generation, canonicalization, SQL Guard,
row-bounding, and deny-corpus behavior. Its profile-specific deltas are the
Aurora MySQL connector identity, cluster or instance endpoint posture, TLS
posture, engine version, timeout and cancellation verification, and flavor
regression coverage. Aurora MySQL remains planned metadata until the underlying
MySQL family activation work is approved.

Both Aurora flavors must preserve audit and release-gate reconstruction fields
for source id, source family, source flavor, dataset contract, schema snapshot,
execution policy, connector profile, dialect profile, guard version, and primary
deny code.
