from __future__ import annotations

import importlib
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.preview import PreviewAuditEvent, PreviewCandidate, PreviewRequest
from app.db.models.source_registry import RegisteredSource
from app.db.session import require_preview_submission_session
from app.services.demo_source_seed import seed_demo_source_governance
from app.services.health import _workflow_lifecycle_metrics


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


def _add_preview_request(
    session: Session,
    *,
    request_id: str,
    request_state: str,
) -> PreviewRequest:
    source = session.query(RegisteredSource).one()
    preview_request = PreviewRequest(
        id=uuid4(),
        request_id=request_id,
        registered_source_id=source.id,
        source_id=source.source_id,
        source_family=source.source_family,
        source_flavor=source.source_flavor,
        dataset_contract_id=source.dataset_contract_id,
        dataset_contract_version=1,
        schema_snapshot_id=source.schema_snapshot_id,
        schema_snapshot_version=1,
        authenticated_subject_id="user:demo-local-operator",
        auth_source="test-helper",
        session_id="session-redacted",
        governance_bindings="group:safequery-demo-local-operators",
        entitlement_decision="allow",
        request_text="Show approved spend",
        request_state=request_state,
    )
    session.add(preview_request)
    session.flush()
    return preview_request


def _add_preview_candidate(
    session: Session,
    *,
    preview_request: PreviewRequest,
    candidate_id: str,
    candidate_state: str,
) -> PreviewCandidate:
    preview_candidate = PreviewCandidate(
        id=uuid4(),
        candidate_id=candidate_id,
        preview_request_id=preview_request.id,
        request_id=preview_request.request_id,
        registered_source_id=preview_request.registered_source_id,
        source_id=preview_request.source_id,
        source_family=preview_request.source_family,
        source_flavor=preview_request.source_flavor,
        dataset_contract_id=preview_request.dataset_contract_id,
        dataset_contract_version=preview_request.dataset_contract_version,
        schema_snapshot_id=preview_request.schema_snapshot_id,
        schema_snapshot_version=preview_request.schema_snapshot_version,
        authenticated_subject_id=preview_request.authenticated_subject_id,
        guard_status="pending",
        candidate_state=candidate_state,
    )
    session.add(preview_candidate)
    session.flush()
    return preview_candidate


