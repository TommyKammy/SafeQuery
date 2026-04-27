# SafeQuery Source-Aware Baseline

SafeQuery is a controlled enterprise NL2SQL application. This repository now
captures the source-aware core service baseline for the first productized local
run:

- a Next.js operator workflow shell
- a FastAPI backend control plane
- an application PostgreSQL system of record
- Alembic migrations for source registry, dataset, schema snapshot, retrieval,
  and related control-plane records
- source-aware preview, audit, evaluation, and operator-workflow contracts

The current baseline is intentionally application-owned. The backend-owned
source registry controls which business sources can be selected, application
PostgreSQL remains separate from business-source credentials, and execution must
stay candidate-only through server-owned candidate identifiers. The browser, SQL
generation adapter, LLM, analyst surface, search surface, and MLflow exports do
not receive execution authority.

## Repository Shape

```text
frontend/  Next.js operator workflow shell and product-state surfaces
backend/   FastAPI control plane, migrations, source registry, and contracts
infra/     Docker Compose baseline for local startup
tests/     Focused smoke checks for repository and documentation contracts
docs/      Architecture, requirements, roadmap, and local development guides
```

## Product evaluation flow

Use this path when you want to inspect the current product baseline as a
non-developer evaluator:

1. Create `.env` from the checked-in example.
2. Start the compose stack.
3. Run migrations.
4. Open the frontend at `http://localhost:3000`.
5. Confirm the backend health endpoint at `http://localhost:8000/health`.
6. Confirm the operator shell can load source registry options from the backend
   instead of relying on hard-coded source names.

A successful first run should show the workflow-first operator shell, reachable
backend health, an application PostgreSQL-backed control plane, and source
registry readiness for reviewed source records. The local baseline can exercise
source-aware request and preview contracts, but it should not be read as a
complete production pilot.

For limited pilot operations after first-run setup, use
[docs/pilot-operations-runbook.md](./docs/pilot-operations-runbook.md) to
classify normal, degraded, maintenance, incident, and recovery posture. Keep
SafeQuery control-plane records authoritative over UI summaries, LLM output,
adapter output, MLflow, Search, Analyst, and external evidence.
Use [docs/pilot-deployment-profile.md](./docs/pilot-deployment-profile.md) to
classify required, optional, and forbidden environment values before treating a
local first-run stack as pilot evidence.

Known product-readiness gaps remain for later Epic K/O/P work:

- real authentication and session wiring
- production SQL generation adapter integration
- fully persisted candidate and run history
- final execute-path wiring for approved candidates
- production deployment, secrets, and release operations

The operator shell direction is defined in
`docs/design/operator-workflow-information-architecture.md`; extend that
workflow-first contract rather than reintroducing placeholder-only health UI.

Optional governed search, analyst-style orchestration, and MLflow integrations
are extension tracks. They can observe or enrich the product when separately
enabled, but they are not prerequisites for the core SafeQuery control path and
must not become trusted execution or authorization authorities.

Future MySQL, MariaDB, Aurora, Oracle, Search, Analyst, and MLflow UI activation
work remains planned metadata or optional extension work unless a later issue
explicitly activates it. First-run productization must not infer those families
from docs, service names, driver names, or placeholder configuration.

## Developer setup flow

For the full local startup workflow, including env setup, compose startup,
migrations, and troubleshooting, use
[docs/local-development.md](./docs/local-development.md).
The same guide also defines the first-run UI empty states for missing source
registry data, entitlement, workflow history, and backend readiness.

Quick start:

1. Create a local environment file from the checked-in example:

```bash
cp .env.example .env
```

The required baseline startup values are:

- `SAFEQUERY_APP_POSTGRES_URL`
- `API_INTERNAL_BASE_URL`
- `NEXT_PUBLIC_API_BASE_URL`
- `APP_POSTGRES_DB`
- `APP_POSTGRES_USER`
- `APP_POSTGRES_PASSWORD`

Optional values with reviewed defaults in code or compose:

