# Local Development Startup

This guide documents the current baseline startup path for local SafeQuery
development and product evaluation. It separates developer setup commands from
the product evaluation flow so first-run users can tell the difference between
building the stack and judging the current SafeQuery baseline.

The repository currently contains the source-aware core service baseline:

- Next.js frontend
- FastAPI backend
- application PostgreSQL
- Alembic migrations for the application-owned control plane
- backend-owned source registry readiness
- source-aware preview, audit, evaluation, and operator-workflow contracts

The local topology also declares dedicated source-role services:

- business PostgreSQL source
- business MSSQL source

Those source services are local role anchors. They do not make application
PostgreSQL a business target, and they do not grant execution authority to an
LLM, SQL generation adapter, browser client, MLflow export, search surface, or
analyst surface.

Use this document as the source of truth for first local runs. `README.md`
keeps a shorter entrypoint and links back here.

For limited pilot operations after first-run setup, use
[pilot-operations-runbook.md](./pilot-operations-runbook.md) to classify normal,
degraded, maintenance, incident, and recovery posture. The runbook keeps
SafeQuery control-plane records authoritative over UI summaries, LLM output,
adapter output, MLflow, Search, Analyst, and external evidence.

## Current Baseline

SafeQuery currently supports two practical local workflows:

- compose-backed startup for the full baseline stack
- host-shell component checks for the frontend or backend in isolation

The compose-backed path is the baseline because it wires the frontend, backend,
database, source registry records, migrations, and health checks together with
the repository's current settings.

## Product evaluation flow

Use this flow when you are evaluating the current product baseline rather than
developing an individual component:

1. Create `.env` from `.env.example`.
2. Start the compose stack from the repository root.
3. Apply Alembic migrations through the compose-backed backend service.
4. Open `http://localhost:3000` and inspect the workflow-first operator shell.
5. Confirm `http://localhost:8000/health` returns a healthy backend response.
6. Confirm the operator shell is using backend source registry data, not a
   source inferred from a service name or local credential name.

A successful first-run baseline should show:

- backend health backed by application PostgreSQL
- source registry readiness for reviewed local source records
- source-aware request and preview contracts anchored to backend records
- explicit source visibility in the operator shell
- candidate-only execution posture, with no raw-SQL execute authority exposed to
  the client

Known Missing Product Wiring:

- real authentication and session bridge wiring
- production SQL generation adapter integration
- final persisted candidate and run history
- execute-path wiring for approved candidates
- deployment, secrets, and production release operations

Optional governed search, analyst-style orchestration, and MLflow integrations
remain extension tracks. They are not required for first-run Epic K activation
and must not become execution, authorization, audit, or source-registry
authorities.

## First-run UI empty states

The operator shell uses the same first-run setup path described in this guide.
When a required backend-owned signal is missing, the UI stays blocked instead
of inventing source, entitlement, history, preview, or result data.

| UI state | What it means | Next action |
| --- | --- | --- |
| Source registry not configured | `/operator/workflow` is reachable but returned no source registry options. | Run migrations, seed the demo source, then run the first-run doctor before submitting preview requests. |
| Source entitlement not available | The backend rejected the workflow context because the operator is not entitled to the selected source. | Confirm the signed-in operator has the dev/local entitlement binding for the selected source, then retry the workflow. |
| No workflow history yet | At least one active source is available, but no authoritative request, candidate, or run summaries exist yet. | Submit a preview request against an active source; history appears only after the backend returns it. |
| Backend workflow unavailable | The workflow payload is unavailable or malformed. | Confirm backend health, migrations, demo source seed, and first-run doctor before using the product shell. |

## Developer setup flow

Use the numbered setup sections below when you need to build, migrate, test, or
troubleshoot the stack locally. The commands are intentionally repo-relative and
avoid workstation-local absolute paths.

## Prerequisites

- Docker and `docker-compose`
- Node.js and `npm` if you want to run frontend checks from the host shell
- Python 3.9+ and `pip` if you want to run backend checks from the host shell

If your shell is pointed at the wrong Docker socket, scope `DOCKER_HOST` on the
command you run instead of changing global settings:

