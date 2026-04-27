from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.services.first_run_doctor as first_run_doctor_service
from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.source_registry import RegisteredSource
from app.services.demo_source_seed import DEMO_SOURCE_UUID, seed_demo_source_governance
from app.services.first_run_doctor import HttpProbeResponse, run_first_run_doctor


@contextmanager
def _session_scope() -> Iterator[Session]:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(255))"))
        session.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('0009_candidate_approval_records')"
            )
        )
        session.commit()
        yield session


def _doctor_sections(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    checks = payload["checks"]
    assert isinstance(checks, list)
    return {
        str(check["name"]): check
        for check in checks
        if isinstance(check, dict) and "name" in check
    }


def _ready_surface_probes() -> dict[str, object]:
    return {
        "backend_probe": lambda _url: HttpProbeResponse(
            status_code=200,
            body='{"status":"ok","service":"safequery-api"}',
            content_type="application/json",
        ),
        "frontend_probe": lambda _url: HttpProbeResponse(
            status_code=200,
            body="<html><head><title>SafeQuery Query Workflow</title></head></html>",
            content_type="text/html",
        ),
    }


def _expected_runtime_posture(source_family: str) -> dict[str, object]:
    return {
        "source_family": source_family,
        "rollout_status": "active_baseline",
        "preview_timeout_seconds": 30,
        "guard_timeout_seconds": 30,
        "execute_timeout_seconds": 30,
        "retryable_unavailable_states": [
            "connection_timeout",
            "source_unreachable",
            "transient_driver_unavailable",
        ],
        "non_retryable_workflow_states": [
            "malformed_request",
            "policy_denied",
            "source_binding_mismatch",
            "unsupported_source_binding",
            "guard_denied",
        ],
        "retry_attempts": 1,
        "retry_backoff": "none_inside_authoritative_execution_boundary",
        "pool_boundary": "per_registered_source",
        "pool_sharing": "no_cross_source_or_application_postgres_reuse",
        "pool_owner": "backend",
    }


def test_http_probe_rejects_non_http_schemes_before_urlopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("urlopen should not be called for rejected schemes")

    monkeypatch.setattr(first_run_doctor_service, "urlopen", fail_if_called)

    with pytest.raises(ValueError, match="Only HTTP"):
        first_run_doctor_service._http_get("file:///tmp/safequery-first-run")


def test_first_run_doctor_fails_closed_when_migration_state_is_missing() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["migrations"]["status"] == "fail"
    assert "Alembic migration state is missing" in sections["migrations"]["message"]


def test_first_run_doctor_fails_closed_when_migration_metadata_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_head_lookup_error() -> set[str]:
        raise RuntimeError("missing scripts")

    monkeypatch.setattr(
        first_run_doctor_service,
        "_alembic_heads",
        raise_head_lookup_error,
    )

    with _session_scope() as session:
        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["migrations"]["status"] == "fail"
    assert "Unable to read Alembic migration metadata" in sections["migrations"][
        "message"
    ]
    assert sections["migrations"]["detail"] == {
        "error": "RuntimeError",
        "applied_revisions": ["0009_candidate_approval_records"],
    }
    assert "source_registry" in sections


def test_first_run_doctor_passes_after_demo_seed() -> None:
    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            backend_base_url="http://localhost:8000",
            frontend_base_url="http://localhost:3000",
            **_ready_surface_probes(),
        )

    payload = result.model_dump(mode="json")
    sections = _doctor_sections(payload)
    assert payload["status"] == "pass"
    assert sections["database"]["status"] == "pass"
    assert sections["migrations"]["status"] == "pass"
    assert sections["source_registry"]["status"] == "pass"
    assert sections["dataset_contract"]["status"] == "pass"
    assert sections["schema_snapshot"]["status"] == "pass"
    assert sections["entitlement_seed"]["status"] == "pass"
    assert sections["execution_connector"]["status"] == "pass"
    assert sections["execution_connector"]["detail"] == {
        "source_id": "demo-business-postgres",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "connector_id": "postgresql_readonly",
        "ownership": "backend",
        "runtime_posture": _expected_runtime_posture("postgresql"),
        "runtime_status": "available",
        "runtime": {"dict_row": "available", "psycopg": "available"},
    }
    assert sections["backend"]["status"] == "pass"
    assert sections["frontend"]["status"] == "pass"


def test_first_run_doctor_fails_when_backend_url_is_unreachable() -> None:
    def unreachable_backend(_url: str) -> HttpProbeResponse:
        raise TimeoutError("connection timed out")

    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            backend_base_url="http://backend.invalid",
            frontend_base_url="http://localhost:3000",
            backend_probe=unreachable_backend,
            frontend_probe=lambda _url: HttpProbeResponse(
                status_code=200,
                body="<html><head><title>SafeQuery Query Workflow</title></head></html>",
                content_type="text/html",
            ),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["backend"]["status"] == "fail"
    assert "Backend health endpoint is not reachable" in sections["backend"]["message"]
    assert sections["backend"]["detail"] == {
        "health_url": "http://backend.invalid/health",
        "error": "TimeoutError",
    }
    assert sections["frontend"]["status"] == "pass"


