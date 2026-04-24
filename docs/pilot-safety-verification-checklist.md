# 2-Source Core Path Pilot-Safety Verification Checklist

## Purpose

This checklist is the pilot-readiness sign-off surface for the completed
2-source core path after G-1 through G-5. It verifies that SafeQuery can run the
MSSQL vertical slice and the business PostgreSQL vertical slice through the same
trusted control path without weakening source binding, candidate lifecycle,
audit, or release-gate behavior.

Use this checklist before optional extension tracks begin.

## Scope and Non-Requirements

In scope:

- MSSQL source path using `business-mssql-source`
- business PostgreSQL source path using `business-postgres-source`
- auth context and entitlement checks at the trusted backend boundary
- explicit source selection before generation
- source-aware generation context preparation
- dialect-specific guard evaluation
- read-only SQL preview bound to the generated candidate
- candidate-only execute using `query_candidate_id`, not raw SQL text
- audit fields for source, candidate, guard, and execution outcomes
- evaluation coverage and source-aware release gate reconstruction
- runtime controls for cancellation, row limits, kill switches, rate limits, and
  replay prevention
- operator workflow checks that keep request, source, candidate, guard, and run
  anchors visible

Out of scope for core completion:

- optional search, analyst, and MLflow extension tracks are not required for
  the 2-source core path completion checklist
- if optional search, analyst, or MLflow behavior is enabled for a deployment,
  verify it under its own extension-track governance, audit, and evaluation
  criteria

## Focused Sign-Off Commands

Run these focused checks from the repository root unless a command changes into
`backend`.

```bash
bash tests/smoke/test-pilot-safety-checklist.sh
bash tests/smoke/test-local-topology-roles.sh
cd backend
python3 -m pytest \
  tests/test_request_source_selection.py \
  tests/test_source_entitlements.py \
  tests/test_generation_context_preparation.py \
  tests/test_sql_generation_adapter_request.py \
  tests/test_adapter_single_source_validation.py \
  tests/test_preview_source_governance_resolution.py \
  tests/test_candidate_source_metadata.py \
  tests/test_candidate_lifecycle_revalidation.py \
  tests/test_source_bound_execute_path.py \
  tests/test_execution_connector_selection.py \
  tests/test_execution_runtime_controls.py \
  tests/test_mssql_execution_connector.py \
  tests/test_postgresql_execution_connector.py \
  tests/test_sql_guard_mssql_profile.py \
  tests/test_sql_guard_postgresql_profile.py \
  tests/test_audit_event_model.py \
  tests/test_evaluation_harness.py \
  tests/test_release_gate.py
```

Inspection points:

- `README.md` local startup section still names application PostgreSQL,
  business PostgreSQL, and business MSSQL as separate roles.
- `infra/docker-compose.yml` still declares separate `app-postgres`,
  `business-postgres-source`, and `business-mssql-source` services.
- `docs/design/dialect-capability-matrix.md` still marks `mssql` as active
  baseline and `postgresql` as an approved follow-on source family with a
  required positive and deny corpus.
- `docs/design/evaluation-harness.md` still requires 100 percent critical deny
  corpus pass rate and release blocking for unresolved threshold misses.
- `backend/tests/test_release_gate.py` still proves source-aware release gate
  failures for missing evaluation coverage, missing audit coverage, stale audit
  coverage, malformed artifacts, and safety regressions.
- `backend/tests/test_source_bound_execute_path.py`,
  `backend/tests/test_execution_runtime_controls.py`,
  `backend/tests/test_mssql_execution_connector.py`, and
  `backend/tests/test_postgresql_execution_connector.py` still cover
  candidate-only execution, runtime controls, and both connector paths.

## Source-Aware Checklist

### Auth

- Confirm authenticated subject context is present before source selection,
  preview, approval, or execution.
- Confirm entitlement checks are source-specific for both MSSQL and business
  PostgreSQL.
- Confirm missing, malformed, placeholder, or mismatched auth context blocks
  before generation or execution.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_source_entitlements.py`.

### Explicit Source Selection

- Confirm every request selects exactly one authoritative source record.
- Confirm MSSQL requests bind to `business-mssql-source`.
- Confirm business PostgreSQL requests bind to `business-postgres-source`.
- Confirm application PostgreSQL is not selectable as a business source.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_request_source_selection.py`.

### Generation

- Confirm generation requests include the selected source identity, source
  family, source flavor, schema snapshot version, dataset contract version, and
  dialect profile version.
- Confirm generation context is assembled only from the selected source.
- Confirm adapter requests fail closed when source binding is missing,
  ambiguous, unsupported, or cross-source.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_generation_context_preparation.py tests/test_sql_generation_adapter_request.py tests/test_adapter_single_source_validation.py`.

### Guard

- Confirm MSSQL candidates use the MSSQL guard profile and business PostgreSQL
  candidates use the PostgreSQL guard profile.
- Confirm parser failures, unsupported syntax, write operations, multi-statement
  attempts, stale policy inputs, and dialect mismatches fail closed.
- Confirm deny decisions retain source identity and expected deny codes for
  later audit and release-gate reconstruction.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_sql_guard_mssql_profile.py tests/test_sql_guard_postgresql_profile.py tests/test_sql_guard_common_contract.py`.

