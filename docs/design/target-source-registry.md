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
