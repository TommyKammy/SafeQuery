# ADR-0002: Enterprise Authentication via SAML Bridge

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- support enterprise authentication requirements
- avoid pulling raw SAML protocol complexity into the core app
- keep product authorization under application control

## Supersedes

None

## Related Docs

- [../requirements/requirements-baseline.md](../requirements/requirements-baseline.md)
- [ADR-0008-session-and-authorization-model.md](./ADR-0008-session-and-authorization-model.md)
- [../design/system-context.md](../design/system-context.md)

## Context

SafeQuery must support enterprise authentication with a SAML 2.0-compatible identity provider. At the same time, the application should avoid carrying raw SAML protocol complexity directly in the core application where possible.

The application must still own session handling and authorization decisions.

## Decision

SafeQuery will integrate enterprise authentication using this pattern:

SAML 2.0-compatible identity provider -> SAML bridge -> application

The bridge translates enterprise authentication into a form the application can consume more simply, such as OAuth or OIDC-compatible flows, while the application remains responsible for:

- session establishment
- route protection
- authorization context
- product-specific access control

The bridge is an authentication integration boundary, not a substitute for application-owned session, CSRF, or authorization enforcement.

## Consequences

Positive outcomes:

- reduces direct SAML protocol complexity inside the application core
- preserves compatibility with enterprise identity requirements
- keeps product authorization under application control
- simplifies future application maintenance

Tradeoffs:

- introduces one more integration boundary to configure and monitor
- requires explicit mapping of bridge claims into application authorization context

## Rejected Alternatives

- direct raw SAML handling inside all application layers
- delegating product authorization to the identity provider alone
- allowing direct SQL Server authentication with end-user credentials
