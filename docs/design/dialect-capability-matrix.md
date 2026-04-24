# Dialect Capability Matrix

## Purpose

This matrix records the source-family rollout posture, including the current
2-source pilot baseline and future families, without implying that every listed
family is already implemented.

It is a planning and review aid for connector, guard, and evaluation work.

## Matrix

| Family or Flavor | Generation Profile | Canonicalization Strategy | Guard Profile | Row-Bounding Strategy | Timeout and Cancellation Posture | Connector Profile | Evaluation Expectation | Rollout Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `mssql` | SQL Server-focused prompt and schema context | T-SQL canonicalization before guard and preview | T-SQL fail-closed guard profile | bounded canonical SQL before preview | timeout and cancellation required | initial read-only SQL Server connector | positive and deny corpus required | active baseline |
| `postgresql` | PostgreSQL-focused prompt and schema context | PostgreSQL canonicalization before guard and preview | PostgreSQL fail-closed guard profile | bounded canonical SQL before preview | timeout and cancellation required | business PostgreSQL connector separate from app PostgreSQL | positive and deny corpus required | active baseline |
| `mysql` | MySQL family profile, backend-selected from source registry only | MySQL-aware single-statement canonicalization with backtick identifier quoting by default | MySQL family fail-closed guard profile | one policy-bounded `LIMIT`; `OFFSET` only with explicit bounded `LIMIT` | connect timeout, statement timeout, and cancellation probe required | planned read-only backend connector profile with secret indirection | positive, deny, row-bounding, timeout, cancellation, and release-gate reconstruction corpus required before activation | planned metadata only |
| `mariadb` | MariaDB delta or sibling profile to MySQL | profile-specific canonicalization | MariaDB guard profile | to be defined by profile approval | to be defined by profile approval | future connector profile | future onboarding corpus required | planned after MySQL |
| `aurora-postgresql` | inherits PostgreSQL generation posture with flavor overrides | PostgreSQL family canonicalization plus flavor notes | PostgreSQL family guard profile with flavor notes | follows PostgreSQL family unless overridden | follows PostgreSQL family unless overridden | Aurora flavor connector profile | PostgreSQL suite plus flavor regressions | planned flavor |
| `aurora-mysql` | inherits MySQL family generation posture with flavor overrides | MySQL family canonicalization plus flavor notes | MySQL family guard profile with flavor notes | follows MySQL family unless overridden | follows MySQL family unless overridden | Aurora flavor connector profile | MySQL suite plus flavor regressions | planned flavor |
| `oracle` | Oracle-focused generation profile | Oracle-specific canonicalization | Oracle fail-closed guard profile | to be defined by profile approval | to be defined by profile approval | future connector profile | future onboarding corpus required | long-range planned |

## Usage Notes

- A family or flavor does not become implementation-ready just because it appears in this matrix.
- Every new family or flavor still requires approval of connector, guard, governance, and evaluation work.
- The matrix complements the target source registry. It does not replace per-source registry records.
- MySQL remains planned until a registry-owned `mysql` source profile, connector
  profile, dialect profile, guard profile, audit contract, and release-gate
  corpus are approved together.
- MySQL execution must not be inferred from adapter hints, client-supplied
  metadata, driver names, connection strings, hostnames, or generated SQL text.
