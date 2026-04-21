# ADR-0013: Operator Workflow and UI Foundation

## Status

Accepted

## Date

2026-04-21

## Owner

SafeQuery product and architecture

## Decision Drivers

- the Epic A shell is useful as a state demo but not strong enough as the product-facing operator workflow
- SafeQuery needs an operator-first shell that reinforces trust, source identity, preview, guard review, and results inspection
- the product must avoid drifting into a generic chat transcript that hides control boundaries

## Supersedes

None

## Related Docs

- [../design/operator-workflow-information-architecture.md](../design/operator-workflow-information-architecture.md)
- [../../DESIGN.md](../../DESIGN.md)
- [./ADR-0006-query-approval-and-execution-integrity.md](./ADR-0006-query-approval-and-execution-integrity.md)

## Context

The repository currently contains an Epic A shell that demonstrates high-level states and backend posture. That shell should not be mistaken for the long-term product information architecture.

SafeQuery requires a workflow-first operator UI that keeps the governed request path visible:

- request composition
- source identity
- SQL preview
- guard outcome
- result inspection

## Decision

SafeQuery will treat the product shell as an operator workflow, not a generic chat experience.

The UI foundation must preserve these invariants:

- the core shell remains application-owned
- the shell makes source identity visible before and after preview
- previewed SQL remains visibly separate from results
- guard posture remains visible and cannot be hidden behind chat-like transcript flow
- history behaves as navigation memory for requests, candidates, and runs rather than as a message log

The Epic A shell remains a developer-facing state demo until the operator workflow contract is fully implemented.

The normative workflow and screen contract lives in:

- `docs/design/operator-workflow-information-architecture.md`
- `DESIGN.md`

## Consequences

Positive outcomes:

- the product UI stays aligned with SafeQuery's trusted control posture
- future contributors have a stable workflow contract instead of inferring behavior from a demo shell
- source-aware UX can be added without making execution semantics ambiguous

Tradeoffs:

- more UI planning is required before deep feature integration
- chat-product ergonomics can be borrowed selectively, but the product shell cannot simply become a chat clone

## Rejected Alternatives

- treating the Epic A shell as the production information architecture
- collapsing the operator workflow into a transcript-first chat layout
- moving preview, guard, or source identity into optional secondary surfaces by default
