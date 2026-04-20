# ADR-0003: SQL Server Driver Strategy

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- choose a stable first delivery path
- avoid delaying safety architecture work for driver evaluation
- preserve room for later driver reassessment

## Supersedes

None

## Related Docs

- [../requirements/technology-stack.md](../requirements/technology-stack.md)
- [../design/runtime-flow.md](../design/runtime-flow.md)

## Context

SafeQuery must execute approved read-only queries against Microsoft SQL Server from a Python backend.

The project needs a stable initial driver path for delivery, while still leaving room to evaluate newer options later.

## Decision

The initial SQL Server driver for SafeQuery is `pyodbc`.

`mssql-python` is treated as a future evaluation track and not as the primary implementation path for the first PoC.

## Consequences

Positive outcomes:

- chooses a mature and familiar initial delivery path
- reduces early uncertainty in the execution layer
- keeps the first phase focused on application safety and architecture

Tradeoffs:

- the project may revisit the driver choice later
- a future migration evaluation may add adapter or testing work

## Rejected Alternatives

- delaying the initial implementation until a newer driver strategy is finalized
- presenting `mssql-python` as the current default before evaluation is complete
- tightly coupling execution behavior to a driver-specific abstraction that is hard to replace
