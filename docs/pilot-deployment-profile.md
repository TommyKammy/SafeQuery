# Pilot Deployment Profile and Environment Contract

This document defines the limited SafeQuery pilot deployment profile and the
environment-value contract operators should use before starting, validating, or
sharing evidence from a pilot stack. It complements
[local-development.md](./local-development.md),
[pilot-safety-verification-checklist.md](./pilot-safety-verification-checklist.md),
and [pilot-operations-runbook.md](./pilot-operations-runbook.md).

The profile is intentionally local/pilot-scoped. It does not define production
release, cloud tenancy, secret rotation, or enterprise identity deployment.
Those remain later deployment and security tracks.

## Pilot Profile Assumptions

The pilot profile assumes:

- operators start from the repo-root `.env.example` contract and create a local
  `.env` before running Compose
- the backend owns source registry, entitlement, request, candidate, guard,
  execution, audit, doctor, and support-bundle decisions
- application PostgreSQL stores SafeQuery control-plane state only
- business-source credentials are separate from application database credentials
- browser-visible values are configuration endpoints, not secrets
- optional extension surfaces such as Search, Analyst, and MLflow are evidence
  helpers only when explicitly enabled for the pilot window

Do not infer pilot readiness from hostnames, service names, local file paths,
comments, or nearby metadata. Missing, blank, placeholder, mixed, or forbidden
environment values must fail closed before pilot traffic continues.

## Environment Categories

Classify every environment value in one of three categories:

| Category | Meaning | Pilot behavior |
| --- | --- | --- |
| Required | The stack, doctor, or pilot workflow cannot be evaluated safely without this value. | Missing or blank values fail closed. |
| Optional | The value has a reviewed default, is needed only for a specific extension, or is activated by a later pilot lane. | Leave unset unless the related lane is explicitly enabled and verified. |
| Forbidden | The value would expose credentials, confuse the trust boundary, or leak source data into untrusted surfaces. | Reject the configuration or stop sharing the artifact. |

When an optional lane is enabled for a deployment, its related governance,
audit, evaluation, and authorization requirements become mandatory for that
deployment.

## Required Values

The local/pilot Compose baseline requires these values:

| Value | Role |
| --- | --- |
| `SAFEQUERY_APP_POSTGRES_URL` | Backend connection to application PostgreSQL for SafeQuery-owned control-plane records. |
| `APP_POSTGRES_DB` | Compose startup value for the application PostgreSQL database. |
| `APP_POSTGRES_USER` | Compose startup value for the application PostgreSQL user. |
| `APP_POSTGRES_PASSWORD` | Compose startup value for the application PostgreSQL password. |
| `API_INTERNAL_BASE_URL` | Frontend server-side route to the backend inside the deployment boundary. |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-facing backend URL. This must be an endpoint only, never a secret-bearing URL. |
| `SAFEQUERY_BACKEND_BASE_URL` | First-run doctor backend probe base URL. |
| `SAFEQUERY_FRONTEND_BASE_URL` | First-run doctor frontend probe base URL. |

The application database values are required because the backend must have an
authoritative place to persist migrations, source registry records, contracts,
schema snapshots, requests, candidates, execution state, and audit records.
They do not create a business query source.

## Optional Values

These values are optional for the baseline local/pilot profile unless a specific
pilot lane says otherwise:

| Value | Role |
| --- | --- |
| `SAFEQUERY_APP_NAME` | Operator-facing application name with a reviewed default. |
| `SAFEQUERY_ENVIRONMENT` | Environment label used for diagnostics and support context. |
| `SAFEQUERY_DEV_AUTH_ENABLED` | Dev/local authentication fixture toggle. It must stay off unless the local pilot path explicitly uses the dev entitlement fixture. |
| `SAFEQUERY_CORS_ORIGINS` | Allowed frontend origins for the backend. Narrow to the expected frontend URL for the pilot. |
| `BUSINESS_POSTGRES_SOURCE_DB` | Compose startup value for the local business PostgreSQL source container. |
| `BUSINESS_POSTGRES_SOURCE_USER` | Compose startup value for the local business PostgreSQL source user. |
| `BUSINESS_POSTGRES_SOURCE_PASSWORD` | Compose startup value for the local business PostgreSQL source password. |
| `BUSINESS_MSSQL_SOURCE_SA_PASSWORD` | Compose startup value for the local business MSSQL source container. |
| `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL` | Backend-only connection setting for an explicitly registered business PostgreSQL source. |
| `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` | Backend-only connection setting for an explicitly registered business MSSQL source. |

