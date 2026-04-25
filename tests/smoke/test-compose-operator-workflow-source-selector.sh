#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

compose_file="infra/docker-compose.yml"
env_file="${SAFEQUERY_SMOKE_ENV_FILE:-.env}"
project_name="${SAFEQUERY_SMOKE_PROJECT_NAME:-safequery-k5-smoke}"
backend_url="${SAFEQUERY_SMOKE_BACKEND_URL:-http://localhost:8000}"
frontend_url="${SAFEQUERY_SMOKE_FRONTEND_URL:-http://localhost:3000}"
keep_stack="${SAFEQUERY_SMOKE_KEEP_STACK:-0}"

compose() {
  docker-compose --env-file "$env_file" -p "$project_name" -f "$compose_file" "$@"
}

cleanup() {
  if [[ -n "${tmp_dir:-}" ]]; then
    rm -rf "$tmp_dir"
  fi
  if [[ "$keep_stack" != "1" ]]; then
    compose down -v --remove-orphans >/dev/null
  fi
}

smoke_sleep() {
  sleep "$1"
}

wait_for_http() {
  local label="$1"
  local url="$2"
  local attempts="${3:-30}"

  for _ in $(seq 1 "$attempts"); do
    if curl --fail --silent --show-error "$url" >"$response_file" 2>"$curl_error_file"; then
      return 0
    fi
    sleep 2
  done

  echo "compose smoke $label failed: $url did not become reachable" >&2
  if [[ -s "$curl_error_file" ]]; then
    sed 's/^/curl: /' "$curl_error_file" >&2
  fi
  return 1
}

doctor_status_passes() {
  local url="$1"
  local response_path="$2"

  python3 - "$url" "$response_path" <<'PY'
import json
import sys

url = sys.argv[1]
response_path = sys.argv[2]
with open(response_path, encoding="utf-8") as response_file:
    payload = json.load(response_file)
if payload.get("status") != "pass":
    failing = [
        {
            "name": check.get("name"),
            "status": check.get("status"),
            "message": check.get("message"),
        }
        for check in payload.get("checks", [])
        if check.get("status") != "pass"
    ]
    raise SystemExit(
        "compose smoke first-run doctor failed: "
        f"{url} reported {json.dumps(failing, sort_keys=True)}"
    )
PY
}

wait_for_first_run_doctor() {
  local url="$1"
  local attempts="${2:-30}"
  local latest_error_file="$tmp_dir/doctor.err"

  : >"$latest_error_file"
  for attempt in $(seq 1 "$attempts"); do
    if curl --fail --silent --show-error "$url" >"$response_file" 2>"$curl_error_file"; then
      if doctor_status_passes "$url" "$response_file" 2>"$latest_error_file"; then
        return 0
      fi
    else
      {
        echo "compose smoke first-run doctor failed: $url did not become reachable"
        if [[ -s "$curl_error_file" ]]; then
          sed 's/^/curl: /' "$curl_error_file"
        fi
      } >"$latest_error_file"
    fi

    if [[ "$attempt" -lt "$attempts" ]]; then
      smoke_sleep 2
    fi
  done

  echo "compose smoke first-run doctor failed: $url did not report status pass after $attempts attempts" >&2
  if [[ -s "$latest_error_file" ]]; then
    sed 's/^/doctor: /' "$latest_error_file" >&2
  fi
  return 1
}

run_compose_source_selector_smoke() {
  tmp_dir="$(mktemp -d)"
  response_file="$tmp_dir/response.json"
  curl_error_file="$tmp_dir/curl.err"
  frontend_file="$tmp_dir/frontend.html"

  if ! command -v docker-compose >/dev/null 2>&1; then
    echo "compose smoke unavailable: docker-compose was not found on PATH" >&2
    exit 127
  fi

  if [[ ! -f "$compose_file" ]]; then
    echo "compose smoke setup failed: missing $compose_file" >&2
    exit 1
  fi

  if [[ ! -f "$env_file" ]]; then
    echo "compose smoke setup failed: missing $env_file; copy .env.example to .env" >&2
    exit 1
  fi

  trap cleanup EXIT

  echo "compose smoke: resetting disposable compose project"
  compose down -v --remove-orphans >/dev/null

  echo "compose smoke: starting baseline stack"
  compose up --build -d

  echo "compose smoke: applying migrations"
  if ! compose run --rm backend alembic upgrade head; then
    echo "compose smoke migration failed: alembic upgrade head did not complete" >&2
    exit 1
  fi

  if ! compose run --rm backend alembic current; then
    echo "compose smoke migration failed: alembic current did not complete" >&2
    exit 1
  fi

  echo "compose smoke: seeding demo source governance"
  if ! compose run --rm backend python -m app.cli.seed_demo_source; then
    echo "compose smoke seed failed: python -m app.cli.seed_demo_source did not complete" >&2
    exit 1
  fi

  echo "compose smoke: checking backend health"
  wait_for_http "backend health" "$backend_url/health" 30
  python3 - "$backend_url/health" "$response_file" <<'PY'
import json
import sys

url = sys.argv[1]
response_path = sys.argv[2]
with open(response_path, encoding="utf-8") as response_file:
    payload = json.load(response_file)
if payload.get("status") != "ok" or payload.get("database", {}).get("status") != "ok":
    raise SystemExit(
        f"compose smoke backend health failed: {url} returned {json.dumps(payload, sort_keys=True)}"
    )
PY

  echo "compose smoke: checking first-run doctor"
  wait_for_first_run_doctor "$backend_url/doctor/first-run" 30

  echo "compose smoke: checking operator workflow source selector"
  wait_for_http "operator workflow" "$backend_url/operator/workflow" 10
  python3 - "$backend_url/operator/workflow" "$response_file" <<'PY'
import json
import sys

url = sys.argv[1]
response_path = sys.argv[2]
with open(response_path, encoding="utf-8") as response_file:
    payload = json.load(response_file)
sources = payload.get("sources")
if not isinstance(sources, list):
    raise SystemExit(f"compose smoke contract failed: {url} did not return a sources array")

active_sources = [
    source
    for source in sources
    if isinstance(source, dict)
    and source.get("activationPosture") == "active"
    and isinstance(source.get("sourceId"), str)
    and source.get("sourceId")
    and isinstance(source.get("displayLabel"), str)
    and source.get("displayLabel")
]

if not active_sources:
    source_summary = [
        {
            "sourceId": source.get("sourceId") if isinstance(source, dict) else None,
            "activationPosture": source.get("activationPosture") if isinstance(source, dict) else None,
        }
        for source in sources
    ]
    raise SystemExit(
        "compose smoke contract failed: /operator/workflow returned no active source "
        f"selector options: {json.dumps(source_summary, sort_keys=True)}"
    )

print(
    "compose smoke: operator workflow exposes active source selector option "
    f"{active_sources[0]['sourceId']}"
)
PY

  echo "compose smoke: checking frontend reachability"
  if ! curl --fail --silent --show-error "$frontend_url" >"$frontend_file"; then
    echo "compose smoke frontend failed: $frontend_url was not reachable" >&2
    exit 1
  fi

  if ! grep -Fq "__NEXT_DATA__" "$frontend_file"; then
    echo "compose smoke frontend failed: $frontend_url did not return a Next.js page" >&2
    exit 1
  fi

  echo "compose smoke: first-run operator workflow source selector passed"
}

if [[ "${SAFEQUERY_SMOKE_SOURCE_ONLY:-0}" != "1" ]]; then
  run_compose_source_selector_smoke
fi
