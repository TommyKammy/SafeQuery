from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.dataset_contract import (
    DatasetContract,
    DatasetContractDataset,
    DatasetContractDatasetKind,
)
from app.db.models.preview import (
    PreviewAuditEvent,
    PreviewCandidate,
    PreviewCandidateApproval,
    PreviewRequest,
)
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.db.session import require_preview_submission_session
from app.features.auth.context import AuthenticatedSubject, require_authenticated_subject
from app.features.auth.session import create_test_application_session
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionRequest,
    submit_preview_request,
)
from app.services.sql_generation_adapter import (
    SQLGenerationAdapterConfigurationError,
    SQLGenerationAdapterResponse,
)


def _seed_authoritative_source_governance(
    session: Session,
    *,
    include_datasets: bool = True,
    source_posture: SourceActivationPosture = SourceActivationPosture.ACTIVE,
) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id="sap-approved-spend",
        display_label="SAP spend cube / approved_vendor_spend",
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=source_posture,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference="vault:sap-approved-spend",
    )
    session.add(source)
    session.flush()

    snapshot = SchemaSnapshot(
        id=uuid4(),
        registered_source_id=source.id,
        snapshot_version=1,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=1,
        display_name="SAP spend cube contract",
        owner_binding="group:finance-analysts",
        security_review_binding=None,
        exception_policy_binding=None,
    )
    session.add(contract)
    session.flush()

    if include_datasets:
        session.add(
            DatasetContractDataset(
                id=uuid4(),
                dataset_contract_id=contract.id,
                schema_name="finance",
                dataset_name="approved_vendor_spend",
                dataset_kind=DatasetContractDatasetKind.TABLE,
            )
        )

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()


class _RecordingHTTPPreviewAdapter:
    def __init__(self) -> None:
        self.adapter_request = None

    def generate_sql(self, request):
        self.adapter_request = request
        return SQLGenerationAdapterResponse(
            candidate_sql=(
                " SELECT vendor_id FROM finance.approved_vendor_spend LIMIT 50; "
            ),
            provider="local_llm",
            adapter_version="test.local_llm.v1",
            model="safequery-test-sql",
        )


class _FailingHTTPPreviewAdapter:
    def generate_sql(self, request):
        raise SQLGenerationAdapterConfigurationError(
            "sql_generation_runtime_unhealthy",
            "SQL generation runtime is unavailable.",
        )


