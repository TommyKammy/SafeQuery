# Dialect Capability Matrix

## Purpose

This matrix records the source-family rollout posture, including the current
2-source pilot baseline and future families, without implying that every listed
family is already implemented.

It is a planning and review aid for connector, guard, and evaluation work.

## Matrix

| Family or Flavor | Generation Profile | Canonicalization Strategy | Guard Profile | Row-Bounding Strategy | Timeout and Cancellation Posture | Connector Profile | Evaluation Expectation | Rollout Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mssql` | SQL Server-focused prompt and schema context | T-SQL canonicalization before guard and preview | T-SQL fail-closed guard profile | bounded canonical SQL before preview | 30s preview, guard, and execute timeout; source-unavailable states are retryable outside the authoritative execution boundary; malformed, denied, or binding-mismatch workflow states are not retried | initial read-only SQL Server connector; backend-owned pool boundary is per registered source with no cross-source or application PostgreSQL reuse | positive and deny corpus required | active baseline |
| `postgresql` | PostgreSQL-focused prompt and schema context | PostgreSQL canonicalization before guard and preview | PostgreSQL fail-closed guard profile | bounded canonical SQL before preview | 30s preview, guard, and execute timeout; source-unavailable states are retryable outside the authoritative execution boundary; malformed, denied, or binding-mismatch workflow states are not retried | business PostgreSQL connector separate from app PostgreSQL; backend-owned pool boundary is per registered source with no cross-source or application PostgreSQL reuse | positive and deny corpus required | active baseline |
| `mysql` | MySQL family profile, backend-selected from source registry only | MySQL-aware single-statement canonicalization with backtick identifier quoting by default | MySQL family fail-closed guard profile | one policy-bounded `LIMIT`; `OFFSET` only with explicit bounded `LIMIT` | connect timeout, statement timeout, and cancellation probe required | planned read-only backend connector profile with secret indirection | positive, deny, row-bounding, timeout, cancellation, and release-gate reconstruction corpus required before activation | planned metadata only |
| `mariadb` | planned MySQL-delta profile, backend-selected from source registry only | MySQL-family baseline plus explicit MariaDB mode and version drift canonicalization | separate MariaDB delta fail-closed guard profile; no silent MySQL guard reuse | one policy-bounded `LIMIT`; `OFFSET` only with explicit bounded `LIMIT` after MariaDB delta review | connect timeout, statement timeout, and cancellation probe required | planned read-only MariaDB backend connector profile with secret indirection | MySQL-overlap scenarios plus MariaDB delta deny, row-bounding, timeout, cancellation, and release-gate reconstruction corpus required before activation | planned metadata only |
| `aurora-postgresql` | inherits PostgreSQL generation posture; registry keeps `source_family=postgresql` and `source_flavor=aurora-postgresql` | inherits PostgreSQL canonicalization and identifier rules | inherits PostgreSQL fail-closed guard and deny corpus | inherits PostgreSQL bounded canonical SQL behavior | connect timeout, statement timeout, and cancellation probe must be reverified for Aurora PostgreSQL | planned Aurora PostgreSQL read-only connector profile with cluster endpoint, engine version, TLS posture, and secret indirection | PostgreSQL suite plus Aurora PostgreSQL flavor, timeout, cancellation, and release-gate reconstruction regressions | planned flavor |
| `aurora-mysql` | inherits planned MySQL generation posture; registry keeps `source_family=mysql` and `source_flavor=aurora-mysql` | inherits MySQL canonicalization and identifier rules | inherits planned MySQL fail-closed guard and deny corpus | inherits one policy-bounded `LIMIT`; `OFFSET` only with explicit bounded `LIMIT` | connect timeout, statement timeout, and cancellation probe must be reverified for Aurora MySQL | planned Aurora MySQL read-only connector profile with cluster endpoint, engine version, TLS posture, and secret indirection | MySQL suite plus Aurora MySQL flavor, timeout, cancellation, and release-gate reconstruction regressions before activation | planned flavor |
| `oracle` | Oracle family profile, backend-selected from source registry only | Oracle-aware single-statement canonicalization with explicit quoted identifier case handling | Oracle family fail-closed guard profile with PL/SQL, database link, package, and session mutation denies | one approved policy-bounded `FETCH FIRST` or `ROWNUM` shape before guard, preview, and execution | connect timeout, statement timeout, and cancellation probe required before activation | long-range read-only Oracle backend connector profile with secret indirection, connect descriptor, service name, wallet reference, and TLS posture | positive, deny, identifier and quoting, row-bounding, timeout, cancellation, and release-gate reconstruction corpus required before activation | long-range planned metadata only |

## Usage Notes

- A family or flavor does not become implementation-ready just because it appears in this matrix.
- Every new family or flavor still requires approval of connector, guard, governance, and evaluation work.
- The matrix complements the target source registry. It does not replace per-source registry records.
- Active MSSQL and PostgreSQL source-unavailable states are limited to
  connection timeout, source unreachable, and transient driver runtime
  unavailable classifications. Policy denial, malformed workflow input, source
  binding mismatch, unsupported binding, and guard denial remain fail-closed
  workflow states and must not be retried as source availability problems.
- Future activation requires explicit positive, safety-deny,
  connector-selection, lifecycle, runtime-control, audit reconstruction,
  release-gate reconstruction, and operator-history coverage before a planned
  entry can become active.
- Release-gate evidence must come from SafeQuery-owned evaluation outcomes and
  source-aware audit events. MLflow exports, search or analyst outputs, and
  adapter traces are supplemental and cannot satisfy authoritative coverage.
- Connector and dialect profile version drift must be represented as a
  fail-closed evaluation comparison case for each family or flavor before
  activation.
- MySQL remains planned until a registry-owned `mysql` source profile, connector
  profile, dialect profile, guard profile, audit contract, and release-gate
  corpus are approved together.
- MySQL execution must not be inferred from adapter hints, client-supplied
  metadata, driver names, connection strings, hostnames, or generated SQL text.
- MariaDB is a distinct planned `source_family=mariadb` MySQL-delta profile. It
  may share MySQL-family expectations only where the backend profile says so;
  connector selection, SQL Guard selection, audit reconstruction, and release
  gates must remain MariaDB-specific until approval.
- Aurora entries are planned flavors. They must be resolved from backend-owned
  source registry metadata as `source_family=postgresql` plus
  `source_flavor=aurora-postgresql`, or `source_family=mysql` plus
  `source_flavor=aurora-mysql`; they must not become top-level families or
  client-supplied adapter hints.
- Oracle is long-range planned metadata only. Oracle support must remain
  inactive until backend-owned source registry records, connector profile,
  dialect profile, guard deny corpus, audit and operator-history mapping,
  entitlement checks, candidate lifecycle revalidation, and release-gate
  reconstruction are approved together.
- Oracle execution must not be inferred from adapter hints, client-supplied
  metadata, analyst artifacts, MLflow traces, driver names, connection
  descriptors, hostnames, labels, or generated SQL text.
