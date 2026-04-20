# SQL Guard Deny Corpus

## Purpose

This document defines the baseline deny corpus that SafeQuery must preserve as executable or reviewable safety regression scenarios.

## Minimum Corpus Categories

The baseline corpus must include representative scenarios for:

- parser failure or malformed SQL that cannot be analyzed safely
- unsupported SQL syntax outside the approved parser envelope
- multi-statement attempts
- DML and DDL attempts
- stored procedure execution
- dynamic SQL execution
- cross-database references
- linked-server access
- external data access through `OPENQUERY`, `OPENROWSET`, or `OPENDATASOURCE`
- system catalog overreach
- unapproved function or TVF usage
- disallowed query hints
- temp object creation or mutation
- resource-abuse constructs such as `WAITFOR`
- non-enforceable result-bound scenarios
- expired-candidate execution attempts
- candidate replay or stale-policy execution attempts
- candidate owner mismatch and entitlement-change attempts

## Expected Outcomes

Each deny corpus scenario should define:

- scenario ID
- representative input SQL or generation context
- expected primary deny code
- expected supporting explanation if relevant
- whether the scenario is critical for pilot sign-off

## Pilot Threshold

Critical deny corpus scenarios must pass at 100 percent for pilot entry.

## Relation to Evaluation Harness

The evaluation harness should treat this corpus as a required safety subset rather than as optional examples.