def test_first_run_doctor_fails_when_backend_health_response_is_unhealthy() -> None:
    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            backend_base_url="http://localhost:8000",
            frontend_base_url="http://localhost:3000",
            backend_probe=lambda _url: HttpProbeResponse(
                status_code=503,
                body='{"status":"degraded","service":"safequery-api"}',
                content_type="application/json",
            ),
            frontend_probe=lambda _url: HttpProbeResponse(
                status_code=200,
                body="<html><head><title>SafeQuery Query Workflow</title></head></html>",
                content_type="text/html",
            ),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["backend"]["status"] == "fail"
    assert "Backend health endpoint returned an unhealthy response" in sections[
        "backend"
    ]["message"]
    assert sections["backend"]["detail"] == {
        "health_url": "http://localhost:8000/health",
        "status_code": 503,
        "health_status": "degraded",
    }


def test_first_run_doctor_fails_when_frontend_url_is_unreachable() -> None:
    def unreachable_frontend(_url: str) -> HttpProbeResponse:
        raise ConnectionError("connection refused")

    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            backend_base_url="http://localhost:8000",
            frontend_base_url="http://frontend.invalid",
            backend_probe=lambda _url: HttpProbeResponse(
                status_code=200,
                body='{"status":"ok","service":"safequery-api"}',
                content_type="application/json",
            ),
            frontend_probe=unreachable_frontend,
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["backend"]["status"] == "pass"
    assert sections["frontend"]["status"] == "fail"
    assert "Frontend app surface is not reachable" in sections["frontend"]["message"]
    assert sections["frontend"]["detail"] == {
        "frontend_url": "http://frontend.invalid",
        "backend_base_url": "http://localhost:8000",
        "error": "ConnectionError",
    }


def test_first_run_doctor_fails_when_frontend_surface_is_unexpected() -> None:
    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            backend_base_url="http://localhost:8000",
            frontend_base_url="http://localhost:3000",
            backend_probe=lambda _url: HttpProbeResponse(
                status_code=200,
                body='{"status":"ok","service":"safequery-api"}',
                content_type="application/json",
            ),
            frontend_probe=lambda _url: HttpProbeResponse(
                status_code=200,
                body="<html><head><title>Placeholder</title></head></html>",
                content_type="text/html",
            ),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["frontend"]["status"] == "fail"
    assert "Frontend did not return the SafeQuery app surface" in sections["frontend"][
        "message"
    ]
    assert sections["frontend"]["detail"] == {
        "frontend_url": "http://localhost:3000",
        "backend_base_url": "http://localhost:8000",
        "status_code": 200,
    }


def test_first_run_doctor_prefers_backend_probe_url_over_public_api_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_urls: list[str] = []

    def backend_probe(url: str) -> HttpProbeResponse:
        seen_urls.append(url)
        return HttpProbeResponse(
            status_code=200,
            body='{"status":"ok","service":"safequery-api"}',
            content_type="application/json",
        )

    monkeypatch.setenv("SAFEQUERY_BACKEND_BASE_URL", "http://backend:8000")
    monkeypatch.setenv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("SAFEQUERY_FRONTEND_BASE_URL", "http://frontend:3000")

    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            backend_probe=backend_probe,
            frontend_probe=lambda _url: HttpProbeResponse(
                status_code=200,
                body="<html><head><title>SafeQuery Query Workflow</title></head></html>",
                content_type="text/html",
            ),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "pass"
    assert seen_urls == ["http://backend:8000/health"]
    assert sections["frontend"]["detail"] == {
        "frontend_url": "http://frontend:3000",
        "backend_base_url": "http://backend:8000",
        "status_code": 200,
    }


def test_first_run_doctor_can_report_api_route_backend_without_cli_probe() -> None:
    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            backend_base_url="http://browser-facing-backend.invalid",
            frontend_base_url="http://localhost:3000",
            backend_probe_mode="served_route",
            frontend_probe=lambda _url: HttpProbeResponse(
                status_code=200,
                body="<html><head><title>SafeQuery Query Workflow</title></head></html>",
                content_type="text/html",
            ),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "pass"
    assert sections["backend"]["status"] == "pass"
    assert "doctor route is serving this response" in sections["backend"]["message"]
    assert sections["backend"]["detail"] == {
        "doctor_route": "/doctor/first-run",
        "backend_base_url": "http://browser-facing-backend.invalid",
    }


def test_first_run_doctor_fails_closed_when_demo_source_connector_binding_drifts() -> None:
    with _session_scope() as session:
        seed_demo_source_governance(session)
        source = session.get(RegisteredSource, DEMO_SOURCE_UUID)
        assert source is not None
        source.source_flavor = "demo"
        session.commit()

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["source_registry"]["status"] == "pass"
    assert sections["dataset_contract"]["status"] == "pass"
    assert sections["schema_snapshot"]["status"] == "pass"
    assert sections["entitlement_seed"]["status"] == "pass"
    assert sections["execution_connector"]["status"] == "fail"
    assert sections["execution_connector"]["detail"] == {
        "source_id": "demo-business-postgres",
        "source_family": "postgresql",
        "source_flavor": "demo",
        "deny_code": "DENY_UNSUPPORTED_SOURCE_BINDING",
    }


