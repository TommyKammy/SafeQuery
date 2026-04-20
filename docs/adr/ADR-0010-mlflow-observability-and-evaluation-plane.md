# ADR-0010: MLflow as Observability and Evaluation Plane

## Status

Accepted

## Date

2026-04-20

## Owner

SafeQuery architecture

## Decision Drivers

- add ML and LLM lifecycle visibility without changing the trusted control plane
- support tracing and evaluation for retrieval and analyst-style features
- keep engineering observability separate from authoritative governance state

## Supersedes

None

## Related Docs

- [../requirements/requirements-baseline.md](../requirements/requirements-baseline.md)
- [../requirements/technology-stack.md](../requirements/technology-stack.md)
- [../design/evaluation-harness.md](../design/evaluation-harness.md)
- [../design/search-and-analyst-capabilities.md](../design/search-and-analyst-capabilities.md)

## Context

SafeQuery is adding richer ML, retrieval, and analyst-style capabilities. Those features benefit from experiment tracking, tracing, evaluation comparison, and model lifecycle tooling.

The system still requires a hard separation between:

- application-owned trust and execution controls
- engineering-facing lifecycle tooling

## Decision

When the MLflow integration feature flag is enabled, SafeQuery will use MLflow as the recommended engineering plane for:

- tracing ML, LLM, retrieval, and analyst-style workflows
- storing and comparing evaluation runs
- tracking prompt, model, and experiment lineage
- optionally registering auxiliary ML models such as rerankers or classifiers

MLflow is not the authoritative system of record for:

- SQL Guard decisions
- candidate lifecycle and execution approval
- authorization state
- authoritative audit retention

PostgreSQL remains the authoritative application audit and persistence store. SafeQuery remains the trusted control plane.

## Export Contract

Default export-allowed data to MLflow:

- trace identifiers and span timing
- application version, adapter version, model version, and prompt version identifiers
- retrieval corpus version and retrieved asset identifiers
- evaluation metrics, deny codes, latency, token counts, row counts, and truncation flags
- experiment metadata for auxiliary models such as rerankers or classifiers

Conditionally allowed data requires an explicit redaction profile approved by the application maintainer and security reviewer:

- redacted natural-language request excerpts
- redacted explanation text samples used for evaluation or debugging
- redacted SQL snippets used only in controlled engineering workflows

Prohibited exports to MLflow:

- raw session cookies, tokens, or credential material
- SQL Server credentials or connection strings
- full query result sets or business-data result fragments
- full retrieved asset bodies from controlled corpora unless separately approved for that corpus
- unredacted natural-language requests, canonical SQL, or identity claims in shared engineering workspaces

Retention and access rules:

- MLflow retention must be equal to or shorter than the authoritative audit retention unless explicitly approved otherwise
- access must be limited to approved engineering and operational roles
- MLflow run identifiers may reference PostgreSQL audit records, but PostgreSQL remains the authoritative source for audit reconstruction and governance review

## Consequences

Positive outcomes:

- stronger observability for ML and LLM workflows
- better regression comparison and release confidence
- cleaner lifecycle management for auxiliary models and prompts

Tradeoffs:

- introduces one more supporting system to operate
- requires clear data-handling and redaction posture for traces
- requires careful distinction between engineering traces and authoritative audits

## Rejected Alternatives

- using MLflow as the authoritative audit or governance system
- embedding lifecycle and experiment state only in ad hoc local files
- making retrieval or analyst tooling depend on vendor-specific opaque platforms by default
