#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

compose_file="infra/docker-compose.yml"
base_env_file="${SAFEQUERY_SMOKE_ENV_FILE:-.env.example}"
project_name="${SAFEQUERY_REAL_SOURCE_SMOKE_PROJECT_NAME:-safequery-real-source-smoke}"
backend_url="${SAFEQUERY_SMOKE_BACKEND_URL:-http://localhost:8000}"
keep_stack="${SAFEQUERY_SMOKE_KEEP_STACK:-0}"

compose() {
  docker-compose --env-file "$smoke_env_file" -p "$project_name" -f "$compose_file" "$@"
}

cleanup() {
  if [[ "$keep_stack" != "1" ]] \
    && command -v docker-compose >/dev/null 2>&1 \
    && [[ -f "${smoke_env_file:-}" ]] \
    && [[ -f "$compose_file" ]]; then
    compose down -v --remove-orphans >/dev/null || true
  fi
  if [[ -n "${tmp_dir:-}" ]]; then
    rm -rf "$tmp_dir"
  fi
}

smoke_not_run() {
  echo "compose real source execution smoke not run: $*" >&2
  exit 125
}

require_docker_runtime() {
  if ! command -v docker-compose >/dev/null 2>&1; then
    smoke_not_run "docker-compose was not found on PATH"
  fi
  if ! command -v docker >/dev/null 2>&1; then
    smoke_not_run "docker was not found on PATH"
  fi
  if ! docker info >/dev/null 2>&1; then
    smoke_not_run "Docker daemon is unavailable; start Docker or Colima and rerun"
  fi
}

prepare_smoke_env() {
  if [[ ! -f "$base_env_file" ]]; then
    smoke_not_run "base env file $base_env_file is missing"
  fi

  smoke_env_file="$tmp_dir/real-source-smoke.env"
  cp "$base_env_file" "$smoke_env_file"
  cat >>"$smoke_env_file" <<'EOF'

SAFEQUERY_DEV_AUTH_ENABLED=true
SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL=postgresql://source_reader:change-me-for-local-source-topology@business-postgres-source:5432/business
SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING=Driver={ODBC Driver 18 for SQL Server};Server=tcp:business-mssql-source,1433;Database=business;Uid=sa;Pwd=ChangeMeDevOnly_123;Encrypt=no;TrustServerCertificate=yes
EOF
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

  echo "compose real source execution smoke $label failed: $url did not become reachable" >&2
  if [[ -s "$curl_error_file" ]]; then
    sed 's/^/curl: /' "$curl_error_file" >&2
  fi
  return 1
}

seed_real_source_data() {
  echo "compose real source execution smoke: seeding real source containers"
  compose run --rm backend python - <<'PY'
from __future__ import annotations

import os
import re
import time

import psycopg
import pyodbc


def retry(label, operation, attempts=30):
    last_error = None
    for _ in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"{label} did not become ready") from last_error


postgres_url = os.environ["SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL"]