def test_http_preview_submission_persists_request_and_candidate_records() -> None:
    previous_env = {
        name: os.environ.get(name)
        for name in (
            "SAFEQUERY_APP_POSTGRES_URL",
            "SAFEQUERY_SESSION_SIGNING_KEY",
        )
    }
    os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
        "postgresql://safequery:safequery@db:5432/safequery"
    )
    os.environ["SAFEQUERY_SESSION_SIGNING_KEY"] = "x" * 32
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:finance-analysts"}),
    )

    main_module = importlib.import_module("app.main")
    app = main_module.create_app()
    app.dependency_overrides[require_authenticated_subject] = lambda: subject
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    client = TestClient(app)

    try:
        _seed_authoritative_source_governance(session)
        app_session = create_test_application_session(subject)

        response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        assert response.status_code == 200
        response_payload = response.json()
        request_id = response.headers["X-Request-ID"]
        response_candidate_id = response_payload["audit"]["events"][2]["query_candidate_id"]

        assert response_payload["request"]["request_id"] == request_id
        assert response_payload["candidate"]["candidate_id"] == response_candidate_id
        assert response_payload["candidate"]["guard_status"] == "pending"
        assert response_payload["candidate"]["candidate_sql"] is None

        persisted_request = session.execute(select(PreviewRequest)).scalar_one()
        persisted_candidate = session.execute(select(PreviewCandidate)).scalar_one()
        persisted_approval = session.execute(
            select(PreviewCandidateApproval)
        ).scalar_one()
        persisted_events = (
            session.execute(
                select(PreviewAuditEvent).order_by(PreviewAuditEvent.lifecycle_order)
            )
            .scalars()
            .all()
        )

        assert persisted_request.request_id == request_id
        assert persisted_request.request_text == (
            "Show approved vendors by quarterly spend"
        )
        assert persisted_request.source_id == "sap-approved-spend"
        assert persisted_request.request_state == "previewed"
        assert persisted_request.authenticated_subject_id == "user:alice"
        assert persisted_request.auth_source == "test-helper"
        assert persisted_request.governance_bindings == "group:finance-analysts"
        assert persisted_request.dataset_contract_version == 1
        assert persisted_request.schema_snapshot_version == 1

        assert persisted_candidate.candidate_id == response_candidate_id
        assert persisted_candidate.request_id == request_id
        assert persisted_candidate.source_id == "sap-approved-spend"
        assert persisted_candidate.source_family == "postgresql"
        assert persisted_candidate.source_flavor == "warehouse"
        assert persisted_candidate.candidate_state == "preview_ready"
        assert persisted_candidate.guard_status == "pending"
        assert persisted_candidate.candidate_sql is None
        assert persisted_candidate.authenticated_subject_id == "user:alice"
        assert persisted_candidate.dataset_contract_version == 1
        assert persisted_candidate.schema_snapshot_version == 1
        assert persisted_candidate.registered_source_id == persisted_request.registered_source_id
        assert persisted_candidate.dataset_contract_id == persisted_request.dataset_contract_id
        assert persisted_candidate.schema_snapshot_id == persisted_request.schema_snapshot_id
        assert persisted_approval.preview_candidate_id == persisted_candidate.id
        assert persisted_approval.candidate_id == response_candidate_id
        assert persisted_approval.request_id == request_id
        assert persisted_approval.source_id == "sap-approved-spend"
        assert persisted_approval.owner_subject_id == "user:alice"
        assert persisted_approval.session_id == "application-session-redacted"
        assert persisted_approval.approval_state == "approved"
        assert persisted_approval.approved_at is not None
        assert persisted_approval.approval_expires_at > persisted_approval.approved_at
        assert persisted_approval.executed_at is None

        assert [event.event_type for event in persisted_events] == [
            "query_submitted",
            "generation_requested",
            "generation_completed",
            "guard_evaluated",
        ]
        assert all(
            event.preview_request_id == persisted_request.id for event in persisted_events
        )
        assert all(
            event.preview_candidate_id == persisted_candidate.id
            for event in persisted_events
        )
        assert all(event.request_id == request_id for event in persisted_events)
        assert persisted_events[-1].candidate_id == response_candidate_id
        assert persisted_events[-1].candidate_state == "preview_ready"
        assert persisted_events[-1].audit_payload["event_type"] == "guard_evaluated"
        assert persisted_events[-1].audit_payload["query_candidate_id"] == (
            response_candidate_id
        )
        serialized_events = str([event.audit_payload for event in persisted_events])
        assert app_session.csrf_token not in serialized_events
        assert app_session.cookie_value not in serialized_events
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


