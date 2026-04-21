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
- whether the source is healthy, paused, or blocked for execution

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

This prevents the application system of record from becoming a default execution target by accident.
