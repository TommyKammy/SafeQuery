# 2-Source Core Path Pilot-Safety Verification Checklist

## Purpose

This checklist is the pilot-readiness sign-off surface for the completed
2-source core path after G-1 through G-5. It verifies that SafeQuery can run the
MSSQL vertical slice and the business PostgreSQL vertical slice through the same
trusted control path without weakening source binding, candidate lifecycle,
audit, or release-gate behavior.

It is also the product-readiness gate for Epic K first-run productization. Epic K
must prove that a non-developer evaluator can start the local baseline, see the
demo source, run the doctor, and inspect a workflow-first shell without
mistaking that milestone for production auth, production LLM generation, real
SQL execution, optional extension activation, or later source-family readiness.

Use this checklist before optional extension tracks begin.

During limited pilot operation, classify runtime posture with
[pilot-operations-runbook.md](./pilot-operations-runbook.md). The runbook
defines normal, degraded, maintenance, incident, and recovery states across
preview, generation, guard, execute, audit, source connectivity, and operator UI
surfaces. The checklist remains the sign-off gate; the runbook is the
operator-facing state and first-action guide.

## First-Run Productization Gate

First-run productization is an explicit gate before SafeQuery proceeds to real
auth, LLM adapter connectivity, safe execution API, or operator UI pilot work.
Passing Epic K means the local product baseline is evaluable. Passing Epic K
does not mean real LLM generation or real SQL execution is production-ready.

Before Epic K is signed off, a non-developer evaluator should be able to:

1. Copy the checked-in environment example and start the compose stack from the
   repository root.
2. Apply migrations through the compose-backed backend service.
3. Seed demo source governance records without creating a production trust
   source.
4. Run the first-run doctor and see pass/fail JSON for migrations, source
   registry readiness, dataset contract linkage, approved schema snapshots,
   entitlement readiness, backend health, and frontend health.
5. Open the operator shell and see demo source visibility through a non-empty
   active source selector returned by the backend.
6. Confirm preview submission remains source-scoped and entitlement-gated, while
   execute authority remains candidate-only and not exposed as raw SQL input.

The gate is product-readiness only. It is separate from later Epic L-P work:

- real auth and session bridge wiring
- production LLM adapter connectivity
- safe execution API wiring for approved candidates
- operator UI pilot completion beyond the first-run shell contract
- optional search, analyst, and MLflow extension activation
- future MySQL, MariaDB, Aurora, Oracle, Search, Analyst, or MLflow UI family
  activation

Do not advance later Epic L-P work by inferring readiness from service names,
placeholder credentials, demo governance bindings, operator-facing summaries, or
documentation proximity. The backend-owned source registry, migrations, doctor
payload, entitlement checks, and workflow API remain the authoritative evidence
for Epic K.

## Scope and Non-Requirements

In scope:

- first-run productization checks from Epic K
- compose-backed migrations, seed data, doctor diagnostics, backend/frontend
  health, and source selector visibility
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

- real authentication, production LLM connectivity, safe execution API pilot
  rollout, and final operator UI pilot behavior remain later Epic L-P gates
- optional search, analyst, and MLflow extension tracks are not required for
  the 2-source core path completion checklist
- if optional search, analyst, or MLflow behavior is enabled for a deployment,
  verify it under its own extension-track governance, audit, and evaluation
  criteria

## Focused Sign-Off Commands

Run these focused checks from the repository root unless a command changes into
`backend`.