def test_first_run_doctor_fails_closed_when_postgresql_driver_runtime_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_postgresql_runtime() -> dict[str, object]:
        raise first_run_doctor_service.PostgreSQLExecutionRuntimeUnavailable(
            "psycopg must be installed and importable before the PostgreSQL "
            "execution connector can run."
        )

    monkeypatch.setattr(
        first_run_doctor_service,
        "check_postgresql_execution_runtime_readiness",
        unavailable_postgresql_runtime,
        raising=False,
    )

    with _session_scope() as session:
        seed_demo_source_governance(session)

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["execution_connector"]["status"] == "fail"
    assert sections["execution_connector"]["message"] == (
        "PostgreSQL driver runtime is unavailable for the backend-owned "
        "execution connector."
    )
    assert sections["execution_connector"]["detail"] == {
        "source_id": "demo-business-postgres",
        "source_family": "postgresql",
        "source_flavor": "warehouse",
        "connector_id": "postgresql_readonly",
        "ownership": "backend",
        "runtime_status": "unavailable",
        "error": "PostgreSQLExecutionRuntimeUnavailable",
        "runtime_posture": _expected_runtime_posture("postgresql"),
        "runtime_dependency": "psycopg",
    }


def test_first_run_doctor_fails_closed_when_mssql_driver_runtime_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_mssql_runtime() -> dict[str, object]:
        raise first_run_doctor_service.MSSQLExecutionRuntimeUnavailable(
            "ODBC Driver 18 for SQL Server must be installed before the MSSQL "
            "execution connector can run."
        )

    monkeypatch.setattr(
        first_run_doctor_service,
        "check_mssql_execution_runtime_readiness",
        unavailable_mssql_runtime,
    )

    check = first_run_doctor_service._check_execution_connector(
        SimpleNamespace(
            source_id="business-mssql-source",
            source_family="mssql",
            source_flavor="sqlserver",
        ),
        SimpleNamespace(contract_version=3),
        SimpleNamespace(snapshot_version=7),
    )

    assert check.model_dump(mode="json") == {
        "name": "execution_connector",
        "status": "fail",
        "message": (
            "MSSQL driver runtime is unavailable for the backend-owned "
            "execution connector."
        ),
        "detail": {
            "source_id": "business-mssql-source",
            "source_family": "mssql",
            "source_flavor": "sqlserver",
            "connector_id": "mssql_readonly",
            "ownership": "backend",
            "runtime_status": "unavailable",
            "error": "MSSQLExecutionRuntimeUnavailable",
            "runtime_posture": _expected_runtime_posture("mssql"),
            "runtime_dependency": "pyodbc/odbc-driver-18",
        },
    }


def test_first_run_doctor_fails_closed_when_source_seed_is_missing() -> None:
    with _session_scope() as session:
        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["source_registry"]["status"] == "fail"
    assert "Run `python -m app.cli.seed_demo_source`" in sections["source_registry"][
        "message"
    ]


def test_first_run_doctor_fails_closed_when_source_governance_tables_are_missing() -> None:
    with _session_scope() as session:
        session.execute(text("DROP TABLE registered_sources"))
        session.commit()

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["source_registry"]["status"] == "fail"
    assert sections["source_registry"]["detail"] == {"error": "OperationalError"}
    assert sections["dataset_contract"]["status"] == "fail"
    assert sections["schema_snapshot"]["status"] == "fail"
    assert sections["entitlement_seed"]["status"] == "fail"
    assert sections["execution_connector"]["status"] == "fail"
    assert sections["backend"]["status"] == "pass"
    assert sections["frontend"]["status"] == "pass"


def test_first_run_doctor_fails_closed_when_contract_or_snapshot_link_is_missing() -> None:
    with _session_scope() as session:
        seed_demo_source_governance(session)
        source = session.get(RegisteredSource, DEMO_SOURCE_UUID)
        assert source is not None
        source.dataset_contract_id = None
        source.schema_snapshot_id = None
        session.commit()

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["dataset_contract"]["status"] == "fail"
    assert sections["schema_snapshot"]["status"] == "fail"


def test_first_run_doctor_fails_closed_when_entitlement_seed_is_missing() -> None:
    with _session_scope() as session:
        seed_demo_source_governance(session)
        source = session.get(RegisteredSource, DEMO_SOURCE_UUID)
        assert source is not None
        contract = session.get(DatasetContract, source.dataset_contract_id)
        assert contract is not None
        contract.owner_binding = None
        session.commit()

        result = run_first_run_doctor(
            session,
            database_probe=lambda: None,
            **_ready_surface_probes(),
        )

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["entitlement_seed"]["status"] == "fail"
    assert "dev/local entitlement seed" in sections["entitlement_seed"]["message"]
