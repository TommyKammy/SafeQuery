# ADR-0008: Session and Authorization Model

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- keep trusted authorization logic in one backend control plane
- make state-changing actions safe against CSRF and confused-deputy risks
- define a default-deny pilot posture

## Supersedes

None

## Related Docs

- [ADR-0001-frontend-backend-split.md](./ADR-0001-frontend-backend-split.md)
- [ADR-0002-auth-bridge-with-saml-2-0.md](./ADR-0002-auth-bridge-with-saml-2-0.md)
- [../design/runtime-flow.md](../design/runtime-flow.md)

## Context

The system already chose a Next.js frontend and FastAPI backend, but that split alone does not define the trusted session and authorization model.

Because Next.js can act as a backend-for-frontend, the project must state clearly where trusted policy enforcement lives.

## Decision

FastAPI is the authoritative trusted backend for:

- session validation
- state-changing authorization checks
- CSRF validation
- claim-to-role mapping
- execution entitlement checks
- candidate ownership checks

The baseline session posture is:

- authenticated browser session using secure application-managed cookies
- CSRF protection for state-changing browser requests
- default-deny role mapping when required claims or app-role mappings are missing
- authorization snapshot capture at approval time plus current-entitlement revalidation at execution time

Next.js is the UI layer and may call FastAPI, but it is not the authoritative policy engine for execution-sensitive behavior.

If role mapping or execution entitlement changes after approval, the backend must deny or invalidate stale candidates rather than allowing prior approvals to bypass current policy.

## Consequences

Positive outcomes:

- keeps trusted enforcement logic in one place
- reduces ambiguity about where execution-sensitive checks belong
- supports browser-based UX without weakening session safety

Tradeoffs:

- requires clear frontend-backend boundary contracts
- requires explicit session and CSRF handling during implementation

## Rejected Alternatives

- making Next.js a second trusted execution backend
- relying only on bridge-issued identity without application session controls
- fail-open claim mapping when authorization context is incomplete
