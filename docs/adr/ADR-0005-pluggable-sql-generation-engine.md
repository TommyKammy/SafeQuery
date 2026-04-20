# ADR-0005: Pluggable SQL Generation Engine

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- preserve long-term engine replaceability
- prevent engine features from becoming shadow control-plane dependencies
- allow practical first delivery with a Vanna-based adapter

## Supersedes

None

## Related Docs

- [../requirements/requirements-baseline.md](../requirements/requirements-baseline.md)
- [ADR-0007-adapter-isolation-and-schema-context-supply.md](./ADR-0007-adapter-isolation-and-schema-context-supply.md)
- [../design/system-context.md](../design/system-context.md)

## Context

SafeQuery needs NL2SQL generation, but the generation component must not own the trusted control boundary.

The team wants to start with a practical implementation using a Vanna-based adapter and a local LLM runtime without making Vanna an unreplaceable core dependency.

## Decision

SafeQuery will isolate SQL generation behind an internal adapter interface.

The initial adapter will be Vanna-based, but the application will retain ownership of:

- authentication and authorization
- dataset exposure policy
- SQL Guard
- execution approval
- SQL execution control
- audit logging
- evaluation assets

Vanna-specific UI, filtering, authorization, and audit behavior are not part of the core architecture baseline.

## Consequences

Positive outcomes:

- enables practical initial delivery
- preserves long-term engine replaceability
- prevents accidental trust-boundary drift into engine-specific features

Tradeoffs:

- requires a clear internal contract for generation requests and results
- may add some adapter code compared with direct engine embedding

## Rejected Alternatives

- treating Vanna as the authoritative control plane
- depending on engine-owned UI as the product surface
- coupling audits, policy, or authorization to a single SQL generation engine