```bash
bash tests/smoke/test-pilot-safety-ui-api-workflow.sh
bash tests/smoke/test-pilot-safety-checklist.sh
bash tests/smoke/test-local-topology-roles.sh
bash tests/smoke/test-local-startup-docs.sh
bash tests/smoke/test-compose-operator-workflow-source-selector.sh
cd backend
python3 -m pytest \
  tests/test_demo_source_seed.py \
  tests/test_first_run_doctor.py \
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
- `docs/design/dialect-capability-matrix.md` reflects the current 2-source
  pilot baseline coverage and required positive and deny corpus expectations for
  both `mssql` and `postgresql`.
- `docs/design/evaluation-harness.md` still requires 100 percent critical deny
  corpus pass rate and release blocking for unresolved threshold misses.
- `backend/tests/test_release_gate.py` still proves source-aware release gate
  failures for missing evaluation coverage, missing audit coverage, stale audit
  coverage, malformed artifacts, and safety regressions.
- `backend/tests/test_demo_source_seed.py` still proves local demo source
  visibility, idempotent seed behavior, and dev/local entitlement binding.
- `backend/tests/test_first_run_doctor.py` still proves migration, source
  registry, dataset contract, schema snapshot, entitlement readiness, backend
  health, and frontend health checks fail closed or pass from authoritative
  records.
- `tests/smoke/test-compose-operator-workflow-source-selector.sh` still proves
  the compose-backed first-run path migrates, seeds demo governance data, passes
  the first-run doctor, and exposes a non-empty active source selector.
- `tests/smoke/test-pilot-safety-ui-api-workflow.sh` still proves the pilot
  workflow through source selection, preview, guard, execute, result, and audit
  inspection by combining the focused UI smoke with backend preview,
  entitlement-denial, execution-denial, cancellation, and audit-history tests.
  It fails if placeholder SQL or placeholder result rows return to the product
  workflow surface.
- `backend/tests/test_source_bound_execute_path.py`,
  `backend/tests/test_execution_runtime_controls.py`,
  `backend/tests/test_mssql_execution_connector.py`, and
  `backend/tests/test_postgresql_execution_connector.py` still cover
  candidate-only execution, runtime controls, and both connector paths.

## Epic K Readiness Evidence

Record Epic K evidence before treating the first-run productization gate as
complete:

- K-1 documentation refresh: `README.md` and `docs/local-development.md` explain
  the product evaluation flow, role separation, path-hygienic commands, and the
  boundary between Epic K and later Epic L-P work.
- K-2 migration evidence: compose-backed `alembic upgrade head` and
  `alembic current` succeed for the application-owned control plane.
- K-3 seed evidence: `python -m app.cli.seed_demo_source` creates the demo
  business PostgreSQL source, dataset contract, approved schema snapshot, and
  dev/local entitlement binding with the backend-owned PostgreSQL `warehouse`
  execution profile, without treating application PostgreSQL as a business
  target.
- K-4 doctor evidence: `python -m app.cli.first_run_doctor` reports pass/fail
  status for migrations, active demo source registry records, dataset contract
  linkage, schema snapshot approval, entitlement readiness, execution connector
  readiness, live backend `/health` reachability, and live frontend app-surface
  reachability.
- K-5 workflow evidence:
  `tests/smoke/test-compose-operator-workflow-source-selector.sh` or the live
  `/operator/workflow` payload shows a non-empty active source selector sourced
  from backend records, not from client guesses or service-name inference.

Epic K is complete only when those artifacts agree. If README instructions,
local development guidance, doctor output, workflow payloads, or checklist
evidence disagree, repair the derived surface rather than redefining readiness
around the summary that happened to pass last.

## Epic L Auth-Context Evidence

Epic L completion evidence is limited to the authentication, application
session, entitlement, audit, and operator-history bridge. It does not complete
the later Epic M/P execute API, real LLM connectivity, production IdP callback,
or operator UI pilot.

Required evidence:

- HTTP preview accepts only a trusted authenticated subject plus a valid
  application session and CSRF boundary.
- Preview lifecycle audit events retain audit-safe subject, redacted session,
  auth-source, normalized governance-binding, entitlement-decision, source, and
  correlation context.
- Entitlement denial paths retain audit-safe denial evidence with source and
  governance-binding context where the current audit model supports it.
- Operator-history summaries can show minimized auth/source context without
  raw tokens, CSRF secrets, session cookies, session secrets, or identity
  provider internals.

Focused verification:
  `cd backend && python3 -m pytest tests/test_audit_event_model.py tests/test_dev_auth_preview_api.py tests/test_preview_source_governance_resolution.py tests/test_operator_history_payloads.py`.

## Source-Aware Checklist

### Auth

- Confirm authenticated subject context is present before source selection,
  preview, approval, or execution.
- Confirm auth-source, redacted session, normalized governance-binding, and
  entitlement-decision context is retained in audit-safe surfaces without raw
  tokens, cookies, CSRF secrets, session secrets, or identity provider internals.
- Confirm entitlement checks are source-specific for both MSSQL and business
  PostgreSQL.
- Confirm missing, malformed, placeholder, or mismatched auth context blocks
  before generation or execution.
- Focused verification:
  `cd backend && python3 -m pytest tests/test_source_entitlements.py tests/test_audit_event_model.py tests/test_dev_auth_preview_api.py tests/test_preview_source_governance_resolution.py tests/test_operator_history_payloads.py`.

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
  policy version, connector profile version, request id, correlation id,
  candidate id or equivalent candidate anchor, user subject, redacted session,
  auth source, governance bindings, entitlement decision, and primary deny code
  where relevant.
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