def test_http_preview_submission_persists_adapter_generated_candidate(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:safequery@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SESSION_SIGNING_KEY", "x" * 32)
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "local_llm")
    monkeypatch.setenv(
        "SAFEQUERY_SQL_GENERATION_LOCAL_LLM_BASE_URL",
        "http://sql-generation.example.test",
    )
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:finance-analysts"}),
    )
    adapter = _RecordingHTTPPreviewAdapter()

    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "resolve_sql_generation_adapter",
        lambda _: adapter,
    )
    app = main_module.create_app()
    app.dependency_overrides[require_authenticated_subject] = lambda: subject
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    client = TestClient(app)

    try:
        _seed_authoritative_source_governance(session)
        app_session = create_test_application_session(subject)

        response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        assert response.status_code == 200
        response_payload = response.json()
        request_id = response.headers["X-Request-ID"]
        candidate_sql = "SELECT vendor_id FROM finance.approved_vendor_spend LIMIT 50"

        assert response_payload["request"]["request_id"] == request_id
        assert response_payload["candidate"]["candidate_sql"] == candidate_sql
        assert response_payload["candidate"]["guard_status"] == "pending"
        assert response_payload["candidate"]["state"] == "preview_ready"

        adapter_payload = adapter.adapter_request.model_dump(mode="json")
        assert adapter_payload["request_id"] == request_id
        assert adapter_payload["source"] == {
            "source_id": "sap-approved-spend",
            "source_family": "postgresql",
            "source_flavor": "warehouse",
        }
        assert adapter_payload["context"]["datasets"] == [
            {
                "schema_name": "finance",
                "dataset_name": "approved_vendor_spend",
                "dataset_kind": "table",
            }
        ]
        assert "vault:sap-approved-spend" not in str(adapter_payload)
        assert "connection_reference" not in str(adapter_payload)
        assert "connection_string" not in str(adapter_payload)
        assert "credentials" not in str(adapter_payload).lower()

        persisted_candidate = session.execute(select(PreviewCandidate)).scalar_one()
        persisted_generation_event = (
            session.execute(
                select(PreviewAuditEvent).where(
                    PreviewAuditEvent.event_type == "generation_completed"
                )
            )
            .scalars()
            .one()
        )

        assert persisted_candidate.candidate_sql == candidate_sql
        assert persisted_candidate.adapter_provider == "local_llm"
        assert persisted_candidate.adapter_model == "safequery-test-sql"
        assert persisted_candidate.adapter_version == "test.local_llm.v1"
        assert persisted_candidate.adapter_run_id
        assert persisted_candidate.prompt_version == "sql_generation_adapter_request.v1"
        assert persisted_candidate.prompt_fingerprint is not None
        assert "Show approved vendors" not in persisted_candidate.prompt_fingerprint
        assert {
            "adapter_provider": "local_llm",
            "adapter_model": "safequery-test-sql",
            "adapter_version": "test.local_llm.v1",
            "adapter_run_id": persisted_candidate.adapter_run_id,
            "prompt_version": "sql_generation_adapter_request.v1",
            "prompt_fingerprint": persisted_candidate.prompt_fingerprint,
        }.items() <= persisted_generation_event.audit_payload.items()
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_http_preview_adapter_failure_persists_authoritative_failure(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:safequery@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SESSION_SIGNING_KEY", "x" * 32)
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "local_llm")
    monkeypatch.setenv(
        "SAFEQUERY_SQL_GENERATION_LOCAL_LLM_BASE_URL",
        "http://sql-generation.example.test",
    )
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:finance-analysts"}),
    )

    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "resolve_sql_generation_adapter",
        lambda _: _FailingHTTPPreviewAdapter(),
    )
    app = main_module.create_app()
    app.dependency_overrides[require_authenticated_subject] = lambda: subject
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    client = TestClient(app)

    try:
        _seed_authoritative_source_governance(session)
        app_session = create_test_application_session(subject)

        response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        assert response.status_code == 422
        assert response.json() == {
            "error": {
                "code": "preview_generation_failed",
                "message": (
                    "SQL generation failed before an authoritative preview "
                    "candidate was created."
                ),
            }
        }

        persisted_request = session.execute(select(PreviewRequest)).scalar_one()
        persisted_events = session.execute(select(PreviewAuditEvent)).scalars().all()
        persisted_candidates = session.execute(select(PreviewCandidate)).scalars().all()

        assert persisted_request.request_id == response.headers["X-Request-ID"]
        assert persisted_request.request_state == "preview_generation_failed"
        assert persisted_request.entitlement_decision == "allow"
        assert persisted_candidates == []
        assert len(persisted_events) == 1
        assert persisted_events[0].event_type == "generation_failed"
        assert persisted_events[0].primary_deny_code == "DENY_SQL_GENERATION_FAILED"
        assert persisted_events[0].denial_cause == "sql_generation_runtime_unhealthy"
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_http_preview_context_failure_persists_specific_failure_code(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:safequery@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SESSION_SIGNING_KEY", "x" * 32)
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "local_llm")
    monkeypatch.setenv(
        "SAFEQUERY_SQL_GENERATION_LOCAL_LLM_BASE_URL",
        "http://sql-generation.example.test",
    )
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:finance-analysts"}),
    )

    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "resolve_sql_generation_adapter",
        lambda _: _RecordingHTTPPreviewAdapter(),
    )
    app = main_module.create_app()
    app.dependency_overrides[require_authenticated_subject] = lambda: subject
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    client = TestClient(app)

    try:
        _seed_authoritative_source_governance(session, include_datasets=False)
        app_session = create_test_application_session(subject)

        response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        assert response.status_code == 422
        assert response.json() == {
            "error": {
                "code": "preview_generation_failed",
                "message": (
                    "SQL generation failed before an authoritative preview "
                    "candidate was created."
                ),
            }
        }

        persisted_request = session.execute(select(PreviewRequest)).scalar_one()
        persisted_events = session.execute(select(PreviewAuditEvent)).scalars().all()
        persisted_candidates = session.execute(select(PreviewCandidate)).scalars().all()

        assert persisted_request.request_id == response.headers["X-Request-ID"]
        assert persisted_request.request_state == "preview_generation_failed"
        assert persisted_request.entitlement_decision == "allow"
        assert persisted_candidates == []
        assert len(persisted_events) == 1
        assert persisted_events[0].event_type == "generation_failed"
        assert persisted_events[0].primary_deny_code == "DENY_SQL_GENERATION_FAILED"
        assert persisted_events[0].denial_cause == "no_approved_datasets"
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_preview_submission_updates_existing_request_and_candidate_records() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:finance-analysts"}),
    )

    with Session(engine) as session:
        _seed_authoritative_source_governance(session)
        audit_context = PreviewAuditContext(
            occurred_at=datetime.now(timezone.utc),
            request_id="preview-request-231",
            correlation_id="preview-correlation-231",
            user_subject="user:alice",
            session_id="session-231",
            query_candidate_id="preview-candidate-231",
            candidate_owner_subject="user:alice",
            auth_source="test-helper",
        )

        submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="sap-approved-spend",
            ),
            subject,
            session,
            audit_context=audit_context.model_copy(deep=True),
        )
        submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by yearly spend",
                source_id="sap-approved-spend",
            ),
            subject,
            session,
            audit_context=audit_context.model_copy(deep=True),
        )

        persisted_requests = session.execute(select(PreviewRequest)).scalars().all()
        persisted_candidates = session.execute(select(PreviewCandidate)).scalars().all()

    assert len(persisted_requests) == 1
    assert len(persisted_candidates) == 1
    assert persisted_requests[0].request_id == "preview-request-231"
    assert persisted_requests[0].request_text == "Show approved vendors by yearly spend"
    assert persisted_requests[0].request_state == "previewed"
    assert persisted_candidates[0].candidate_id == "preview-candidate-231"
    assert persisted_candidates[0].request_id == "preview-request-231"
    assert persisted_candidates[0].source_id == "sap-approved-spend"


