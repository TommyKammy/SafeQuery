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

1. Start the local stack:

```bash
docker-compose -f infra/docker-compose.yml up --build -d
```

2. Confirm the UI is reachable:

```bash
curl -I http://localhost:3000
```

3. Confirm the API health endpoint is reachable and healthy:

```bash
curl http://localhost:8000/health
```

PostgreSQL stays on the compose network only for this baseline. The app stack reaches it internally, which avoids common host-port conflicts during local startup.

If your Docker shell is pointed at a stale Colima socket, scope the command to the active profile instead of changing global settings:

```bash
DOCKER_HOST=unix:///Users/$USER/.colima/default/docker.sock docker-compose -f infra/docker-compose.yml up --build -d
```

4. Stop the stack when finished:

```bash
docker-compose -f infra/docker-compose.yml down
```

To remove the PostgreSQL volume as well:

```bash
docker-compose -f infra/docker-compose.yml down -v
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
cd frontend && npm install && npm run build
cd ../backend && python3 -m pip install -e .
```
