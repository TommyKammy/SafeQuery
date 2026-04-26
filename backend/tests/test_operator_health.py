from __future__ import annotations

import importlib
from contextlib import contextmanager
from typing import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import require_preview_submission_session
from app.services.demo_source_seed import seed_demo_source_governance


@contextmanager
def _session_scope() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_demo_source_governance(session)
        yield session
    engine.dispose()


def _client(session: Session) -> TestClient:
    get_settings.cache_clear()
    main_module = importlib.import_module("app.main")
    app = main_module.create_app()
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    return TestClient(app)


def test_health_exposes_bounded_operator_aggregate_without_sensitive_fields(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:safequery@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "disabled")
    get_settings.cache_clear()
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "check_database_health",
        lambda _url: {"status": "ok", "detail": "ready"},
    )

    with _session_scope() as session:
        response = _client(session).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["operator_health"] == {
        "status": "ok",
        "can_authorize_execution": False,
        "components": {
            "backend": {"status": "ok", "detail": "ready"},
            "frontend_api_connection": {"status": "ok", "detail": "reachable"},
            "source_registry": {
                "status": "ok",
                "detail": "ready",
                "registered_source_count": 1,
                "active_source_count": 1,
                "postures": {
                    "active": 1,
                    "blocked": 0,
                    "paused": 0,
                    "retired": 0,
                },
            },
            "active_source_connectivity": {
                "status": "ok",
                "detail": "ready",
                "active_source_count": 1,
                "ready_source_count": 1,
                "unavailable_source_count": 0,
            },
            "generation_adapter": {
                "status": "disabled",
                "detail": "provider_disabled",
                "provider": "disabled",
            },
            "audit_persistence": {
                "status": "ok",
                "detail": "ready",
            },
        },
    }
    assert "connection_reference" not in response.text
    assert "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL" not in response.text
    assert "postgresql://" not in response.text
    assert "/Users/" not in response.text


def test_health_degrades_operator_aggregate_when_sources_are_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:safequery@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "disabled")
    get_settings.cache_clear()
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "check_database_health",
        lambda _url: {"status": "ok", "detail": "ready"},
    )

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        response = _client(session).get("/health")
    engine.dispose()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["operator_health"]["status"] == "degraded"
    assert payload["operator_health"]["can_authorize_execution"] is False
    assert payload["operator_health"]["components"]["source_registry"] == {
        "status": "degraded",
        "detail": "no_active_sources",
        "registered_source_count": 0,
        "active_source_count": 0,
        "postures": {
            "active": 0,
            "blocked": 0,
            "paused": 0,
            "retired": 0,
        },
    }
    assert payload["operator_health"]["components"]["active_source_connectivity"] == {
        "status": "degraded",
        "detail": "no_active_sources",
        "active_source_count": 0,
        "ready_source_count": 0,
        "unavailable_source_count": 0,
    }