def _audit_event(
    *,
    preview_request: PreviewRequest,
    preview_candidate: PreviewCandidate | None = None,
    lifecycle_order: int,
    event_type: str,
    candidate_state: str | None = None,
    primary_deny_code: str | None = None,
    denial_cause: str | None = None,
) -> PreviewAuditEvent:
    payload = {"event_type": event_type}
    if denial_cause is not None:
        payload["denial_cause"] = denial_cause
    return PreviewAuditEvent(
        event_id=uuid4(),
        lifecycle_order=lifecycle_order,
        preview_request_id=preview_request.id,
        preview_candidate_id=(
            preview_candidate.id if preview_candidate is not None else None
        ),
        request_id=preview_request.request_id,
        candidate_id=(
            preview_candidate.candidate_id if preview_candidate is not None else None
        ),
        event_type=event_type,
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        correlation_id=f"correlation-{preview_request.request_id}",
        authenticated_subject_id="user:demo-local-operator",
        session_id="session-redacted",
        auth_source="test-helper",
        source_id=preview_request.source_id,
        source_family=preview_request.source_family,
        source_flavor=preview_request.source_flavor,
        dataset_contract_version=preview_request.dataset_contract_version,
        schema_snapshot_version=preview_request.schema_snapshot_version,
        primary_deny_code=primary_deny_code,
        denial_cause=denial_cause,
        candidate_state=candidate_state,
        audit_payload=payload,
    )


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
        "workflow_lifecycle_metrics": {
            "status": "no_traffic",
            "audit_event_count": 0,
            "preview": {
                "submitted": 0,
                "generation_completed": 0,
                "generation_failed": 0,
                "guard_evaluated": 0,
                "terminal_failures": {},
            },
            "execute": {
                "requested": 0,
                "completed": 0,
                "denied": 0,
                "failed": 0,
                "terminal_failures": {},
            },
            "audit_persistence": {
                "recorded_events": 0,
                "sources_with_events": 0,
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


def test_health_exposes_bounded_workflow_lifecycle_metrics(
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
    structured_logs: list[dict[str, object]] = []

    class _RecordingLogger:
        def info(self, _message: str, *, extra: dict[str, object]) -> None:
            event_data = extra.get("event_data")
            if isinstance(event_data, dict):
                structured_logs.append(event_data)

    monkeypatch.setattr(main_module, "get_logger", lambda: _RecordingLogger())

    with _session_scope() as session:
        preview_success_request = _add_preview_request(
            session,
            request_id="request-preview-success",
            request_state="previewed",
        )
        preview_success_candidate = _add_preview_candidate(
            session,
            preview_request=preview_success_request,
            candidate_id="candidate-preview-success",
            candidate_state="preview_ready",
        )
        preview_failed_request = _add_preview_request(
            session,
            request_id="request-preview-failed",
            request_state="preview_generation_failed",
        )
        execute_success_request = _add_preview_request(
            session,
            request_id="request-execute-success",
            request_state="previewed",
        )
        execute_success_candidate = _add_preview_candidate(
            session,
            preview_request=execute_success_request,
            candidate_id="candidate-execute-success",
            candidate_state="preview_ready",
        )
        execute_failed_request = _add_preview_request(
            session,
            request_id="request-execute-failed",
            request_state="previewed",
        )
        execute_failed_candidate = _add_preview_candidate(
            session,
            preview_request=execute_failed_request,
            candidate_id="candidate-execute-failed",
            candidate_state="failed",
        )
        session.add_all(
            [
                _audit_event(
                    preview_request=preview_success_request,
                    preview_candidate=preview_success_candidate,
                    lifecycle_order=1,
                    event_type="query_submitted",
                ),
                _audit_event(
                    preview_request=preview_success_request,
                    preview_candidate=preview_success_candidate,
                    lifecycle_order=2,
                    event_type="guard_evaluated",
                    candidate_state="preview_ready",
                ),
                _audit_event(
                    preview_request=preview_failed_request,
                    lifecycle_order=1,
                    event_type="generation_failed",
                    primary_deny_code="DENY_SQL_GENERATION_FAILED",
                    denial_cause="sql_generation_runtime_unhealthy",
                ),
                _audit_event(
                    preview_request=execute_success_request,
                    preview_candidate=execute_success_candidate,
                    lifecycle_order=3,
                    event_type="execution_completed",
                ),
                _audit_event(
                    preview_request=execute_failed_request,
                    preview_candidate=execute_failed_candidate,
                    lifecycle_order=3,
                    event_type="execution_failed",
                    candidate_state="failed",
                ),
            ]
        )
        session.commit()
        response = _client(session).get("/health")

    assert response.status_code == 200
    metrics = response.json()["operator_health"]["workflow_lifecycle_metrics"]
    assert metrics == {
        "status": "active",
        "audit_event_count": 5,
        "preview": {
            "submitted": 1,
            "generation_completed": 0,
            "generation_failed": 1,
            "guard_evaluated": 1,
            "terminal_failures": {
                "sql_generation_runtime_unhealthy": 1,
            },
        },
        "execute": {
            "requested": 0,
            "completed": 1,
            "denied": 0,
            "failed": 1,
            "terminal_failures": {
                "failed": 1,
            },
        },
        "audit_persistence": {
            "recorded_events": 5,
            "sources_with_events": 1,
        },
    }
    assert "safequery_exec" not in response.text
    assert "postgresql://" not in response.text
    assert {
        "event": "operator.workflow_lifecycle_metrics",
        "workflow_lifecycle_metrics": metrics,
    } in structured_logs
    assert "safequery_exec" not in str(structured_logs)
    assert "postgresql://" not in str(structured_logs)


def test_workflow_lifecycle_metrics_does_not_hydrate_audit_events() -> None:
    with _session_scope() as session:
        preview_request = _add_preview_request(
            session,
            request_id="request-preview-failure-bounds",
            request_state="preview_generation_failed",
        )
        session.add_all(
            [
                _audit_event(
                    preview_request=preview_request,
                    lifecycle_order=index + 1,
                    event_type="generation_failed",
                    denial_cause=f"failure-{index}",
                )
                for index in range(10)
            ]
        )
        session.commit()
        session.expunge_all()
        loaded_audit_event_types: list[str] = []

        def _record_loaded(_session: Session, instance: object) -> None:
            if isinstance(instance, PreviewAuditEvent):
                loaded_audit_event_types.append(instance.event_type)

        event.listen(session, "loaded_as_persistent", _record_loaded)
        try:
            metrics = _workflow_lifecycle_metrics(session)
        finally:
            event.remove(session, "loaded_as_persistent", _record_loaded)

    assert loaded_audit_event_types == []
    assert metrics["audit_event_count"] == 10
    assert metrics["audit_persistence"] == {
        "recorded_events": 10,
        "sources_with_events": 1,
    }
    assert metrics["preview"] == {
        "submitted": 0,
        "generation_completed": 0,
        "generation_failed": 10,
        "guard_evaluated": 0,
        "terminal_failures": {
            "failure-0": 1,
            "failure-1": 1,
            "failure-2": 1,
            "failure-3": 1,
            "failure-4": 1,
            "failure-5": 1,
            "failure-6": 1,
            "failure-7": 1,
        },
    }