def seed_postgres():
    with psycopg.connect(postgres_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS public.approved_vendors")
            cursor.execute(
                """
                CREATE TABLE public.approved_vendors (
                    vendor_id integer PRIMARY KEY,
                    vendor_name text NOT NULL
                )
                """
            )
            cursor.executemany(
                "INSERT INTO public.approved_vendors (vendor_id, vendor_name) VALUES (%s, %s)",
                [(index, f"pg-vendor-{index:03d}") for index in range(1, 226)],
            )


retry("business PostgreSQL source", seed_postgres)

mssql_connection_string = os.environ["SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING"]
master_connection_string = re.sub(
    r"Database=[^;]+",
    "Database=master",
    mssql_connection_string,
    count=1,
    flags=re.IGNORECASE,
)


def seed_mssql():
    with pyodbc.connect(master_connection_string, autocommit=True) as connection:
        connection.cursor().execute(
            "IF DB_ID(N'business') IS NULL CREATE DATABASE business"
        )

    with pyodbc.connect(mssql_connection_string, autocommit=True) as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            IF OBJECT_ID(N'dbo.approved_vendor_spend', N'U') IS NOT NULL
                DROP TABLE dbo.approved_vendor_spend
            """
        )
        cursor.execute(
            """
            CREATE TABLE dbo.approved_vendor_spend (
                vendor_id int NOT NULL PRIMARY KEY,
                vendor_name nvarchar(128) NOT NULL
            )
            """
        )
        cursor.executemany(
            "INSERT INTO dbo.approved_vendor_spend (vendor_id, vendor_name) VALUES (?, ?)",
            [(index, f"mssql-vendor-{index:03d}") for index in range(1, 226)],
        )


retry("business MSSQL source", seed_mssql)
PY
}

seed_execution_candidates() {
  echo "compose real source execution smoke: seeding approved execution candidates"
  compose run --rm backend python - <<'PY'
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import (
    PreviewCandidate,
    PreviewCandidateApproval,
    PreviewRequest,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.db.session import SessionLocal
from app.services.candidate_lifecycle import CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY
from app.services.demo_source_seed import (
    DEMO_DEV_GOVERNANCE_BINDING,
    DEMO_DEV_SUBJECT_ID,
    seed_demo_source_governance,
)


def upsert_source_governance(
    session,
    *,
    source_uuid: UUID,
    snapshot_uuid: UUID,
    contract_uuid: UUID,
    source_id: str,
    display_label: str,
    source_family: str,
    source_flavor: str,
    connection_reference: str,
) -> tuple[RegisteredSource, SchemaSnapshot, DatasetContract]:
    source = session.get(RegisteredSource, source_uuid)
    if source is None:
        source = RegisteredSource(
            id=source_uuid,
            source_id=source_id,
            display_label=display_label,
            source_family=source_family,
            source_flavor=source_flavor,
            activation_posture=SourceActivationPosture.ACTIVE,
            connection_reference=connection_reference,
        )
        session.add(source)
        session.flush()

    source.source_id = source_id
    source.display_label = display_label
    source.source_family = source_family
    source.source_flavor = source_flavor
    source.activation_posture = SourceActivationPosture.ACTIVE
    source.connection_reference = connection_reference

    snapshot = session.get(SchemaSnapshot, snapshot_uuid)
    if snapshot is None:
        snapshot = SchemaSnapshot(
            id=snapshot_uuid,
            registered_source_id=source.id,
            snapshot_version=1,
            review_status=SchemaSnapshotReviewStatus.APPROVED,
            reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.add(snapshot)
    snapshot.registered_source_id = source.id
    snapshot.snapshot_version = 1
    snapshot.review_status = SchemaSnapshotReviewStatus.APPROVED
    snapshot.reviewed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.flush()

    contract = session.get(DatasetContract, contract_uuid)
    if contract is None:
        contract = DatasetContract(
            id=contract_uuid,
            registered_source_id=source.id,
            schema_snapshot_id=snapshot.id,
            contract_version=1,
            display_name=f"{display_label} contract",
            owner_binding=DEMO_DEV_GOVERNANCE_BINDING,
        )
        session.add(contract)
    contract.registered_source_id = source.id
    contract.schema_snapshot_id = snapshot.id
    contract.contract_version = 1
    contract.display_name = f"{display_label} contract"
    contract.owner_binding = DEMO_DEV_GOVERNANCE_BINDING
    session.flush()

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.flush()
    return source, snapshot, contract


def upsert_candidate(
    session,
    *,
    candidate_uuid: UUID,
    request_uuid: UUID,
    approval_uuid: UUID,
    approval_id: str,
    request_id: str,
    candidate_id: str,
    source: RegisteredSource,
    snapshot: SchemaSnapshot,
    contract: DatasetContract,
    approved_sql: str,
) -> None:
    request = session.get(PreviewRequest, request_uuid)
    if request is None:
        request = PreviewRequest(
            id=request_uuid,
            request_id=request_id,
            registered_source_id=source.id,
            source_id=source.source_id,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
            dataset_contract_id=contract.id,
            dataset_contract_version=contract.contract_version,
            schema_snapshot_id=snapshot.id,
            schema_snapshot_version=snapshot.snapshot_version,
            authenticated_subject_id=DEMO_DEV_SUBJECT_ID,
            auth_source="compose-real-source-smoke",
            session_id="compose-real-source-smoke",
            governance_bindings=DEMO_DEV_GOVERNANCE_BINDING,
            entitlement_decision="allow",
            request_text=f"Smoke execution for {source.source_id}",
            request_state="previewed",
        )
        session.add(request)
    request.registered_source_id = source.id
    request.source_id = source.source_id
    request.source_family = source.source_family
    request.source_flavor = source.source_flavor
    request.dataset_contract_id = contract.id
    request.dataset_contract_version = contract.contract_version
    request.schema_snapshot_id = snapshot.id
    request.schema_snapshot_version = snapshot.snapshot_version
    request.authenticated_subject_id = DEMO_DEV_SUBJECT_ID
    request.governance_bindings = DEMO_DEV_GOVERNANCE_BINDING
    request.entitlement_decision = "allow"
    request.request_state = "previewed"
    session.flush()

    candidate = session.get(PreviewCandidate, candidate_uuid)
    if candidate is None:
        candidate = PreviewCandidate(
            id=candidate_uuid,
            candidate_id=candidate_id,
            preview_request_id=request.id,
            request_id=request.request_id,
            registered_source_id=source.id,
            source_id=source.source_id,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
            dataset_contract_id=contract.id,
            dataset_contract_version=contract.contract_version,
            schema_snapshot_id=snapshot.id,
            schema_snapshot_version=snapshot.snapshot_version,
            authenticated_subject_id=DEMO_DEV_SUBJECT_ID,
            candidate_sql=approved_sql,
            guard_status="allow",
            candidate_state="preview_ready",
        )
        session.add(candidate)
    candidate.preview_request_id = request.id
    candidate.request_id = request.request_id
    candidate.registered_source_id = source.id
    candidate.source_id = source.source_id
    candidate.source_family = source.source_family
    candidate.source_flavor = source.source_flavor
    candidate.dataset_contract_id = contract.id
    candidate.dataset_contract_version = contract.contract_version
    candidate.schema_snapshot_id = snapshot.id
    candidate.schema_snapshot_version = snapshot.snapshot_version
    candidate.authenticated_subject_id = DEMO_DEV_SUBJECT_ID
    candidate.candidate_sql = approved_sql
    candidate.guard_status = "allow"
    candidate.candidate_state = "preview_ready"
    session.flush()

    approval = session.get(PreviewCandidateApproval, approval_uuid)
    if approval is None:
        approval = PreviewCandidateApproval(
            id=approval_uuid,
            approval_id=approval_id,
            preview_candidate_id=candidate.id,
            candidate_id=candidate.candidate_id,
            request_id=request.request_id,
            registered_source_id=source.id,
            source_id=source.source_id,
            source_family=source.source_family,
            source_flavor=source.source_flavor,
            dataset_contract_version=contract.contract_version,
            schema_snapshot_version=snapshot.snapshot_version,
            execution_policy_version=CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY[
                source.source_family
            ],
            approved_sql=approved_sql,
            owner_subject_id=DEMO_DEV_SUBJECT_ID,
            session_id="compose-real-source-smoke",
            approved_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            approval_expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            approval_state="approved",
        )
        session.add(approval)
    approval.preview_candidate_id = candidate.id
    approval.candidate_id = candidate.candidate_id
    approval.request_id = request.request_id
    approval.registered_source_id = source.id
    approval.source_id = source.source_id
    approval.source_family = source.source_family
    approval.source_flavor = source.source_flavor
    approval.dataset_contract_version = contract.contract_version
    approval.schema_snapshot_version = snapshot.snapshot_version
    approval.execution_policy_version = CURRENT_EXECUTION_POLICY_VERSION_BY_SOURCE_FAMILY[
        source.source_family
    ]
    approval.approved_sql = approved_sql
    approval.owner_subject_id = DEMO_DEV_SUBJECT_ID
    approval.session_id = "compose-real-source-smoke"
    approval.approved_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    approval.approval_expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    approval.executed_at = None
    approval.invalidated_at = None
    approval.approval_state = "approved"


with SessionLocal() as session:
    pg_seed = seed_demo_source_governance(session)
    pg_source = session.get(RegisteredSource, pg_seed.source_record_id)
    pg_snapshot = session.get(SchemaSnapshot, pg_seed.schema_snapshot_id)
    pg_contract = session.get(DatasetContract, pg_seed.dataset_contract_id)
    assert pg_source is not None
    assert pg_snapshot is not None
    assert pg_contract is not None

    mssql_source, mssql_snapshot, mssql_contract = upsert_source_governance(
        session,
        source_uuid=UUID("66666666-6666-4666-8666-666666666666"),
        snapshot_uuid=UUID("77777777-7777-4777-8777-777777777777"),
        contract_uuid=UUID("88888888-8888-4888-8888-888888888888"),
        source_id="demo-business-mssql",
        display_label="Demo business MSSQL",
        source_family="mssql",
        source_flavor="sqlserver",
        connection_reference="env:SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING",
    )

    upsert_candidate(
        session,
        candidate_uuid=UUID("99999999-9999-4999-8999-999999999991"),
        request_uuid=UUID("99999999-9999-4999-8999-999999999992"),
        approval_uuid=UUID("99999999-9999-4999-8999-999999999993"),
        approval_id="approval-compose-postgres-real-source",
        request_id="request-compose-postgres-real-source",
        candidate_id="candidate-compose-postgres-real-source",
        source=pg_source,
        snapshot=pg_snapshot,
        contract=pg_contract,
        approved_sql="SELECT vendor_name FROM public.approved_vendors ORDER BY vendor_id",
    )
    upsert_candidate(
        session,
        candidate_uuid=UUID("99999999-9999-4999-8999-999999999994"),
        request_uuid=UUID("99999999-9999-4999-8999-999999999995"),
        approval_uuid=UUID("99999999-9999-4999-8999-999999999996"),
        approval_id="approval-compose-mssql-real-source",
        request_id="request-compose-mssql-real-source",
        candidate_id="candidate-compose-mssql-real-source",
        source=mssql_source,
        snapshot=mssql_snapshot,
        contract=mssql_contract,
        approved_sql="SELECT vendor_name FROM dbo.approved_vendor_spend ORDER BY vendor_id",
    )
    session.commit()
PY
}

write_session_headers() {
  compose run --rm backend python - "$session_headers_file" <<'PY'
from __future__ import annotations

import json
import sys

from app.features.auth.dev import build_dev_authenticated_subject
from app.features.auth.session import create_test_application_session

session = create_test_application_session(build_dev_authenticated_subject())
payload = {
    "csrf_header_name": session.csrf_header_name,
    "csrf_token": session.csrf_token,
    "cookie_name": session.cookie_name,
    "cookie_value": session.cookie_value,
}
with open(sys.argv[1], "w", encoding="utf-8") as output:
    json.dump(payload, output)
PY
}

json_field() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"
}

api_post() {
  local path="$1"
  local body="$2"
  local output_path="$3"
  local status_path="$4"

  local csrf_header_name csrf_token cookie_name cookie_value
  csrf_header_name="$(json_field "$session_headers_file" csrf_header_name)"
  csrf_token="$(json_field "$session_headers_file" csrf_token)"
  cookie_name="$(json_field "$session_headers_file" cookie_name)"
  cookie_value="$(json_field "$session_headers_file" cookie_value)"

  curl --silent --show-error \
    -X POST "$backend_url$path" \
    -H "content-type: application/json" \
    -H "$csrf_header_name: $csrf_token" \
    --cookie "$cookie_name=$cookie_value" \
    --data "$body" \
    --output "$output_path" \
    --write-out "%{http_code}" >"$status_path"
}

assert_status() {
  local label="$1"
  local expected="$2"
  local status_path="$3"
  local body_path="$4"
  local actual

  actual="$(cat "$status_path")"
  if [[ "$actual" != "$expected" ]]; then
    echo "compose real source execution smoke $label failed: expected HTTP $expected, got $actual" >&2
    cat "$body_path" >&2
    return 1
  fi
}

assert_denial_response() {
  local label="$1"
  local expected_code="$2"
  local body_path="$3"

  python3 - "$label" "$expected_code" "$body_path" <<'PY'
import json
import sys

label, expected_code, body_path = sys.argv[1:]
with open(body_path, encoding="utf-8") as body_file:
    payload = json.load(body_file)
actual_code = payload.get("error", {}).get("code")
if actual_code != expected_code:
    raise SystemExit(
        f"compose real source execution smoke {label} failed: "
        f"expected error code {expected_code}, got {actual_code}"
    )
PY
}

assert_execution_response() {
  local label="$1"
  local expected_source="$2"
  local expected_connector="$3"
  local body_path="$4"

  python3 - "$label" "$expected_source" "$expected_connector" "$body_path" <<'PY'
import json
import sys

label, expected_source, expected_connector, body_path = sys.argv[1:]
with open(body_path, encoding="utf-8") as body_file:
    payload = json.load(body_file)

metadata = payload.get("metadata", {})
events = payload.get("audit", {}).get("events", [])
completed_event = events[-1] if events else {}
checks = {
    "source_id": payload.get("source_id") == expected_source,
    "connector_id": payload.get("connector_id") == expected_connector,
    "ownership": payload.get("ownership") == "backend",
    "row_count": metadata.get("row_count") == 200,
    "row_limit": metadata.get("row_limit") == 200,
    "result_truncated": metadata.get("result_truncated") is True,
    "truncation_reason": metadata.get("truncation_reason") == "row_limit",
    "audit_event_type": completed_event.get("event_type") == "execution_completed",
    "audit_row_count": completed_event.get("execution_row_count") == metadata.get("row_count"),
    "audit_truncation": completed_event.get("result_truncated") is True,
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit(
        f"compose real source execution smoke {label} failed checks {failed}: "
        f"{json.dumps(payload, sort_keys=True)}"
    )
PY
}

assert_persisted_audit() {
  echo "compose real source execution smoke: checking persisted execution audit"
  compose run --rm backend python - <<'PY'
from __future__ import annotations

from sqlalchemy import select

from app.db.models.preview import PreviewAuditEvent
from app.db.session import SessionLocal

expected = {
    "candidate-compose-postgres-real-source": "demo-business-postgres",
    "candidate-compose-mssql-real-source": "demo-business-mssql",
}
with SessionLocal() as session:
    for candidate_id, source_id in expected.items():
        events = (
            session.execute(
                select(PreviewAuditEvent)
                .where(PreviewAuditEvent.candidate_id == candidate_id)
                .order_by(PreviewAuditEvent.lifecycle_order)
            )
            .scalars()
            .all()
        )
        event_types = [event.event_type for event in events]
        if event_types != [
            "execution_requested",
            "execution_started",
            "execution_completed",
        ]:
            raise SystemExit(
                f"candidate {candidate_id} persisted event types were {event_types}"
            )
        completed = events[-1]
        if completed.source_id != source_id:
            raise SystemExit(
                f"candidate {candidate_id} persisted source was {completed.source_id}"
            )
        if completed.audit_payload.get("execution_row_count") != 200:
            raise SystemExit(
                f"candidate {candidate_id} persisted row count was "
                f"{completed.audit_payload.get('execution_row_count')}"
            )
        if completed.audit_payload.get("result_truncated") is not True:
            raise SystemExit(
                f"candidate {candidate_id} persisted truncation was "
                f"{completed.audit_payload.get('result_truncated')}"
            )
PY
}

run_compose_real_source_execution_smoke() {
  require_docker_runtime

  if [[ ! -f "$compose_file" ]]; then
    echo "compose real source execution smoke setup failed: missing $compose_file" >&2
    exit 1
  fi

  tmp_dir="$(mktemp -d)"
  response_file="$tmp_dir/response.json"
  curl_error_file="$tmp_dir/curl.err"
  session_headers_file="$tmp_dir/session.json"
  trap cleanup EXIT
  prepare_smoke_env

  echo "compose real source execution smoke: resetting disposable compose project"
  compose down -v --remove-orphans >/dev/null

  echo "compose real source execution smoke: starting baseline stack"
  compose up --build -d

  echo "compose real source execution smoke: applying migrations"
  compose run --rm backend alembic upgrade head

  wait_for_http "backend health" "$backend_url/health" 30
  seed_real_source_data
  seed_execution_candidates
  write_session_headers

  api_post \
    "/candidates/candidate-compose-postgres-real-source/execute" \
    '{"selected_source_id":"demo-business-mssql"}' \
    "$tmp_dir/wrong-source.json" \
    "$tmp_dir/wrong-source.status"
  assert_status "wrong-source candidate binding" "403" "$tmp_dir/wrong-source.status" "$tmp_dir/wrong-source.json"
  assert_denial_response "wrong-source candidate binding" "execution_denied" "$tmp_dir/wrong-source.json"

  api_post \
    "/candidates/candidate-compose-postgres-real-source/execute" \
    '{"selected_source_id":"demo-business-postgres","canonical_sql":"SELECT 1"}' \
    "$tmp_dir/raw-sql.json" \
    "$tmp_dir/raw-sql.status"
  assert_status "raw SQL rejection" "422" "$tmp_dir/raw-sql.status" "$tmp_dir/raw-sql.json"
  assert_denial_response "raw SQL rejection" "invalid_request" "$tmp_dir/raw-sql.json"

  api_post \
    "/candidates/candidate-compose-postgres-real-source/execute" \
    '{"selected_source_id":"demo-business-postgres"}' \
    "$tmp_dir/postgres-execute.json" \
    "$tmp_dir/postgres-execute.status"
  assert_status "PostgreSQL candidate execution" "200" "$tmp_dir/postgres-execute.status" "$tmp_dir/postgres-execute.json"
  assert_execution_response "PostgreSQL candidate execution" "demo-business-postgres" "postgresql_readonly" "$tmp_dir/postgres-execute.json"

  api_post \
    "/candidates/candidate-compose-mssql-real-source/execute" \
    '{"selected_source_id":"demo-business-mssql"}' \
    "$tmp_dir/mssql-execute.json" \
    "$tmp_dir/mssql-execute.status"
  assert_status "MSSQL candidate execution" "200" "$tmp_dir/mssql-execute.status" "$tmp_dir/mssql-execute.json"
  assert_execution_response "MSSQL candidate execution" "demo-business-mssql" "mssql_readonly" "$tmp_dir/mssql-execute.json"

  assert_persisted_audit
  echo "compose real source execution smoke: passed"
}

if [[ "${SAFEQUERY_SMOKE_SOURCE_ONLY:-0}" != "1" ]]; then
  run_compose_real_source_execution_smoke
fi
