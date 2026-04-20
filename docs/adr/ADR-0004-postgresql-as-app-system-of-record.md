# ADR-0004: PostgreSQL as the Application System of Record

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- keep application-owned records separate from business data execution
- preserve durable auditability and evaluation storage
- avoid dependence on engine-owned logs

## Supersedes

None

## Related Docs

- [../requirements/technology-stack.md](../requirements/technology-stack.md)
- [../design/audit-event-model.md](../design/audit-event-model.md)

## Context

SafeQuery requires durable application-owned storage for:

- audit logs
- evaluation assets
- internal metadata
- future control-plane persistence

These records must remain under application control and must not depend on either the SQL generation engine or the target business data source.

## Decision

SafeQuery will use PostgreSQL as the system of record for application-owned persistence.

SQLAlchemy 2.x and Alembic will manage the application persistence layer and schema evolution.

Microsoft SQL Server remains the target business data source for approved read-only query execution and is not repurposed as the application control-plane store.

## Consequences

Positive outcomes:

- clean separation between business data access and application-owned records
- durable foundation for audits and evaluations
- good fit for future admin, governance, and reporting features

Tradeoffs:

- adds an additional datastore to operate
- requires schema management and migration discipline

## Rejected Alternatives

- storing authoritative audits inside the SQL generation engine
- using SQL Server business tables as the application metadata store
- relying only on local files for durable application state
