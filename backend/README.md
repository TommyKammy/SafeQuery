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

- `SAFEQUERY_DATABASE_URL`

Optional:

- `SAFEQUERY_APP_NAME` defaults to `SafeQuery API`
- `SAFEQUERY_ENVIRONMENT` defaults to `development`
- `SAFEQUERY_CORS_ORIGINS` defaults to `http://localhost:3000`

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

For host-side Alembic commands, point `SAFEQUERY_DATABASE_URL` at a database that
is explicitly reachable from your shell before running Alembic:

```bash
python3 -m pip install -e backend
cd backend
SAFEQUERY_DATABASE_URL="postgresql://safequery:safequery@127.0.0.1:5432/safequery" alembic upgrade head
SAFEQUERY_DATABASE_URL="postgresql://safequery:safequery@127.0.0.1:5432/safequery" alembic current
```
