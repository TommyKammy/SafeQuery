# Review LLM Adapter Contract

## Purpose

The Review LLM adapter is a critique-only boundary for structured review of an
operator request or generated answer context. It can summarize intent, identify
the data it used, list metrics, dimensions, filters, assumptions, risks, and
clarifying questions, and return reviewer-facing diagnostics.

The adapter output is not an authorization source. It must not approve SQL,
mint or select a candidate, bypass SQL Guard, approve execution, or replace the
backend-owned preview and execute lifecycle.

## Structured Output

The backend accepts one structured object with these fields:

- `contractVersion`: fixed to `review_llm_adapter_output.v1`
- `status`: one of `ready`, `needs_clarification`, or `blocked`
- `confidence`: one of `low`, `medium`, `high`, or `unknown`
- `intentSummary`: concise reviewer-facing intent summary
- `dataUsed`: context references or reviewed evidence labels
- `metrics`: reviewed metric names
- `dimensions`: reviewed grouping or entity dimensions
- `filters`: reviewed filter constraints
- `assumptions`: assumptions the reviewer should inspect
- `riskFlags`: risks that keep the output advisory
- `clarifyingQuestions`: questions for the operator or reviewer
- `diagnostics`: adapter version, model/provider metadata, prompt version,
  response identifier, and optional raw output excerpt

The contract deliberately has no `canAuthorizeExecution`,
`executionAuthorized`, `approvalStatus`, `queryCandidateId`, or equivalent
execution-authorizing field. If such a field appears anywhere in the adapter
output, the parser rejects the output before it can reach a reviewer surface.

## Status Semantics

`ready` means the critique output is structurally complete enough for reviewer
inspection. It does not mean the candidate is approved or executable.

`needs_clarification` means the adapter found missing or ambiguous inputs and
the caller should ask one or more clarifying questions before relying on the
critique.

`blocked` means the adapter found a critique boundary problem or risk that
requires a real prerequisite outside the Review LLM output.

Low confidence cannot be returned with `ready`; it must be represented as
`needs_clarification` or `blocked`.

## Malformed Output Handling

The parser accepts a JSON object or already-decoded mapping and validates it
against the structured schema. Invalid JSON, non-object JSON, missing required
fields, unsupported statuses, blank strings, unknown fields, and execution
authority fields are rejected as malformed adapter output.

Malformed output must fail closed. The caller may surface a controlled review
diagnostic, but it must not infer readiness, candidate approval, or execution
permission from partial output.

## Boundary Rules

- The Review LLM can critique and summarize; it cannot authorize.
- SQL Guard and backend candidate lifecycle remain the enforcement boundary.
- Preview and execute requests still require backend-owned source, subject,
  candidate, guard, TTL, replay, and entitlement checks.
- Reviewer-facing diagnostics are advisory evidence, not durable lifecycle
  truth.