def test_http_preview_entitlement_denial_persists_audit_event_without_secrets() -> None:
    previous_env = {
        name: os.environ.get(name)
        for name in (
            "SAFEQUERY_APP_POSTGRES_URL",
            "SAFEQUERY_SESSION_SIGNING_KEY",
        )
    }
    os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
        "postgresql://safequery:safequery@db:5432/safequery"
    )
    os.environ["SAFEQUERY_SESSION_SIGNING_KEY"] = "x" * 32
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:unentitled-analysts"}),
    )

    main_module = importlib.import_module("app.main")
    app = main_module.create_app()
    app.dependency_overrides[require_authenticated_subject] = lambda: subject
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    client = TestClient(app)

    try:
        _seed_authoritative_source_governance(session)
        app_session = create_test_application_session(subject)

        response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        assert response.status_code == 403
        request_id = response.headers["X-Request-ID"]
        persisted_request = session.execute(select(PreviewRequest)).scalar_one()
        persisted_events = session.execute(select(PreviewAuditEvent)).scalars().all()
        persisted_candidates = session.execute(select(PreviewCandidate)).scalars().all()

        assert persisted_candidates == []
        assert persisted_request.request_id == request_id
        assert persisted_request.request_state == "preview_denied"
        assert persisted_request.entitlement_decision == "deny"
        assert persisted_request.request_text == (
            "Show approved vendors by quarterly spend"
        )
        assert len(persisted_events) == 1
        assert persisted_events[0].preview_request_id == persisted_request.id
        assert persisted_events[0].preview_candidate_id is None
        assert persisted_events[0].event_type == "generation_failed"
        assert persisted_events[0].primary_deny_code == "DENY_SOURCE_ENTITLEMENT"
        assert persisted_events[0].audit_payload["denial_cause"] == (
            "entitlement_denied"
        )
        serialized_events = str([event.audit_payload for event in persisted_events])
        assert app_session.csrf_token not in serialized_events
        assert app_session.cookie_value not in serialized_events
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