### Preview

- Confirm preview surfaces are read-only candidate views, not editable execute
  input.
- Confirm preview metadata includes request identity, candidate identity, SQL
  hash or equivalent review anchor, source identity, guard posture, and
  generated timestamp.
- Confirm preview resolution rejects missing source governance, mixed source
  snapshots, and unsupported source binding.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_preview_source_governance_resolution.py tests/test_candidate_source_metadata.py`.

### Candidate-Only Execute

- Confirm execution accepts only a stored candidate identifier and never accepts
  raw SQL text as the execute boundary.
- Confirm candidate source identity matches the selected connector and runtime
  controls.
- Confirm stale candidates, expired approval, replay attempts, invalidated
  candidates, owner mismatch, source mismatch, and policy-version drift deny
  before connector dispatch.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_source_bound_execute_path.py tests/test_candidate_lifecycle_revalidation.py`.

### Audit

- Confirm audit events include source id, source family, source flavor, dialect
  profile version, dataset contract version, schema snapshot version, execution
  policy version, connector profile version, request id, candidate id or
  equivalent candidate anchor, user subject, and primary deny code where
  relevant.
- Confirm denied paths are audited with the same source-aware fields as allowed
  paths.
- Confirm evaluation results are not treated as a replacement for application
  audit.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_audit_event_model.py tests/test_release_gate.py`.

### Evaluation

- Confirm the evaluation harness covers positive and deny scenarios for MSSQL
  and business PostgreSQL.
- Confirm critical deny corpus regressions block pilot readiness.
- Confirm source metadata appears in observed evaluation artifacts.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_evaluation_harness.py tests/test_release_gate.py`.

## Fail-Closed Negative Checks

- cross-source execution: a candidate generated, previewed, or approved for one
  source must not execute against another source or connector.
- application PostgreSQL reuse: `SAFEQUERY_APP_POSTGRES_URL` and the
  `app-postgres` service must remain application-owned persistence and must not
  become a business-source credential or selectable target.
- stale candidates: expired approval, stale policy version, stale schema
  snapshot, stale dataset contract, invalidation, or replay must deny before
  connector dispatch.
- owner mismatch: execution must deny when the authenticated subject does not
  match candidate ownership or the current entitlement snapshot no longer
  authorizes the source.
- unsupported source binding: missing source id, unsupported source family,
  unsupported source flavor, missing connector profile, missing guard profile,
  or ambiguous binding must block before generation, preview, or execution.
- missing audit coverage: release-gate reconstruction must fail closed when any
  required source-aware evaluation scenario lacks matching source-aware audit
  coverage.

Focused verification:

```bash
cd backend
python3 -m pytest \
  tests/test_application_postgres_guard.py \
  tests/test_adapter_credential_isolation.py \
  tests/test_adapter_single_source_validation.py \
  tests/test_execution_connector_selection.py \
  tests/test_execution_runtime_controls.py \
  tests/test_source_bound_records.py \
  tests/test_source_bound_execute_path.py \
  tests/test_release_gate.py
```

## Release Gate and Runtime Controls

Release sign-off requires a `pass` status from source-aware release gate
reconstruction. The current release gate behavior is source-aware and must stay
fail-closed for:

- missing evaluation coverage
- missing audit coverage
- stale audit coverage
- missing source-aware audit fields
- malformed evaluation artifacts
- safety scenario regressions

Runtime controls must be verified before pilot entry:

- source kill switch denies before runner dispatch
- source-specific rate limit denies before runner dispatch
- timeout and cancellation controls are passed to the selected runner
- row limits are capped by source-bound runtime controls
- pre-cancelled execution denies without connector dispatch
- connector selection is derived from the authoritative candidate source, not
  from client-supplied source hints

Focused verification:

```bash
cd backend
python3 -m pytest \
  tests/test_execution_runtime_controls.py \
  tests/test_execution_connector_selection.py \
  tests/test_mssql_execution_connector.py \
  tests/test_postgresql_execution_connector.py \
  tests/test_release_gate.py
```

## Operator Sign-Off Workflow

For each of MSSQL and business PostgreSQL, inspect or exercise one positive
scenario and one fail-closed scenario through the operator workflow contract:

1. Select or confirm exactly one source while the request is still an active
   draft.
2. Submit the natural-language request only after trusted auth context and
   source posture are present.
3. Confirm generation produces a candidate bound to the selected source.
4. Confirm preview displays the candidate as read-only SQL with source,
   candidate, guard, and review anchors visible.
5. Confirm guard status is source-specific and fail-closed when prerequisite
   signals are missing or stale.
6. Execute only through the candidate identifier after approval.
7. Confirm result or denial surfaces keep request, source, candidate, run, and
   audit anchors visible.
8. Confirm history reopen preserves old source lineage and creates a new draft
   instead of mutating an old candidate or run.

Manual sign-off should record:

- command output for the focused sign-off commands
- inspected source records and connector profile names
- inspected positive and negative scenario ids
- release gate status and failure list, if any
- any skipped check with the explicit prerequisite that prevented it

Do not sign off pilot readiness by inferring success from naming conventions,
client-supplied source hints, optional extension traces, or operator-facing
summary text alone. Use the authoritative source, candidate, audit, and release
gate records.
