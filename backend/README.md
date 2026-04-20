# SafeQuery Backend Baseline

This package contains the minimum FastAPI baseline for SafeQuery.

Current scope:

- root API placeholder
- PostgreSQL-backed `/health` endpoint
- Alembic migration scaffold with a baseline revision
- explicit package seams for auth, guard, execution, and audit work

Not implemented yet:

- authentication and sessions
- SQL generation
- SQL guard
- SQL execution
- audit persistence

## Configuration

The backend loads typed application settings through `app.core.config.Settings`.

Required:

- `SAFEQUERY_APP_POSTGRES_URL`

Optional:

- `SAFEQUERY_APP_NAME` defaults to `SafeQuery API`
- `SAFEQUERY_ENVIRONMENT` defaults to `development`
- `SAFEQUERY_CORS_ORIGINS` defaults to `http://localhost:3000`
- `SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL` reserves a distinct business
  PostgreSQL source identity for later generation-context work
- `SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING` reserves a distinct MSSQL
  execution identity for later execution-path work

Settings load from `.env` or `../.env`, which keeps the repository-level local
startup path and direct backend commands aligned.

For standalone backend commands, copy `backend/.env.example` to `backend/.env`
or export the variables in your shell before starting the app or Alembic.

## Migration Commands

The compose-backed command path is the baseline workflow because the repository's
PostgreSQL service is intentionally kept on the compose network only:

```bash
docker-compose -f infra/docker-compose.yml run --rm backend alembic upgrade head
docker-compose -f infra/docker-compose.yml run --rm backend alembic current
```

For host-side Alembic commands, point `SAFEQUERY_APP_POSTGRES_URL` at a
database that is explicitly reachable from your shell before running Alembic:

```bash
python3 -m pip install -e backend
cd backend
SAFEQUERY_APP_POSTGRES_URL="postgresql://safequery:change-me-for-shared-environments@127.0.0.1:5432/safequery" alembic upgrade head
SAFEQUERY_APP_POSTGRES_URL="postgresql://safequery:change-me-for-shared-environments@127.0.0.1:5432/safequery" alembic current
```

The backend treats those names as separate identities:

- application persistence: `application_postgres_persistence`
- business PostgreSQL generation source:
  `business_postgres_source_generation`
- business MSSQL execution source: `business_mssql_source_execution`

If later code asks for either business-source configuration before the matching
source-specific variable is set, settings access fails closed with an explicit
runtime error instead of guessing or reusing the application database secret.