def test_http_preview_unavailable_source_persists_audit_event() -> None:
    previous_env = {
        name: os.environ.get(name)
        for name in (
            "SAFEQUERY_APP_POSTGRES_URL",
            "SAFEQUERY_SESSION_SIGNING_KEY",
        )
    }
    os.environ["SAFEQUERY_APP_POSTGRES_URL"] = (
        "postgresql://safequery:safequery@db:5432/safequery"
    )
    os.environ["SAFEQUERY_SESSION_SIGNING_KEY"] = "x" * 32
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:finance-analysts"}),
    )

    main_module = importlib.import_module("app.main")
    app = main_module.create_app()
    app.dependency_overrides[require_authenticated_subject] = lambda: subject
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    client = TestClient(app)

    try:
        _seed_authoritative_source_governance(
            session,
            source_posture=SourceActivationPosture.PAUSED,
        )
        app_session = create_test_application_session(subject)

        response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": "Show approved vendors by quarterly spend",
                "source_id": "sap-approved-spend",
            },
        )

        assert response.status_code == 422
        assert response.json() == {
            "error": {
                "code": "preview_source_unavailable",
                "message": "Selected source is unavailable for preview.",
            }
        }
        request_id = response.headers["X-Request-ID"]
        persisted_request = session.execute(select(PreviewRequest)).scalar_one()
        persisted_event = session.execute(select(PreviewAuditEvent)).scalar_one()

        assert persisted_request.request_id == request_id
        assert persisted_request.request_state == "preview_unavailable"
        assert persisted_request.entitlement_decision == "deny"
        assert persisted_event.preview_request_id == persisted_request.id
        assert persisted_event.preview_candidate_id is None
        assert persisted_event.event_type == "generation_failed"
        assert persisted_event.primary_deny_code == "DENY_SOURCE_UNAVAILABLE"
        assert persisted_event.denial_cause == "source_unavailable"
        assert persisted_event.audit_payload["source_id"] == "sap-approved-spend"
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()


def test_preview_submission_rejects_candidate_rebind_by_request_source_key() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    subject = AuthenticatedSubject(
        subject_id="user:alice",
        governance_bindings=frozenset({"group:finance-analysts"}),
    )

    with Session(engine) as session:
        _seed_authoritative_source_governance(session)
        audit_context = PreviewAuditContext(
            occurred_at=datetime.now(timezone.utc),
            request_id="preview-request-231",
            correlation_id="preview-correlation-231",
            user_subject="user:alice",
            session_id="session-231",
            query_candidate_id="preview-candidate-231",
            candidate_owner_subject="user:alice",
            auth_source="test-helper",
        )

        submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="sap-approved-spend",
            ),
            subject,
            session,
            audit_context=audit_context.model_copy(deep=True),
        )

        rebound_context = audit_context.model_copy(
            update={"query_candidate_id": "preview-candidate-rebound"}
        )
        try:
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by yearly spend",
                    source_id="sap-approved-spend",
                ),
                subject,
                session,
                audit_context=rebound_context,
            )
        except PreviewSubmissionContractError as exc:
            assert str(exc) == (
                "Preview candidate cannot be rebound to a different candidate."
            )
        else:
            raise AssertionError("expected candidate rebinding to fail closed")

        persisted_requests = session.execute(select(PreviewRequest)).scalars().all()
        persisted_candidates = session.execute(select(PreviewCandidate)).scalars().all()

    assert len(persisted_requests) == 1
    assert len(persisted_candidates) == 1
    assert persisted_requests[0].request_text == "Show approved vendors by quarterly spend"
    assert persisted_candidates[0].candidate_id == "preview-candidate-231"
    assert persisted_candidates[0].guard_status == "pending"


def test_preview_candidate_model_uses_composite_request_source_foreign_key() -> None:
    foreign_keys = {
        tuple(element.parent.name for element in constraint.elements): tuple(
            element.target_fullname for element in constraint.elements
        )
        for constraint in PreviewCandidate.__table__.foreign_key_constraints
    }

    assert foreign_keys[("preview_request_id", "registered_source_id")] == (
        "preview_requests.id",
        "preview_requests.registered_source_id",
    )