Optional business-source connection values must stay backend-only and
source-scoped. They are valid only when the backend-owned source registry,
connector profile, entitlement, guard, and pilot verification evidence agree.

## Forbidden Values

The pilot profile forbids:

- raw secrets in frontend or public payloads, including `NEXT_PUBLIC_*`
  variables, browser responses, UI state, static assets, telemetry, issue text,
  and screenshots
- source credentials in audit exports or support bundles
- source connection URLs, connection strings, passwords, tokens, cookies, CSRF
  secrets, session secrets, private keys, or identity-provider internals in
  artifacts shared outside the backend trust boundary
- application database credentials reused for business-source access
- application PostgreSQL treated as an active business source
- business-source credentials inferred from application database names,
  service names, driver names, or comments
- client-supplied identity, tenant, source, host, proto, or forwarded-header
  values treated as trusted environment binding
- workstation-local absolute paths in publishable docs, validation plans,
  support bundles, audit exports, or operator-facing evidence

If a forbidden value appears, stop the affected pilot path, rotate or replace
the exposed credential if needed, and preserve only bounded identifiers such as
request ids, candidate ids, run ids, audit ids, source ids, and command names.

## Application Database

Application PostgreSQL is SafeQuery-owned persistence. It stores application
records such as:

- migrations and schema posture
- source registry records and source readiness state
- dataset contracts and schema snapshots
- request, candidate, guard, approval, execution, and audit records
- operator workflow history and readiness evidence

`SAFEQUERY_APP_POSTGRES_URL` must point to this application database. In this
contract, application PostgreSQL is not a business source, not a query target,
and not a fallback source credential pool.

## Business Sources

Business sources are separate from application PostgreSQL and become usable only
through explicit backend records:

- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL` belongs to an explicitly registered
  business PostgreSQL source such as the local demo source.
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` belongs to an explicitly
  registered business MSSQL source.

For each active source, the pilot must be able to prove source id, source
family, optional flavor, connector profile, dataset contract, schema snapshot,
entitlement binding, guard profile, and readiness evidence from authoritative
backend records. Do not activate a source from environment naming alone.

## Auth, CSRF, and Session

Auth, CSRF, and session values remain trusted-backend concerns:

- `SAFEQUERY_DEV_AUTH_ENABLED` is a local fixture toggle, not production auth.
- Session cookies, CSRF secrets, bridge tokens, identity-provider assertions,
  and authorization internals must never be placed in frontend/public
  environment values or support artifacts.
- The backend must establish and validate application-owned session and
  authorization context before state-changing or execute-bound paths.

If auth context is missing, placeholder, unsigned, forwarded without a trusted
proxy, or otherwise untrusted, keep the pilot path blocked.

## Audit Export and Support Bundle

Audit exports and support bundles are bounded diagnostic artifacts. They may
include application version, environment label, source ids, source posture,
health summaries, migration posture, workflow state summaries, lifecycle
metrics, and audit completeness counts.

Dedicated governance review exports are separate reviewer-scoped artifacts, not
support bundles with a broader audience. Use
`docs/design/audit-governance-export-bundle.md` for the required source/time
filters, reviewer-only authority, redaction rules, and fail-closed behavior.
Support-bundle posture must not substitute for that contract.

They must not include:

- raw operator prompts, raw SQL, or raw result rows
- database URLs, connection strings, passwords, tokens, cookies, session
  secrets, CSRF secrets, private keys, or source connection references
- source credentials in audit exports or support bundles
- workstation-local absolute paths

Before sharing an artifact, inspect it as text and stop if a forbidden value is
present. An export or bundle that contains forbidden values is an incident or
recovery input, not a shareable pilot artifact.

## Validation and Doctor Guidance

Use the first-run doctor after env setup, migrations, and demo source seeding:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend python -m app.cli.first_run_doctor
```

The doctor should fail closed when required backend-owned prerequisites are
missing, including application database connectivity, migrations, source
registry records, dataset contract linkage, approved schema snapshots,
entitlement seed data, execution connector binding, execution driver runtime
availability, backend reachability, and frontend reachability. A driver
`runtime_status: unavailable` result points to a missing PostgreSQL `psycopg`
or MSSQL `pyodbc` / ODBC Driver 18 prerequisite and should be remediated before
interpreting source connectivity denied or unavailable results.

The doctor is not a secret scanner. Operators must still manually inspect
changed docs, validation plans, audit exports, support bundles, and public
payloads for forbidden values before sharing them.

When a doctor, smoke, export, or support-bundle result depends on a missing
prerequisite signal, reject the pilot posture instead of substituting guessed
context. Use repo-relative command forms and documented environment variables
in durable notes.
