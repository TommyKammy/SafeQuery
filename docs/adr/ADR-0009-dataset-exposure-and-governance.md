# ADR-0009: Dataset Exposure and Governance

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- keep pilot data exposure narrow and reviewable
- prevent accidental inclusion of sensitive tables or columns
- make schema changes visible before they affect generation or execution

## Supersedes

None

## Related Docs

- [../requirements/requirements-baseline.md](../requirements/requirements-baseline.md)
- [ADR-0007-adapter-isolation-and-schema-context-supply.md](./ADR-0007-adapter-isolation-and-schema-context-supply.md)
- [../design/sql-guard-spec.md](../design/sql-guard-spec.md)

## Context

SafeQuery relies on an allow-listed dataset, but the pilot needs more explicit governance rules for what enters that allow-list and how schema drift is handled.

SafeQuery may also expose governed retrieval and analyst-style capabilities over semantic assets such as glossary definitions, metric descriptions, curated examples, and playbooks. Those assets need the same operational discipline as the SQL-facing dataset contract.

## Decision

The pilot exposure model is application-owned and based on approved dataset contracts.

Baseline rules:

- prefer approved views over direct base-table exposure
- expose only approved columns
- exclude or mask sensitive columns before they enter the allow-list
- version the schema snapshot used for generation and guard decisions
- detect schema drift and require review before updating the allow-list
- assign a data owner to approve exposure scope
- assign a security reviewer to approve masking and sensitive-data posture
- assign an application maintainer to apply approved contract changes in code and config
- record exception approvals and expiration when temporary deviations are allowed

Retrieval corpus governance follows the same application-owned model.

Baseline retrieval rules:

- approve retrieval asset classes before indexing them
- assign an asset owner for each retrieval asset class or collection
- assign a security reviewer to approve indexing posture, citation visibility, and sensitive-content exclusion
- assign an application maintainer to apply approved indexing, invalidation, and authorization-scope changes
- version retrieval corpus snapshots and explanation templates used by analyst-style responses
- invalidate retrieval assets when source truth changes, ownership changes, or security review is withdrawn
- restrict retrieval visibility according to application roles and approved scope rather than search-engine defaults
- record exceptions, temporary approvals, and expiration timestamps for non-standard retrieval exposure

The default pilot posture is one shared dataset contract for all pilot users. Role-scoped contracts require explicit documentation and approval before implementation.

## Consequences

Positive outcomes:

- keeps data exposure narrow and understandable
- reduces the chance of leaking sensitive fields through generation or execution
- improves repeatability of guard and evaluation behavior
- extends reviewable governance to retrieval and analyst knowledge surfaces

Tradeoffs:

- requires an explicit governance workflow
- increases operational work when schemas evolve
- adds review overhead for retrieval assets and explanation templates

## Rejected Alternatives

- unrestricted schema exposure in the pilot
- trusting engine prompts alone to avoid sensitive objects
- silently updating allow-lists when source schemas drift
