# SQL Guard Specification

## Purpose

This document defines the baseline SafeQuery SQL Guard behavior for the first pilot.

The goal is not merely to detect obviously unsafe SQL. The goal is to define an application-owned validation contract that protects the execution path from unauthorized scope, excessive resource use, and T-SQL-specific bypass patterns.

## Guard Scope

SQL Guard runs after candidate SQL generation and before any approval or execution path becomes available.

Canonicalization and any required row-bounding rewrite happen before SQL Guard runs.

The guard evaluates canonicalized candidate SQL and produces a structured allow or deny decision.

## Validation Model

The baseline validation posture is parser-oriented rather than string-matching only.

The guard should:

- parse the candidate into a structured representation
- reason over referenced objects after canonicalization
- validate fully-qualified object references against the allow-list
- apply deny rules for unsupported or unsafe T-SQL features

If parsing, AST construction, or equivalent structured analysis fails, the guard must fail closed and deny the candidate rather than falling back to permissive string-based execution logic.

## Execution Bounding Contract

The Phase 1 contract is:

- previewed SQL is the executable bounded canonical SQL
- if row-bounding rewrites are needed, they are applied before preview and become part of the canonical SQL and SQL hash
- byte and timeout bounds are enforced by runtime delivery controls without mutating SQL after approval

This contract preserves preview-to-execute integrity while still allowing runtime delivery safety controls.

## Baseline Allow Conditions

The candidate may proceed only if all of the following are true:

- the statement is read-only
- the statement contains exactly one allowed query statement
- all referenced objects resolve to the allow-listed dataset contract
- execution limits can be enforced for the request
- the statement does not rely on denied T-SQL constructs

## Baseline Deny Conditions

The guard denies execution if any of the following are present:

- parse failure or AST construction failure
- unsupported SQL syntax that cannot be safely reasoned over by the configured parser path
- multiple statements
- DDL or DML
- stored procedure execution
- dynamic SQL execution
- synonym resolution to non-allow-listed objects
- unapproved scalar functions, table-valued functions, or user-defined functions
- temporary table creation or mutation
- cross-database references
- linked-server references
- `OPENQUERY`, `OPENROWSET`, or `OPENDATASOURCE`
- access to system catalogs outside the approved policy
- `WAITFOR` or similar resource-abuse constructs
- disallowed query hints
- statements that would bypass configured row, byte, or timeout controls

## Object Resolution Rules

- object checks should prefer fully-qualified resolution
- views and tables must be validated against the application-owned allow-list
- if schema resolution is ambiguous, deny rather than infer
- schema snapshot version should be recorded with the guard result

## Result Control Rules

The baseline execution path must enforce:

- max rows returned
- max bytes returned
- maximum execution time
- cancellation support for long-running requests

If the system cannot guarantee these controls for a request, the guard should deny execution.

## Explainability

The guard result should be structured and auditable, including:

- allow or deny outcome
- machine-readable denial codes
- human-readable summary
- guard version
- schema snapshot version

The denial-code source of truth lives in [sql-guard-deny-catalog.md](./sql-guard-deny-catalog.md).

## Deny Corpus Requirement

The guard must be backed by a representative deny corpus that exercises the baseline denial categories. The required baseline corpus is described in [sql-guard-deny-corpus.md](./sql-guard-deny-corpus.md).

## Open Follow-Ups

Later iterations may refine:

- exact parser and AST library choice
- policy expression language for dataset contracts
- more granular hint and function policies
- parameterization and query template normalization
