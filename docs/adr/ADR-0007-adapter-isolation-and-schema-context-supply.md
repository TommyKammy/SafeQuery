# ADR-0007: Adapter Isolation and Schema Context Supply

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- prevent shadow trust boundaries in the SQL generation layer
- keep production SQL Server credentials inside the trusted backend
- allow engine replacement without changing governance boundaries

## Supersedes

None

## Related Docs

- [ADR-0005-pluggable-sql-generation-engine.md](./ADR-0005-pluggable-sql-generation-engine.md)
- [ADR-0009-dataset-exposure-and-governance.md](./ADR-0009-dataset-exposure-and-governance.md)
- [../design/system-context.md](../design/system-context.md)

## Context

The SQL generation adapter needs schema and business context to produce useful candidate SQL. If it acquires direct access to production SQL Server or unrestricted schema introspection, it becomes a shadow control plane.

## Decision

The adapter receives only curated application-supplied context, such as:

- approved schema metadata
- allow-listed view and column metadata
- controlled business glossary content
- policy metadata needed for generation quality

The adapter does not receive:

- production SQL Server credentials
- authority to run business queries
- authority to approve or deny execution
- authority to persist authoritative audit events

## Consequences

Positive outcomes:

- keeps the execution boundary inside the trusted backend
- reduces accidental overexposure of business schema
- makes engine substitution easier

Tradeoffs:

- requires an application-owned context preparation path
- may reduce generation quality if context curation is too thin

## Rejected Alternatives

- giving the adapter direct production SQL Server connectivity
- letting the adapter inspect unrestricted schema on demand
- allowing the adapter to own end-to-end query execution