```bash
DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock" \
  docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

## 1. Create the Required Env Files

The full stack expects a repository-level `.env` file:

```bash
cp .env.example .env
```

That file provides the baseline values for:

- application PostgreSQL startup: `APP_POSTGRES_DB`, `APP_POSTGRES_USER`,
  `APP_POSTGRES_PASSWORD`
- backend startup: `SAFEQUERY_APP_NAME`, `SAFEQUERY_ENVIRONMENT`,
  `SAFEQUERY_APP_POSTGRES_URL`, `SAFEQUERY_CORS_ORIGINS`
- frontend startup: `API_INTERNAL_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`

It also reserves distinct local-only credentials for the optional source
containers:

- business PostgreSQL source startup: `BUSINESS_POSTGRES_SOURCE_DB`,
  `BUSINESS_POSTGRES_SOURCE_USER`, `BUSINESS_POSTGRES_SOURCE_PASSWORD`
- business MSSQL source startup: `BUSINESS_MSSQL_SOURCE_SA_PASSWORD`

Optional reviewed-but-unset source connection settings are also reserved there
so later feature work cannot blur them with the application database secret:

- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL`
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING`

Treat those as three different local roles:

- application PostgreSQL is SafeQuery-owned persistence and stays bound to
  `SAFEQUERY_APP_POSTGRES_URL`
- business PostgreSQL source is a separate read-oriented source role reserved
  for later generation-context work through
  `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL`
- business MSSQL source is a separate execution-oriented source role reserved
  for later execution-path work through
  `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING`

The hardened local foundation keeps those roles explicit before any source-aware
core path exists, so operators can inspect the topology without guessing and
without treating application PostgreSQL as a business target.

The backend-owned source registry remains authoritative for source activation.
Do not infer an active source from a hostname, credential name, driver string,
or nearby documentation note.

The backend image packages `pyodbc` and Microsoft ODBC Driver 18 for SQL Server
for the MSSQL connector. Those packages are runtime prerequisites only; MSSQL
execution remains disabled until
`SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` is explicitly configured for
the business MSSQL source and the request is bound to a backend-owned,
candidate-only MSSQL connector selection.

The checked-in baseline values are already wired to the compose network:

- application database hostname: `app-postgres`
- frontend internal API hostname: `backend`
- browser-facing API URL: `http://localhost:8000`

The optional source-topology hostnames are also fixed in the checked-in
examples so operators can inspect the intended role split without guessing:

- business PostgreSQL source hostname: `business-postgres-source`
- business MSSQL source hostname: `business-mssql-source`

Optional host-shell env files are also available when you want to run a single
component without Docker:

```bash
cp frontend/.env.local.example frontend/.env.local
cp backend/.env.example backend/.env
```

Those files are not required for the baseline compose flow, but they are the
right first-run setup for isolated frontend or backend commands.

## 2. Start the Baseline Stack

Start the full local stack from the repository root:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

This command starts services in the expected dependency order:

1. application PostgreSQL
2. backend
3. frontend

The compose file lives at `infra/docker-compose.yml`.

If `.env` is missing or a required variable is blank, the startup should fail
closed with an explicit Compose error instead of silently substituting guessed
values.

The backend baseline still depends only on application PostgreSQL. The separate
business PostgreSQL source and business MSSQL source are present so operators
can inspect the intended multi-source topology without guessing and without
treating application PostgreSQL as a business target.

## 3. Verify Basic Health

Check that the frontend is reachable:

```bash
curl -I http://localhost:3000
```

Check that the backend health endpoint succeeds:

```bash
curl http://localhost:8000/health
```

The backend `/health` endpoint is the baseline health check for the app and the
database connection.

For product evaluation, backend health is necessary but not sufficient. After
migrations, seed demo governance data and then run the first-run doctor:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend python -m app.cli.seed_demo_source
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend python -m app.cli.first_run_doctor
```

The doctor emits JSON with pass/fail/degraded checks for application database
connectivity, Alembic posture, active demo source registry records, linked
dataset contracts, approved schema snapshots, dev/local entitlement seed data,
the backend-owned execution connector binding, `SAFEQUERY_BACKEND_BASE_URL`
`/health` reachability, and `SAFEQUERY_FRONTEND_BASE_URL` app-surface
reachability. Missing registry data, contract links, schema snapshots,
entitlements, execution connector readiness, migrations, unreachable backend
health, or an unreachable/unexpected frontend surface are failures, not empty UI
states.

The same payload is available from the running backend:

```bash
curl http://localhost:8000/doctor/first-run
```

Because the API-served doctor route is already running inside the backend, that
payload marks the backend route itself as reachable. Use the CLI doctor when
you need to verify that the configured `SAFEQUERY_BACKEND_BASE_URL` also
reaches `/health`. In Compose, `.env.example` points the backend container at
the service-local backend and frontend URLs so the doctor probes reachable
surfaces from inside the compose network.

Confirm the live operator workflow contract exposes at least one active source
selector option:

```bash
curl http://localhost:8000/operator/workflow
```

Confirm that the frontend can render the operator workflow shell and that source
registry data is available to the shell. Missing registry data should block
preview submission rather than letting the UI guess an executable source.

## 4. Validate the Hardened Foundation

Run the focused smoke checks that prove the local role split and fail-closed
startup behavior before moving on to deeper source-aware work:

```bash
bash tests/smoke/test-local-topology-roles.sh
cd backend
python3 -m pytest tests/test_application_postgres_guard.py
python3 -m pytest tests/test_source_foundation_smoke.py
bash tests/smoke/test-compose-operator-workflow-source-selector.sh
```

Those checks cover different enforcement boundaries:

- `tests/smoke/test-local-topology-roles.sh` proves the compose topology and
  checked-in env examples keep `app-postgres`, `business-postgres-source`, and
  `business-mssql-source` distinct
- `tests/test_application_postgres_guard.py` proves startup validation fails
  closed if `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL` tries to reuse
  `SAFEQUERY_APP_POSTGRES_URL`
- `tests/test_source_foundation_smoke.py` proves the backend still reports a
  coherent source posture when optional business sources are unset or configured
- `tests/smoke/test-compose-operator-workflow-source-selector.sh` proves the
  documented first-run compose path can migrate, seed demo governance data,
  pass backend readiness checks, and expose a non-empty active source selector
  through `/operator/workflow`

When the startup guards fire, expect explicit messages instead of implicit
fallbacks:

- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse SAFEQUERY_APP_POSTGRES_URL`
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must be configured before the business MSSQL execution source can be used.`
- `pyodbc must be installed before the MSSQL execution connector can run.`
- `ODBC Driver 18 for SQL Server must be installed before the MSSQL execution connector can run.`

On successful startup, inspect backend logs for the source-role telemetry fields
that summarize the hardened foundation without inferring from service names:

- `source_posture`
- `configured_source_count`
- `source_roles`

These checks preserve the SafeQuery trust boundary: source registry decisions
are backend-owned, application PostgreSQL stays separate from business sources,
candidate-only execution remains the only approved execute posture, and there is
no LLM or adapter execution authority.

## 5. Run Migrations

The current baseline keeps PostgreSQL on the compose network only, so the
compose-backed Alembic path is the default migration workflow:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic upgrade head
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic current
```

