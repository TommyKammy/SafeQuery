# SafeQuery Baseline

SafeQuery is a controlled enterprise NL2SQL application. This repository checkpoint establishes the minimum local baseline for:

- a Next.js frontend
- a FastAPI backend
- a PostgreSQL application database

The baseline intentionally stops at placeholder UI and health-oriented API behavior. No auth, SQL generation, SQL guard, or SQL execution logic is implemented yet.

## Repository Shape

```text
frontend/  Next.js UI placeholder and local stack status surface
backend/   FastAPI API placeholder and PostgreSQL-backed health checks
infra/     Docker Compose baseline for local startup
tests/     Focused smoke checks for repository structure
docs/      Architecture and requirements source material
```

## Local Startup

For the full baseline startup workflow, including env setup, compose startup,
migrations, and troubleshooting, use
[docs/local-development.md](./docs/local-development.md).

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
  `business-postgres-source` service for later generation-context work
- business MSSQL source uses
  `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` and the
  `business-mssql-source` service for later execution-path work

2. Start the local stack:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

If `.env` is missing or a required value is blank, Docker Compose will stop with
an explicit missing-variable error instead of silently using local defaults.

The baseline startup path still uses the same compose entrypoint, but the local
topology now declares a separate application PostgreSQL service, a separate
business PostgreSQL source, and a separate business MSSQL source so later
source-aware work has explicit local anchors. This role split does not make the application database a business target.

3. Confirm the UI is reachable:

```bash
curl -I http://localhost:3000
```

4. Confirm the API health endpoint is reachable and healthy:

```bash
curl http://localhost:8000/health
```

PostgreSQL stays on the compose network only for this baseline. The app stack
reaches it internally, which avoids common host-port conflicts during local
startup.

If your Docker shell is pointed at a stale Colima socket, scope the command to the active profile instead of changing global settings:

```bash
DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock" \
  docker-compose --env-file .env -f infra/docker-compose.yml up --build -d
```

5. Stop the stack when finished:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml down
```

To remove the PostgreSQL volume as well:

```bash
docker-compose --env-file .env -f infra/docker-compose.yml down -v
```

## Extension Seams

The initial structure leaves explicit room for later feature work:

- `backend/app/features/auth/` for session and identity enforcement
- `backend/app/features/guard/` for SQL validation and deny logic
- `backend/app/features/execution/` for approved query execution handling
- `backend/app/features/audit/` for lifecycle audit persistence

The frontend remains a simple shell so later query input, SQL preview, and audit workflows can be added without changing the trusted backend boundary.

## Focused Verification

Repository structure smoke check:

```bash
tests/smoke/test-baseline.sh
```

Optional local component checks:

```bash
cd frontend && cp .env.local.example .env.local && npm install && npm run build
cd ../backend && cp .env.example .env && python3 -m pip install -e .
```

Backend settings can also load from `.env` or `../.env`, so running from the
repo root or from `backend/` uses the same configuration path.

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
SAFEQUERY_APP_POSTGRES_URL="postgresql://safequery:change-me-for-shared-environments@127.0.0.1:5432/safequery" alembic upgrade head
SAFEQUERY_APP_POSTGRES_URL="postgresql://safequery:change-me-for-shared-environments@127.0.0.1:5432/safequery" alembic current
```

Source-foundation smoke verification:

```bash
cd backend
python3 -m pytest tests/test_source_foundation_smoke.py
```

Startup-guard verification:

```bash
cd backend
python3 -m pytest tests/test_application_postgres_guard.py
```

Local topology smoke verification:

```bash
bash tests/smoke/test-local-topology-roles.sh
```

Application persistence and business-source access now use separate reviewed
names:

- `SAFEQUERY_APP_POSTGRES_URL` for the application-owned PostgreSQL system of
  record
- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL` for a business PostgreSQL source used
  to curate generation context later
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` for the dedicated MSSQL
  execution source path

Do not reuse the application PostgreSQL credential as a business-source secret.

The fail-closed startup guards are intentional:

- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL must not reuse SAFEQUERY_APP_POSTGRES_URL`
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING must be configured before the business MSSQL execution source can be used.`

The compose topology mirrors those roles explicitly:

- `app-postgres` for application PostgreSQL persistence
- `business-postgres-source` for the optional local business PostgreSQL source
- `business-mssql-source` for the optional local business MSSQL source

The backend baseline still depends only on `app-postgres`; the source services
exist to keep the local topology and credentials explicit for later work.

On startup, the backend logs `source_posture`, `configured_source_count`, and a
`source_roles` map so local diagnosis can confirm which source role is
configured or intentionally left unset without inferring from service names.

The dedicated local startup guide remains the source of truth for contributor
setup and troubleshooting.
