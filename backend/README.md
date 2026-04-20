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
