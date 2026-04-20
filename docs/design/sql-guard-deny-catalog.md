# SQL Guard and Execution Deny Catalog

## Purpose

This document defines the baseline machine-readable deny code catalog for SafeQuery SQL Guard and execute-time policy enforcement.

## Code Families

### Statement shape

- `DENY_PARSE_FAILURE`: parser or AST construction failed, so the guard cannot safely reason about the SQL
- `DENY_UNSUPPORTED_SQL_SYNTAX`: syntax is syntactically present but outside the supported safe-analysis envelope
- `DENY_MULTI_STATEMENT`: more than one statement detected
- `DENY_WRITE_OPERATION`: DML or DDL detected
- `DENY_PROCEDURE_EXECUTION`: stored procedure or equivalent execution detected
- `DENY_DYNAMIC_SQL`: dynamic SQL execution detected

### Object and scope control

- `DENY_OBJECT_NOT_ALLOWLISTED`: referenced object is outside the approved dataset contract
- `DENY_AMBIGUOUS_OBJECT_RESOLUTION`: object resolution is ambiguous after canonicalization
- `DENY_CROSS_DATABASE`: cross-database reference detected
- `DENY_LINKED_SERVER`: linked-server or remote-server reference detected
- `DENY_EXTERNAL_DATA_ACCESS`: `OPENQUERY`, `OPENROWSET`, `OPENDATASOURCE`, or equivalent external access detected
- `DENY_SYSTEM_CATALOG_ACCESS`: system catalog access outside approved policy detected

### Function and feature control

- `DENY_UNAPPROVED_FUNCTION`: unapproved UDF, TVF, or function family detected
- `DENY_DISALLOWED_HINT`: disallowed query hint detected
- `DENY_TEMP_OBJECT`: temporary object creation or mutation detected
- `DENY_RESOURCE_ABUSE`: constructs such as `WAITFOR` or similar abuse patterns detected

### Execution and policy control

- `DENY_APPROVAL_EXPIRED`: candidate approval expired before execution claim
- `DENY_RESULT_BOUND_UNENFORCEABLE`: required row, byte, or timeout bounds cannot be enforced
- `DENY_POLICY_VERSION_STALE`: candidate policy inputs are stale against current policy
- `DENY_CANDIDATE_INVALIDATED`: candidate was invalidated before execution
- `DENY_CANDIDATE_REPLAY`: replay or max-execution-count policy violation detected
- `DENY_CANDIDATE_OWNER_MISMATCH`: authenticated subject does not match candidate owner
- `DENY_ENTITLEMENT_CHANGED`: current authorization no longer permits execution

## Usage Notes

- deny outcomes should include one primary deny code and may include supporting detail codes
- audit and evaluation artifacts should reference these codes directly
- new codes should be added intentionally rather than overloaded into existing meanings
