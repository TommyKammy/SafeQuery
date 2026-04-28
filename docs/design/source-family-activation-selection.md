# Source-Family Activation Selection

## Purpose

This document records the Epic V selection of the first future source family or
flavor that should advance toward active implementation planning. It compares
the planned families against the activation gate, connector threat model,
dialect capability matrix, guard readiness checklist, runtime and secret
requirements, and evaluation fixture requirements.

The selection is planning only. It does not approve activation, and active
connector implementation is out of scope.

## Selection

Recommended first planning candidate: Aurora PostgreSQL.

The selected candidate is the Aurora PostgreSQL flavor represented as
`source_family=postgresql` with `source_flavor=aurora-postgresql`, not a new
top-level source family. This keeps the first future planning step closest to
the existing PostgreSQL active baseline while still requiring Aurora-specific
runtime, connector-profile, secret, endpoint, audit, and release-gate evidence
before any executable support can be scoped.

The recommendation depends on these Epic V sources:

- `target-source-registry.md`: defines the activation states, required
  readiness evidence, runtime and secret prerequisites, and the Aurora flavor
  registry binding.
- `security/threat-model.md`: records Aurora PostgreSQL risks for authoritative
  flavor binding, connector profile and dataset contract evidence, runtime
  behavior, secrets readiness, row bounds, and audit reconstruction.
- `dialect-capability-matrix.md`: records Aurora PostgreSQL as a planned
  flavor that inherits PostgreSQL generation, canonicalization, guard, deny
  corpus, and row-bounding posture, with Aurora-specific runtime and
  release-gate regressions.
- `dialect-guard-readiness-checklists.md`: requires Aurora PostgreSQL flavor
  regression evidence before activation review.
- `evaluation-harness.md`: requires positive, deny, malformed, metadata-only,
  schema-bound, runtime-unavailable, audit reconstruction, release-gate
  reconstruction, and operator-history coverage before activation.

Aurora PostgreSQL is selected for active implementation planning because it has
the smallest safe planning distance from an existing active baseline:

- The authoritative family remains `postgresql`, which already has an active
  baseline and SafeQuery-owned guard, canonicalization, deny-corpus, and
  row-bounding posture.
- The planned delta is flavor-specific: backend-owned registry flavor binding,
  Aurora endpoint posture, TLS posture, engine version, timeout behavior,
  cancellation behavior, connector profile evidence, and flavor regression
  coverage.
- The decision avoids treating MySQL-family or Oracle-specific dialect work as
  implicitly solved by nearby roadmap text.

## Deferred Families

`mysql` is deferred because it still has missing MySQL-specific guard
readiness, missing MySQL runtime readiness, missing MySQL secrets readiness,
missing MySQL dataset-contract and row-bounds readiness, and missing MySQL
release-gate reconstruction. MySQL remains planned metadata only until a
registry-owned `mysql` source profile, connector profile, dialect profile,
guard profile, audit contract, evaluation corpus, and backend-owned secret
indirection are approved together.

`mariadb` is deferred because it still has missing MariaDB-specific guard
readiness, missing MariaDB runtime readiness, missing MariaDB secrets readiness,
missing MariaDB dataset-contract and row-bounds readiness, and missing MariaDB
release-gate reconstruction. MariaDB must stay a distinct
`source_family=mariadb` profile and must not silently inherit MySQL connector or
guard approval.

`mysql` / `aurora-mysql` is deferred because it is blocked by the underlying
MySQL family and still has missing Aurora MySQL flavor regression evidence.
Aurora MySQL cannot become executable before MySQL family readiness is approved,
and its cluster endpoint, TLS, engine-version, timeout, cancellation,
connector-profile, secret, audit, and release-gate deltas still need separate
proof.

`oracle` is deferred because it still has missing Oracle-specific guard
readiness, missing Oracle runtime and wallet readiness, missing Oracle secrets
readiness, missing Oracle dataset-contract and row-bounds readiness, and missing
Oracle release-gate reconstruction. Oracle remains long-range planned metadata
until Oracle-specific connector, dialect, guard, audit, entitlement, candidate
lifecycle, operator-history, and release-gate requirements are approved
together.

Other future families remain unselected until they have an explicit source
registry model, threat model, dialect profile, guard checklist, runtime and
secret readiness plan, and SafeQuery-owned evaluation fixture plan comparable to
the Epic V sources cited above.

## Non-Executable Boundary

This selection does not add connector code, does not wire runtime drivers, does
not add secret handling, and does not add SQL execution support.

Aurora PostgreSQL remains planned metadata only. It must not appear in active
execution coverage, runtime-capable UI/API metadata, first-run doctor success
claims, support-bundle readiness claims, or connector dispatch paths until a
later activation gate approves the complete evidence package.

The selection must not be used as evidence that Aurora support can be inferred
from hostnames, labels, adapter output, driver names, generated SQL text,
connection URLs, analyst artifacts, MLflow traces, or operator-facing summary
text. The backend-owned source registry record remains the authoritative source
of `source_family=postgresql` and `source_flavor=aurora-postgresql`.

## Next-Roadmap Handoff

The next-roadmap handoff artifact should be an Aurora PostgreSQL activation
planning packet. It must be reviewed before active connector implementation is
scoped.

The packet should include:

- registry profile draft for an Aurora PostgreSQL planned source record
- flavor-specific runtime readiness plan for endpoint posture, TLS posture,
  engine version, timeout behavior, cancellation behavior, source-unavailable
  classification, and retry boundaries
- backend-owned secret indirection plan using the approved PostgreSQL-family
  secret reference pattern without exposing secret values
- connector-profile and dialect-profile version plan showing exactly what is
  inherited from PostgreSQL and what is Aurora-specific
- fixture manifest covering allow, deny, malformed, metadata-only,
  schema-bound, runtime-unavailable, audit reconstruction, release-gate
  reconstruction, and operator-history scenarios
- release-gate reconstruction plan that proves the Aurora flavor from
  SafeQuery-owned evaluation outcomes and source-aware audit events
- operator-history checklist that records how planned metadata, activation
  candidate review, and active-baseline approval will remain distinguishable