- `SAFEQUERY_APP_NAME`
- `SAFEQUERY_ENVIRONMENT`
- `SAFEQUERY_DEV_AUTH_ENABLED`
- `SAFEQUERY_CORS_ORIGINS`
- `BUSINESS_POSTGRES_SOURCE_DB`
- `BUSINESS_POSTGRES_SOURCE_USER`
- `BUSINESS_POSTGRES_SOURCE_PASSWORD`
- `BUSINESS_MSSQL_SOURCE_SA_PASSWORD`
- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL`
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING`

Keep the local roles distinct from the start:

- application PostgreSQL uses `SAFEQUERY_APP_POSTGRES_URL` and the
  `app-postgres` service for SafeQuery-owned state
- business PostgreSQL source uses
  `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL` and the
  `business-postgres-source` service for source-specific context work
- business MSSQL source uses
  `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` and the
  `business-mssql-source` service for source-specific connector work

This role split does not make the application database a business target.
The backend image packages `pyodbc` and Microsoft ODBC Driver 18 for SQL
Server, but the MSSQL execution connector still stays source-scoped: it is only
usable when `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` is explicitly
configured for the business MSSQL source.

2. Start the local stack:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

If `.env` is missing or a required value is blank, Docker Compose stops with an
explicit missing-variable error instead of silently using local defaults.

If your Docker shell is pointed at a stale Colima socket, scope the command to
the active profile instead of changing global settings:

```bash
DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock" \
  docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

3. Apply migrations:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic upgrade head
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic current
```

4. Seed the local demo source governance records:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend python -m app.cli.seed_demo_source
```

The seed is safe to rerun against a local development database. It creates the
`demo-business-postgres` source registry record, matching dataset contract, two
minimal allow-listed demo datasets, and an approved schema snapshot pointer. The
seed references `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL` for the business source
and binds the source to the backend-owned PostgreSQL `warehouse` execution
profile; it does not make application PostgreSQL a business target. The dataset
contract owner binding is the dev/local-only fixture
`group:safequery-demo-local-operators`, intended for later development auth
middleware to attach to `user:demo-local-operator`; it is not a production trust
source and does not bypass the source-scoped entitlement check.

5. Run the first-run doctor:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend python -m app.cli.first_run_doctor
```

The doctor returns machine-readable JSON and fails closed when migrations,
demo source registry records, linked dataset contracts, approved schema
snapshots, dev/local entitlement seed data, or the backend-owned execution
connector binding are missing. The execution connector check also reports
driver runtime availability for active source families: `psycopg` for
PostgreSQL and `pyodbc` plus ODBC Driver 18 for SQL Server. A
`runtime_status: unavailable` result means the backend image or host runtime is
missing a driver prerequisite; it is distinct from a later source connectivity
denial or unavailable external source. The CLI doctor also probes
`SAFEQUERY_BACKEND_BASE_URL` `/health` and `SAFEQUERY_FRONTEND_BASE_URL`;
unreachable or unhealthy surfaces are reported as failures instead of
first-run-ready passes.
For the required, optional, and forbidden environment-value contract that frames
these checks, see
[docs/pilot-deployment-profile.md](./docs/pilot-deployment-profile.md).

6. Confirm the live operator workflow contract exposes an active source selector
   option:

```bash
curl http://localhost:8000/operator/workflow
```

For the full compose-backed first-run smoke path, run:

```bash
bash tests/smoke/test-compose-operator-workflow-source-selector.sh
```

This smoke starts the compose baseline, runs migrations and demo seed through
repo-owned backend commands, checks backend health and the first-run doctor,
then fails with a targeted message if `/operator/workflow` returns no active
source selector option.

7. Confirm the UI is reachable:

```bash
curl -I http://localhost:3000
```

8. Confirm the API health endpoint is reachable and healthy:

```bash
curl http://localhost:8000/health
```

9. Stop the stack when finished:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml down
```

To remove the PostgreSQL volume as well:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml down -v
```

## Trust Boundary

