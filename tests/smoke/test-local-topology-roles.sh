#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

tmp_env="$(mktemp)"
trap 'rm -f "$tmp_env"' EXIT
cp .env.example "$tmp_env"

rendered_compose="$(docker-compose --env-file "$tmp_env" -f infra/docker-compose.yml config)"

missing=0

required_compose_patterns=(
  "app-postgres:"
  "business-postgres-source:"
  "business-mssql-source:"
  "SAFEQUERY_APP_POSTGRES_URL: postgresql://safequery:safequery@app-postgres:5432/safequery"
  "MSSQL_SA_PASSWORD: ChangeMeDevOnly_123"
  "app_postgres_data:"
  "business_postgres_source_data:"
)

for pattern in "${required_compose_patterns[@]}"; do
  if ! grep -Fq "$pattern" <<<"$rendered_compose"; then
    echo "missing required topology pattern in rendered compose config: $pattern" >&2
    missing=1
  fi
done

if grep -Eq '^  postgres:$' <<<"$rendered_compose"; then
  echo "found ambiguous baseline topology service name in rendered compose config" >&2
  missing=1
fi

if grep -Eq '^  postgres_data:$' <<<"$rendered_compose"; then
  echo "found ambiguous baseline topology volume name in rendered compose config" >&2
  missing=1
fi

if grep -Fq "@postgres:5432" <<<"$rendered_compose"; then
  echo "found ambiguous baseline topology hostname in rendered compose config: @postgres:5432" >&2
  missing=1
fi

required_env_patterns=(
  "SAFEQUERY_APP_POSTGRES_URL=postgresql://safequery:safequery@app-postgres:5432/safequery"
  "# SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL=postgresql://source_reader:change-me-for-local-source-topology@business-postgres-source:5432/business"
  "# SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING=Driver={ODBC Driver 18 for SQL Server};Server=tcp:business-mssql-source,1433;Database=business;Uid=sa;Pwd=ChangeMeDevOnly_123;Encrypt=no;TrustServerCertificate=yes"
)

for pattern in "${required_env_patterns[@]}"; do
  if ! grep -Fq "$pattern" .env.example; then
    echo "missing required topology pattern in .env.example: $pattern" >&2
    missing=1
  fi
done

required_doc_patterns=(
  "application PostgreSQL"
  "business PostgreSQL source"
  "business MSSQL source"
  "app-postgres"
  "business-postgres-source"
  "business-mssql-source"
)

for pattern in "${required_doc_patterns[@]}"; do
  if ! grep -Fq "$pattern" docs/local-development.md; then
    echo "missing required topology pattern in docs/local-development.md: $pattern" >&2
    missing=1
  fi
done

exit "$missing"
