# ADR-0015: Semantic Contract and SQL Guard Responsibility

## Status

Accepted

## Date

2026-05-17

## Owner

SafeQuery assurance architecture

## Decision Drivers

- separate business-intent authorization from executable SQL safety before adding semantic contracts
- keep SQL Guard authoritative for executable SQL denial even when semantic intent is approved
- prevent governed-answer assurance levels from overstating coverage when semantic mapping is missing
- preserve historical audit reconstruction across forward-only contract versions

## Supersedes

None

## Related Docs

- [../design/sql-guard-spec.md](../design/sql-guard-spec.md)
- [../design/evaluation-harness.md](../design/evaluation-harness.md)
- [../design/runtime-flow.md](../design/runtime-flow.md)
- [../design/query-lifecycle-state-machine.md](../design/query-lifecycle-state-machine.md)
- [../implementation-roadmap.md](../implementation-roadmap.md)

## Context

SafeQuery is adding a Semantic Contract layer for governed answer assurance.
That layer will describe approved business concepts such as metrics,
dimensions, filters, time semantics, and ambiguity rules before SQL generation.

SQL Guard already has a narrower and lower-level responsibility: it evaluates
canonicalized executable SQL before preview and execution become available.
The guard decides whether a candidate statement is structurally safe,
read-only, source-scoped, bounded, and compatible with the configured dialect
and dataset allow-list.

These responsibilities overlap in the operator workflow, but they are not
substitutes. SafeQuery needs both layers because a query can express approved
business intent while producing unsafe SQL, and a syntactically safe SQL
statement can still answer the wrong business question.

## Decision

SafeQuery will use Semantic Contract checks for business-intent authorization
and SQL Guard checks for executable SQL safety. Both layers must pass before an
answer can be treated as governed and execution-eligible.

Semantic Contract responsibilities:

- define the approved business concepts for a source domain
- map user intent to approved metrics, dimensions, filters, and time semantics
- classify unsupported or ambiguous business intent before SQL generation
- provide the semantic evidence needed for Level 2 governed-answer claims
- version the approved business meaning used by preview, candidate, answer, and audit records

SQL Guard responsibilities:

- evaluate canonicalized candidate SQL after generation and before execution
- enforce read-only, single-statement, allow-listed object, row-bound, timeout,
  and dialect-profile safety rules
- deny unsafe executable SQL even when semantic intent was mapped successfully
- produce structured guard outcomes, guard versions, and deny codes for audit reconstruction

The boundary rules are:

- Semantic Contract cannot bypass SQL Guard.
- SQL Guard cannot prove business intent correctness.
- unsupported business intent is blocked by the Semantic Contract layer before
  SQL generation or before Level 2 assurance is claimed
- unsafe executable SQL is blocked by SQL Guard after canonicalization and
  before preview or execution eligibility
- semantic allow plus SQL deny is a valid and expected outcome; the candidate
  remains non-executable and the audit record must preserve both the semantic
  mapping and guard denial
- semantic missing prevents Level 2 claims; an answer with only SQL Guard
  evidence may at most claim the lower assurance level that its observed
  evaluation artifacts support

## Contract Versioning

Semantic contracts use forward-only contract versioning. A new business definition, metric
expression, dimension rule, filter policy, ambiguity rule, or source binding
creates a new contract version instead of mutating the meaning of prior
records.

Preview, candidate, answer, audit, and release-gate records that depend on
semantic mapping must store the semantic contract identity and version that were
active when the record was created. Old answers bind to old contract versions:
old answers bind to old contract versions for audit and release-gate
reconstruction instead of being reinterpreted under a newer business definition.
Historical audit behavior must reconstruct the decision using the stored
contract version rather than reinterpreting old answers under the newest
contract.

If the current contract version is missing, retired, or incompatible with a
historical record, the system must report that reconstruction gap explicitly.
It must not silently upgrade the historical answer or treat a newer contract as
proof that the old answer was semantically correct.

## Assurance Levels

Level 1 SQL safety can be supported by SQL Guard, candidate lifecycle, source
governance, and execution audit evidence.

Level 2 business-intent correctness requires Semantic Contract evidence in
addition to SQL safety evidence. Without semantic mapping to an approved
contract version, the release gate and operator-facing surfaces must not present
Level 2 governed-answer assurance as covered.

Level 3 unsupported-answer behavior depends on both the Semantic Contract layer
and later result/evidence validation work. This ADR only fixes the responsibility
boundary; it does not implement schema, persistence, mapping, or answer
validation services.

## Consequences

Positive outcomes:

- business-intent authorization and SQL safety remain independently auditable
- approved intent cannot authorize unsafe SQL execution
- safe SQL shape cannot be mistaken for correct business meaning
- historical answer review can reconstruct the contract version that governed the answer

Tradeoffs:

- preview and release-gate records need additional semantic evidence fields in later work
- operators may see two different denial families for one request
- version migration requires explicit forward-only contract lifecycle decisions

## Rejected Alternatives

- letting a semantic allow decision make SQL execution eligible without SQL Guard
- treating SQL Guard approval as proof that the answer satisfied the requested business intent
- mutating semantic contract definitions in place and reinterpreting historical answers
- claiming Level 2 governed-answer assurance when semantic contract evidence is absent