SafeQuery's trusted boundary stays in the backend:

- the backend-owned source registry decides which source records are executable
- application PostgreSQL stores SafeQuery control-plane state only
- business-source credentials are distinct from application persistence
- preview and execute surfaces are tied to server-owned source and candidate
  records
- candidate-only execution is required; clients must not submit raw SQL for
  execution
- no LLM or adapter execution authority is granted by this baseline

The fail-closed startup guards are intentional:

- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse SAFEQUERY_APP_POSTGRES_URL`
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must be configured before the business MSSQL execution source can be used.`
- `psycopg must be installed and importable before the PostgreSQL execution connector can run.`
- `pyodbc must be installed and importable before the MSSQL execution connector can run.`
- `ODBC Driver 18 for SQL Server must be installed before the MSSQL execution connector can run.`

The compose topology mirrors those roles explicitly:

- `app-postgres` for application PostgreSQL persistence
- `business-postgres-source` for the optional local business PostgreSQL source
- `business-mssql-source` for the optional local business MSSQL source

On startup, the backend logs `source_posture`, `configured_source_count`, and a
`source_roles` map so local diagnosis can confirm which source role is
configured or intentionally left unset without inferring from service names.

## Focused Verification

Repository structure smoke check:

```bash
tests/smoke/test-baseline.sh
```

Documentation entrypoint checks:

```bash
bash tests/smoke/test-local-startup-docs.sh
bash tests/smoke/test-doc-entrypoints-current-set.sh
bash tests/smoke/test-epic-a-doc-framing.sh
```

Backend migration scaffold verification:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic upgrade head
docker-compose --env-file .env -f infra/docker-compose.yml run --rm backend alembic current
```

If you need to run Alembic from the host shell instead, provide an explicitly
reachable database URL rather than relying on the compose-only `app-postgres`
hostname:

```bash
python3 -m pip install -e backend
cd backend
SAFEQUERY_APP_POSTGRES_URL="<reachable-app-postgres-url>" alembic upgrade head
SAFEQUERY_APP_POSTGRES_URL="<reachable-app-postgres-url>" alembic current
```

Source-foundation smoke verification:

```bash
cd backend
python3 -m pytest tests/test_source_foundation_smoke.py
```

Compose-backed first-run operator workflow smoke verification:

```bash
bash tests/smoke/test-compose-operator-workflow-source-selector.sh
```

Pilot safety UI/API smoke verification:

```bash
bash tests/smoke/test-pilot-safety-ui-api-workflow.sh
```

This smoke is the single command-backed pilot path for the local unit-contract
layer. It runs the checklist guard, a focused frontend workflow smoke, and
backend preview, denial, cancellation, execute, and audit-history tests. It
does not start Docker; use the compose-backed smokes below when containerized
source dependencies also need verification.

Compose-backed real source execution smoke verification:

```bash
bash tests/smoke/test-compose-real-source-execution.sh
```

This disposable smoke starts the compose baseline with explicit business
PostgreSQL and MSSQL source credentials from the repo-local example values,
seeds bounded read-only source fixtures, verifies wrong-source and raw-SQL
execute requests are rejected before execution, executes approved candidate IDs
against both real source containers, and checks persisted execution audit
evidence. If Docker / Colima is unavailable, it exits with an explicit
smoke-not-run status instead of reporting a product pass.

Startup-guard verification:

```bash
cd backend
python3 -m pytest tests/test_application_postgres_guard.py
```

Local topology smoke verification:

```bash
bash tests/smoke/test-local-topology-roles.sh
```

## Epic K Sequence

The intended Epic K order starts with this README and local development refresh,
then moves through first-run seed data, doctor/readiness checks, and the next
source-aware productization issues. Track that sequence in
[docs/implementation-roadmap.md](./docs/implementation-roadmap.md) and keep
issue text path-hygienic by using repo-relative commands and placeholders such
as `<supervisor-config-path>` instead of workstation-local absolute paths.

The roadmap is directional planning, not an activation switch for later source
families or optional UI tracks.