Use the first command to apply the scaffolded baseline migration and the second
to confirm the active revision.

If you need to run Alembic from the host shell instead, use `backend/.env` or
an explicit `SAFEQUERY_APP_POSTGRES_URL` that points at a database reachable from
your shell. Do not reuse the compose-only `app-postgres` hostname from `.env` in a
host-shell command.

Example host-shell path:

```bash
python3 -m pip install -e backend
cd backend
SAFEQUERY_APP_POSTGRES_URL="postgresql://safequery:change-me-for-shared-environments@127.0.0.1:5432/safequery" alembic upgrade head
SAFEQUERY_APP_POSTGRES_URL="postgresql://safequery:change-me-for-shared-environments@127.0.0.1:5432/safequery" alembic current
```

## 6. Optional Host-Shell Component Checks

Frontend build check:

```bash
cp frontend/.env.local.example frontend/.env.local
cd frontend
npm install
npm run build
```

Backend install check:

```bash
cp backend/.env.example backend/.env
python3 -m pip install -e backend
```

The backend settings loader accepts `.env` and `../.env`, which keeps the repo
root and `backend/` command paths aligned.

Host-shell component checks are developer setup checks. They do not replace the
compose-backed product evaluation flow because they do not prove the full
frontend, backend, migration, and source-registry topology together.

## 7. Stop the Stack

Stop the running stack:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml down
```

Remove the PostgreSQL volume too if you want a clean database reset:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml down -v
```

## Troubleshooting

### `docker-compose` fails with missing variable errors

Copy `.env.example` to `.env` again and confirm the required keys are present:

- `SAFEQUERY_APP_POSTGRES_URL`
- `API_INTERNAL_BASE_URL`
- `NEXT_PUBLIC_API_BASE_URL`
- `APP_POSTGRES_DB`
- `APP_POSTGRES_USER`
- `APP_POSTGRES_PASSWORD`

### `docker-compose up --build` fails with a missing `docker-buildx` plugin

Some local Docker installs are configured to invoke Buildx even when the plugin
is not present. If you see an error similar to `fork/exec ... docker-buildx: no
such file or directory`, rerun the startup command with BuildKit disabled for
that invocation:

```bash
DOCKER_BUILDKIT=0 \
  docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

If you also need to point the command at an active Colima socket, add the
override separately for that invocation:

```bash
DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock" \
DOCKER_BUILDKIT=0 \
  docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

### Frontend loads but API calls fail

Confirm the backend health check first:

```bash
curl http://localhost:8000/health
```

If that succeeds, re-check the frontend env values in `.env` or
`frontend/.env.local` and make sure the browser-facing API URL still points at
`http://localhost:8000`.

### Host-shell Alembic commands cannot reach PostgreSQL

This is expected if you try to use the compose-only hostname `app-postgres` from a
host shell. Use the compose-backed migration commands instead, or point
`SAFEQUERY_APP_POSTGRES_URL` at a host-reachable database endpoint.

## Epic K Sequence

Epic K starts with the refreshed README and this local development guide, then
continues into first-run seed data, source-registry doctor/readiness checks, and
the next productization issues. Keep the sequence aligned with
[docs/implementation-roadmap.md](./implementation-roadmap.md) and use
repo-relative commands or placeholders such as `<supervisor-config-path>` when
writing issue text or validation notes.

Future families from Epic J remain planned metadata only unless a later issue
explicitly activates them through backend-owned source registry, connector,
guard, entitlement, audit, candidate lifecycle, and release-gate work. MySQL,
MariaDB, Aurora, Oracle, Search, Analyst, and MLflow UI work must not be treated
as part of first-run Epic K activation.
