# ADR-0014: UI Implementation Stack and OSS Adoption Boundaries

## Status

Accepted

## Date

2026-04-21

## Owner

SafeQuery product and frontend architecture

## Decision Drivers

- improve usability by borrowing proven interaction patterns without surrendering the SafeQuery shell to an external product model
- keep the frontend aligned with FastAPI as the only trusted execution backend
- avoid monolithic chat UI adoption that would blur workflow, source, and preview semantics

## Supersedes

None

## Related Docs

- [../requirements/technology-stack.md](../requirements/technology-stack.md)
- [../design/operator-workflow-information-architecture.md](../design/operator-workflow-information-architecture.md)
- [../../DESIGN.md](../../DESIGN.md)
- [./ADR-0013-operator-workflow-and-ui-foundation.md](./ADR-0013-operator-workflow-and-ui-foundation.md)

## Context

SafeQuery needs a modern operator UI. Generic chat products and low-code shells offer useful interaction ideas, but they also carry assumptions that conflict with SafeQuery:

- transcript-first navigation
- assistant-centric framing
- hidden source identity
- backend shortcuts that bypass the trusted execution path

## Decision

SafeQuery will keep a custom Next.js UI as the primary product shell.

The project may selectively adopt open-source UI primitives and ergonomic patterns when they support the SafeQuery workflow contract, especially for:

- layout primitives
- message-composer ergonomics adapted into a governed request composer
- history navigation patterns
- accessible dialog, drawer, and panel components

The project will not adopt a monolithic chat UI or low-code shell as the SafeQuery product surface if doing so would:

- weaken preview-before-execute
- obscure source identity
- bypass FastAPI as the trusted backend
- make request, candidate, and run history indistinguishable

Open-source UI building blocks are permitted. SafeQuery's operator shell, API contract, and governance semantics remain application-owned.

## Consequences

Positive outcomes:

- the team can reuse mature UI building blocks without inheriting the wrong product model
- SafeQuery keeps a stable workflow-first shell while still improving ergonomics
- backend trust boundaries remain intact

Tradeoffs:

- more integration work remains on the application team
- borrowed patterns must be adapted carefully rather than copied wholesale

## Rejected Alternatives

- adopting a full chat product shell as the SafeQuery primary UI
- using a low-code admin surface as the main operator workflow
- letting frontend convenience features redefine the core request, preview, or execution model
