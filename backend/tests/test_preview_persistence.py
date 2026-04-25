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
from app.db.models.dataset_contract import DatasetContract
from app.db.models.preview import PreviewCandidate, PreviewRequest
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


def _seed_authoritative_source_governance(session: Session) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id="sap-approved-spend",
        display_label="SAP spend cube / approved_vendor_spend",
        source_family="postgresql",
        source_flavor="warehouse",
        activation_posture=SourceActivationPosture.ACTIVE,
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

    source.dataset_contract_id = contract.id
    source.schema_snapshot_id = snapshot.id
    session.commit()


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
        request_id = response.headers["X-Request-ID"]
        response_candidate_id = response.json()["audit"]["events"][2][
            "query_candidate_id"
        ]

        persisted_request = session.execute(select(PreviewRequest)).scalar_one()
        persisted_candidate = session.execute(select(PreviewCandidate)).scalar_one()

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
