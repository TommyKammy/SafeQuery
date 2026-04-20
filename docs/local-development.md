# Local Development Startup

This guide documents the current baseline startup path for local SafeQuery
development. It is intentionally limited to the foundation stack that exists in
this repository today:

- Next.js frontend
- FastAPI backend
- application PostgreSQL
- Alembic migration scaffold

The local topology also declares dedicated source-role services:

- business PostgreSQL source
- business MSSQL source

Use this document as the source of truth for first local runs. `README.md`
keeps a shorter entrypoint and links back here.

## Current Baseline

SafeQuery currently supports two practical local workflows:

- compose-backed startup for the full baseline stack
- host-shell component checks for the frontend or backend in isolation

The compose-backed path is the baseline because it wires the frontend, backend,
database, and health checks together with the repository's current settings.

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

## 4. Run Migrations

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

## 5. Optional Host-Shell Component Checks

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

## 6. Stop the Stack

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
