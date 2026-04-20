# ADR-0006: Query Approval and Execution Integrity

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- guarantee that executed SQL is the same SQL that was previewed and guard-approved
- prevent client-side SQL substitution at execution time
- preserve auditable approval semantics

## Supersedes

None

## Related Docs

- [../design/runtime-flow.md](../design/runtime-flow.md)
- [../design/query-lifecycle-state-machine.md](../design/query-lifecycle-state-machine.md)
- [../design/audit-event-model.md](../design/audit-event-model.md)

## Context

SafeQuery requires preview-before-execute behavior. That guarantee is weak unless the system binds previewed SQL to execution through a server-owned identifier and stored canonical representation.

If the execution API accepts raw SQL from the client, a user or compromised frontend path could attempt to execute SQL that was never approved by the guard.

## Decision

The execution API must accept only a server-issued `query_candidate_id`.

Each candidate stores:

- opaque and unguessable `query_candidate_id`
- canonicalized SQL
- SQL hash
- owner subject
- authorization snapshot
- guard decision
- guard version
- schema snapshot version
- approval timestamp
- approval expiration timestamp
- adapter version
- execution count
- max execution count
- invalidated timestamp if invalidated
- invalidation reason if invalidated

The backend executes only the stored canonical SQL associated with an approved, unexpired, non-invalidated candidate.

In the baseline lifecycle, approval becomes effective when:

- SQL Guard returns an allow decision for the canonical SQL
- the backend persists the candidate and its approval metadata

That same point establishes:

- `approval timestamp`
- `approval expiration timestamp`
- the candidate as execution-eligible subject to later owner, entitlement, replay, and invalidation checks

The preview shown to the user is therefore the preview of an already approved candidate rather than a separate pre-approval artifact.

The user-visible button press in Phase 1 is the execution request or confirmation step. It is not the point at which approval metadata is created.

At execute time the backend must re-check:

- current authenticated subject matches candidate owner subject
- current entitlements still satisfy execution policy
- execution count has not exceeded `max_execution_count`

The Phase 1 replay posture is single use with `max_execution_count = 1` unless explicitly changed by a later approved decision.

The Phase 1 SQL-bounding contract is:

- previewed SQL is the executable bounded canonical SQL
- canonicalization and any required row-bounding rewrite happen before guard evaluation
- guard result, SQL hash, preview text, and execute-time SQL all refer to the same canonical SQL
- if row-bounding rewrites are required, they happen before preview and become part of the canonical SQL and hash
- byte and timeout controls are enforced by runtime delivery controls and do not rewrite SQL after approval

Single-use replay protection is enforced through an atomic execution claim. The step that claims the candidate for execution and increments `execution_count` must succeed at most once through a database transaction, conditional update, or equivalent compare-and-swap mechanism.

Policy or entitlement changes such as allow-list updates, schema snapshot changes, guard-version changes, role-mapping changes, or kill-switch activation must invalidate or deny execution of previously approved candidates unless they are revalidated explicitly.

Phase 1 preview is read-only. The frontend must not edit SQL inline and then submit it directly for execution.

If edited SQL is supported later, it must create a new candidate and undergo a fresh guard evaluation.

## Consequences

Positive outcomes:

- prevents raw SQL execute endpoints from appearing by accident
- preserves strong linkage between preview, guard, approval, and execution
- improves auditability and incident review
- constrains replay and leaked-ID risk

Tradeoffs:

- requires candidate persistence before execution
- introduces approval TTL and candidate lifecycle management

## Rejected Alternatives

- accepting raw SQL text in the execute endpoint
- trusting the frontend to submit exactly the previewed SQL
- treating edited preview text as implicitly approved
