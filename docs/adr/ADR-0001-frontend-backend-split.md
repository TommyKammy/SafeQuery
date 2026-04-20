# ADR-0001: Frontend and Backend Split

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- keep trusted control logic outside the browser
- maintain a clear application-owned control plane
- allow the UI to evolve without weakening safety or execution controls

## Supersedes

None

## Related Docs

- [../requirements/requirements-baseline.md](../requirements/requirements-baseline.md)
- [ADR-0008-session-and-authorization-model.md](./ADR-0008-session-and-authorization-model.md)
- [../design/container-view.md](../design/container-view.md)

## Context

SafeQuery is a controlled enterprise NL2SQL application with a custom web UI, explicit review-before-execute behavior, application-owned safety controls, and application-owned audit logging.

The system must keep the trusted control boundary in the application rather than in the SQL generation engine.

## Decision

SafeQuery will use:

- a Next.js and TypeScript frontend for user interaction
- a FastAPI backend for trusted orchestration and control-plane logic

The frontend is responsible for presenting:

- authentication entry and session-aware UX
- natural language request input
- SQL preview
- guard results
- execution confirmation
- result rendering

The backend is responsible for:

- session-aware API behavior
- authorization context
- orchestration of SQL generation
- SQL Guard enforcement
- execution control
- audit persistence

For the first SafeQuery baseline, FastAPI is the sole trusted backend for execution-sensitive decisions. Next.js is the application UI layer and must not expose an alternate raw execution path.

## Consequences

Positive outcomes:

- keeps trusted control logic off the client
- preserves a clear application-owned control plane
- allows UI evolution without changing guard or execution logic
- aligns cleanly with a replaceable SQL generation adapter model

Tradeoffs:

- requires well-defined frontend-backend contracts
- adds cross-layer API design work
- keeps more state transition logic on the server side

## Rejected Alternatives

- embedding control logic directly into engine-specific UI
- collapsing the product into a thin wrapper around a third-party NL2SQL interface
- moving validation or execution authority into the browser
