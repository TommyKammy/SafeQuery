from __future__ import annotations

import importlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.models.preview import (
    PreviewAuditEvent,
    PreviewCandidate,
    PreviewCandidateApproval,
    PreviewRequest,
)
from app.db.models.source_registry import RegisteredSource
from app.db.session import require_preview_submission_session
from app.features.auth.context import AuthenticatedSubject, require_authenticated_subject
from app.services.demo_source_seed import seed_demo_source_governance
from app.services.support_bundle import build_support_bundle


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
    app.dependency_overrides[require_authenticated_subject] = lambda: AuthenticatedSubject(
        subject_id="user:support-reviewer",
        governance_bindings=frozenset({"group:security-reviewers"}),
    )
    app.dependency_overrides[require_preview_submission_session] = lambda: session
    return TestClient(app)


def _add_workflow_records_with_sensitive_payload(session: Session) -> None:
    source = session.query(RegisteredSource).one()
    preview_request = PreviewRequest(
        id=uuid4(),
        request_id="request-support-bundle",
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
        session_id="session-support-bundle",
        governance_bindings="group:safequery-demo-local-operators",
        entitlement_decision="allow",
        request_text="Show approved spend",
        request_state="previewed",
    )
    session.add(preview_request)
    session.flush()

    preview_candidate = PreviewCandidate(
        id=uuid4(),
        candidate_id="candidate-support-bundle",
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
        candidate_sql="select * from raw_private_rows",
        guard_status="passed",
        candidate_state="preview_ready",
    )
    session.add(preview_candidate)
    session.flush()

    session.add(
        PreviewAuditEvent(
            event_id=uuid4(),
            lifecycle_order=4,
            preview_request_id=preview_request.id,
            preview_candidate_id=preview_candidate.id,
            request_id=preview_request.request_id,
            candidate_id=preview_candidate.candidate_id,
            event_type="guard_evaluated",
            occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            correlation_id="correlation-support-bundle",
            authenticated_subject_id="user:demo-local-operator",
            session_id="session-support-bundle",
            auth_source="test-helper",
            source_id=preview_request.source_id,
            source_family=preview_request.source_family,
            source_flavor=preview_request.source_flavor,
            dataset_contract_version=preview_request.dataset_contract_version,
            schema_snapshot_version=preview_request.schema_snapshot_version,
            candidate_state="preview_ready",
            audit_payload={
                "raw_rows": [{"customer_secret": "sk-live-should-not-leak"}],
                "debug_path": "/".join(
                    ["", "Users", "example", ".safequery", "private.log"]
                ),
                "connection": "postgresql://reader:secret@db:5432/business",
            },
        )
    )
    session.commit()


def _add_governance_review_workflow_records(
    session: Session,
    *,
    execution_row_count: object = 12,
) -> None:
    source = session.query(RegisteredSource).one()
    preview_request = PreviewRequest(
        id=uuid4(),
        request_id="request-governance-bundle",
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
        session_id="session-governance-bundle",
        governance_bindings="group:safequery-demo-local-operators",
        entitlement_decision="allow",
        request_text="Show approved spend",
        request_state="executed",
    )
    session.add(preview_request)
    session.flush()

    preview_candidate = PreviewCandidate(
        id=uuid4(),
        candidate_id="candidate-governance-bundle",
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
        candidate_sql="select * from raw_private_rows",
        adapter_provider="fixture-adapter",
        adapter_model="fixture-model",
        adapter_version="fixture-version",
        adapter_run_id="adapter-run-316",
        prompt_version="prompt-v1",
        prompt_fingerprint="prompt-fingerprint-316",
        guard_status="passed",
        candidate_state="executed",
    )
    session.add(preview_candidate)
    session.flush()

    session.add(
        PreviewCandidateApproval(
            id=uuid4(),
            approval_id="approval-governance-bundle",
            preview_candidate_id=preview_candidate.id,
            candidate_id=preview_candidate.candidate_id,
            request_id=preview_request.request_id,
            registered_source_id=preview_request.registered_source_id,
            source_id=preview_request.source_id,
            source_family=preview_request.source_family,
            source_flavor=preview_request.source_flavor,
            dataset_contract_version=preview_request.dataset_contract_version,
            schema_snapshot_version=preview_request.schema_snapshot_version,
            execution_policy_version=3,
            approved_sql="select * from raw_private_rows",
            owner_subject_id=preview_request.authenticated_subject_id,
            session_id=preview_request.session_id,
            approved_at=datetime(2026, 1, 2, 3, 4, 10, tzinfo=timezone.utc),
            approval_expires_at=datetime(2026, 1, 2, 3, 9, 10, tzinfo=timezone.utc),
            executed_at=datetime(2026, 1, 2, 3, 5, 3, tzinfo=timezone.utc),
            approval_state="executed",
        )
    )

    lifecycle_events = [
        ("query_submitted", 1, None, None),
        ("generation_completed", 3, preview_candidate.candidate_id, "preview_ready"),
        ("guard_evaluated", 4, preview_candidate.candidate_id, "preview_ready"),
        ("execution_completed", 7, preview_candidate.candidate_id, "executed"),
    ]
    for event_type, lifecycle_order, candidate_id, candidate_state in lifecycle_events:
        session.add(
            PreviewAuditEvent(
                event_id=uuid4(),
                lifecycle_order=lifecycle_order,
                preview_request_id=preview_request.id,
                preview_candidate_id=(
                    preview_candidate.id if candidate_id is not None else None
                ),
                request_id=preview_request.request_id,
                candidate_id=candidate_id,
                event_type=event_type,
                occurred_at=datetime(
                    2026,
                    1,
                    2,
                    3,
                    4 + lifecycle_order,
                    5,
                    tzinfo=timezone.utc,
                ),
                correlation_id="correlation-governance-bundle",
                authenticated_subject_id=preview_request.authenticated_subject_id,
                session_id=preview_request.session_id,
                auth_source=preview_request.auth_source,
                governance_bindings=preview_request.governance_bindings,
                entitlement_decision=preview_request.entitlement_decision,
                adapter_provider=preview_candidate.adapter_provider,
                adapter_model=preview_candidate.adapter_model,
                adapter_version=preview_candidate.adapter_version,
                adapter_run_id=preview_candidate.adapter_run_id,
                prompt_version=preview_candidate.prompt_version,
                prompt_fingerprint=preview_candidate.prompt_fingerprint,
                source_id=preview_request.source_id,
                source_family=preview_request.source_family,
                source_flavor=preview_request.source_flavor,
                dataset_contract_version=preview_request.dataset_contract_version,
                schema_snapshot_version=preview_request.schema_snapshot_version,
                candidate_state=candidate_state,
                audit_payload={
                    "execution_row_count": execution_row_count,
                    "result_truncated": False,
                    "raw_rows": [{"customer_secret": "sk-live-should-not-leak"}],
                    "debug_path": "/".join(
                        ["", "Users", "example", ".safequery", "private.log"]
                    ),
                    "connection": "postgresql://reader:secret@db:5432/business",
                },
            )
        )
    session.commit()


def _assert_secret_safe(serialized: str) -> None:
    forbidden_fragments = (
        "postgresql://",
        "Driver={ODBC Driver 18 for SQL Server}",
        "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING",
        '"connection_reference"',
        "raw_private_rows",
        "raw_rows",
        "customer_secret",
        "sk-live-should-not-leak",
        "/".join(["", "Users", "example"]),
        "\\".join(["", "Users", "example"]),
        "secret@",
    )
    for fragment in forbidden_fragments:
        assert fragment not in serialized
    assert not re.search(r"(?i)(password|api[_-]?key|secret)", serialized)


def test_support_bundle_service_includes_bounded_diagnostics_without_secrets(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:app-secret@db:5432/safequery",
    )
    monkeypatch.setenv(
        "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        "postgresql://source_reader:source-secret@pg-source:5432/business",
    )
    monkeypatch.setenv(
        "SAFEQUERY_BUSINESS_MSSQL_SOURCE_CONNECTION_STRING",
        "Driver={ODBC Driver 18 for SQL Server};Server=tcp:mssql-source,1433;"
        "Database=business;Uid=safequery_reader;Pwd=source-secret",
    )
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "disabled")
    get_settings.cache_clear()

    with _session_scope() as session:
        _add_workflow_records_with_sensitive_payload(session)
        bundle = build_support_bundle(
            session,
            settings=get_settings(),
            database={"status": "ok", "detail": "ready"},
            sql_generation={"status": "disabled", "detail": "provider_disabled"},
            generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

    payload = bundle.model_dump(mode="json", by_alias=True)
    governance_review = payload.pop("governanceReview")
    assert governance_review["authority"] == "safequery_control_plane"
    assert governance_review["limitations"] == [
        "Bundle is read-only review evidence and does not authorize execution.",
        "Subordinate adapter, LLM, search, analyst, MLflow, UI, and external evidence is labeled as non-authoritative.",
        "Raw SQL, result rows, credentials, connection references, tokens, and workstation-local paths are excluded.",
    ]
    assert governance_review["evidence"][0]["sourceId"] == "demo-business-postgres"
    assert governance_review["evidence"][0]["authority"] == "safequery_control_plane"
    assert governance_review["evidence"][0]["candidate"]["adapterEvidence"][
        "authority"
    ] == "subordinate_adapter"
    assert payload == {
        "bundleVersion": 1,
        "generatedAt": "2026-01-02T03:04:05Z",
        "application": {
            "service": "safequery-api",
            "version": "0.1.0",
            "environment": "development",
        },
        "sourcePosture": {
            "source_posture": "coherent",
            "configured_source_count": 3,
            "source_roles": {
                "application_postgres_persistence": "configured",
                "business_postgres_source_generation": "configured",
                "business_mssql_source_execution": "configured",
            },
        },
        "migrationPosture": {
            "status": "unknown",
            "detail": "OperationalError",
            "appliedRevisions": [],
            "expectedHeads": [],
        },
        "activeSources": [
            {
                "sourceId": "demo-business-postgres",
                "sourceFamily": "postgresql",
                "sourceFlavor": "warehouse",
                "activationPosture": "active",
                "datasetContractVersion": 1,
                "schemaSnapshotVersion": 1,
                "governanceBindings": [
                    {
                        "role": "owner",
                        "state": "valid",
                        "affectsEntitlement": True,
                        "summary": "Owner binding is current and normalized.",
                        "recovery": "No operator recovery is required for this binding.",
                    },
                    {
                        "role": "security_review",
                        "state": "valid",
                        "affectsEntitlement": False,
                        "summary": "Security Review binding is current and normalized.",
                        "recovery": "No operator recovery is required for this binding.",
                    },
                    {
                        "role": "exception_policy",
                        "state": "missing",
                        "affectsEntitlement": False,
                        "summary": "Exception Policy binding is missing or malformed.",
                        "recovery": "Reconcile the authoritative dataset contract before granting access.",
                    },
                ],
            }
        ],
        "health": {
            "status": "ok",
            "components": {
                "backend": {"status": "ok", "detail": "ready"},
                "frontend_api_connection": {"status": "ok", "detail": "reachable"},
                "generation_adapter": {
                    "status": "disabled",
                    "detail": "provider_disabled",
                    "provider": "unknown",
                },
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
                "audit_persistence": {"status": "ok", "detail": "ready"},
            },
        },
        "workflow": {
            "historyCount": 2,
            "recentStates": [
                {
                    "itemType": "candidate",
                    "lifecycleState": "preview_ready",
                    "sourceId": "demo-business-postgres",
                },
                {
                    "itemType": "request",
                    "lifecycleState": "previewed",
                    "sourceId": "demo-business-postgres",
                },
            ],
            "lifecycleMetrics": {
                "status": "active",
                "audit_event_count": 1,
                "preview": {
                    "submitted": 0,
                    "generation_completed": 0,
                    "generation_failed": 0,
                    "guard_evaluated": 1,
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
                    "recorded_events": 1,
                    "sources_with_events": 1,
                },
            },
        },
        "auditCompleteness": {
            "status": "present",
            "recordedEvents": 1,
            "sourcesWithEvents": 1,
        },
        "redaction": {
            "excluded": [
                "connection_strings",
                "raw_credentials",
                "tokens",
                "raw_result_rows",
                "candidate_sql",
                "raw_identity_payloads",
                "workstation_local_paths",
                "source_connection_references",
            ]
        },
    }
    _assert_secret_safe(json.dumps(payload, sort_keys=True))


def test_support_bundle_includes_source_aware_governance_review_evidence(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:app-secret@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "disabled")
    get_settings.cache_clear()

    with _session_scope() as session:
        _add_governance_review_workflow_records(session)
        bundle = build_support_bundle(
            session,
            settings=get_settings(),
            database={"status": "ok", "detail": "ready"},
            sql_generation={"status": "disabled", "detail": "provider_disabled"},
            generated_at=datetime(2026, 1, 2, 3, 10, 5, tzinfo=timezone.utc),
        )

    payload = bundle.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert payload["governanceReview"]["authority"] == "safequery_control_plane"
    assert payload["governanceReview"]["limitations"] == [
        "Bundle is read-only review evidence and does not authorize execution.",
        "Subordinate adapter, LLM, search, analyst, MLflow, UI, and external evidence is labeled as non-authoritative.",
        "Raw SQL, result rows, credentials, connection references, tokens, and workstation-local paths are excluded.",
    ]
    assert payload["governanceReview"]["evidence"] == [
        {
            "authority": "safequery_control_plane",
            "recordType": "workflow_lifecycle",
            "requestId": "request-governance-bundle",
            "candidateId": "candidate-governance-bundle",
            "sourceId": "demo-business-postgres",
            "sourceFamily": "postgresql",
            "sourceFlavor": "warehouse",
            "datasetContractVersion": 1,
            "schemaSnapshotVersion": 1,
            "lifecycle": [
                {
                    "eventType": "query_submitted",
                    "occurredAt": "2026-01-02T03:05:05Z",
                    "lifecycleOrder": 1,
                    "authority": "safequery_control_plane",
                },
                {
                    "eventType": "generation_completed",
                    "occurredAt": "2026-01-02T03:07:05Z",
                    "lifecycleOrder": 3,
                    "candidateState": "preview_ready",
                    "authority": "safequery_control_plane",
                },
                {
                    "eventType": "guard_evaluated",
                    "occurredAt": "2026-01-02T03:08:05Z",
                    "lifecycleOrder": 4,
                    "candidateState": "preview_ready",
                    "authority": "safequery_control_plane",
                },
                {
                    "eventType": "execution_completed",
                    "occurredAt": "2026-01-02T03:11:05Z",
                    "lifecycleOrder": 7,
                    "candidateState": "executed",
                    "authority": "safequery_control_plane",
                },
            ],
            "actor": {
                "authority": "safequery_control_plane",
                "authenticatedSubjectId": "user:demo-local-operator",
                "authSource": "test-helper",
                "governanceBindings": ["group:safequery-demo-local-operators"],
                "entitlementDecision": "allow",
            },
            "candidate": {
                "authority": "safequery_control_plane",
                "candidateState": "executed",
                "guardStatus": "passed",
                "adapterEvidence": {
                    "authority": "subordinate_adapter",
                    "adapterProvider": "fixture-adapter",
                    "adapterModel": "fixture-model",
                    "adapterVersion": "fixture-version",
                    "adapterRunId": "adapter-run-316",
                    "promptVersion": "prompt-v1",
                    "promptFingerprint": "prompt-fingerprint-316",
                },
            },
            "review": {
                "authority": "safequery_control_plane",
                "approvalId": "approval-governance-bundle",
                "approvalState": "executed",
                "ownerSubjectId": "user:demo-local-operator",
                "approvedAt": "2026-01-02T03:04:10Z",
                "approvalExpiresAt": "2026-01-02T03:09:10Z",
                "executedAt": "2026-01-02T03:05:03Z",
                "executionPolicyVersion": 3,
            },
            "executeResult": {
                "authority": "safequery_control_plane",
                "eventType": "execution_completed",
                "occurredAt": "2026-01-02T03:11:05Z",
                "rowCount": 12,
                "resultTruncated": False,
            },
        }
    ]
    serialized = json.dumps(payload, sort_keys=True)
    _assert_secret_safe(serialized)
    assert "raw_private_rows" not in serialized


def test_governance_review_execute_result_rejects_boolean_row_count(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:app-secret@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "disabled")
    get_settings.cache_clear()

    with _session_scope() as session:
        _add_governance_review_workflow_records(session, execution_row_count=True)
        bundle = build_support_bundle(
            session,
            settings=get_settings(),
            database={"status": "ok", "detail": "ready"},
            sql_generation={"status": "disabled", "detail": "provider_disabled"},
            generated_at=datetime(2026, 1, 2, 3, 10, 5, tzinfo=timezone.utc),
        )

    payload = bundle.model_dump(mode="json", by_alias=True, exclude_none=True)
    execute_result = payload["governanceReview"]["evidence"][0]["executeResult"]
    assert "rowCount" not in execute_result
    assert execute_result["resultTruncated"] is False


def test_governance_review_export_rejects_unsafe_export_values_by_category(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:app-secret@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "disabled")
    get_settings.cache_clear()

    unsafe_cases = (
        (
            "ghp_unsafeTokenShouldNotEcho123456789",
            "token-like values",
            lambda session: setattr(
                session.query(PreviewCandidate).one(),
                "adapter_run_id",
                "ghp_unsafeTokenShouldNotEcho123456789",
            ),
        ),
        (
            "postgresql://reader:secret-value@db:5432/business",
            "connection-string-like values",
            lambda session: setattr(
                session.query(PreviewRequest).one(),
                "auth_source",
                "postgresql://reader:secret-value@db:5432/business",
            ),
        ),
        (
            "database_password",
            "raw credential names",
            lambda session: setattr(
                session.query(PreviewCandidate).one(),
                "adapter_provider",
                "database_password",
            ),
        ),
        (
            "operator@example.test",
            "raw identity payloads",
            lambda session: setattr(
                session.query(PreviewRequest).one(),
                "authenticated_subject_id",
                '{"sub":"user:demo","email":"operator@example.test"}',
            ),
        ),
        (
            "/".join(["", "Users", "example", ".safequery", "private.log"]),
            "workstation-local paths",
            lambda session: setattr(
                session.query(PreviewCandidate).one(),
                "prompt_fingerprint",
                "/".join(["", "Users", "example", ".safequery", "private.log"]),
            ),
        ),
    )

    for unsafe_value, expected_category, mutate in unsafe_cases:
        with _session_scope() as session:
            _add_governance_review_workflow_records(session)
            mutate(session)
            session.commit()

            try:
                build_support_bundle(
                    session,
                    settings=get_settings(),
                    database={"status": "ok", "detail": "ready"},
                    sql_generation={
                        "status": "disabled",
                        "detail": "provider_disabled",
                    },
                    generated_at=datetime(2026, 1, 2, 3, 10, 5, tzinfo=timezone.utc),
                )
            except ValueError as exc:
                message = str(exc)
            else:
                raise AssertionError(
                    f"Expected support bundle export to reject {expected_category}."
                )

        assert expected_category in message
        assert unsafe_value not in message


def test_support_bundle_endpoint_returns_secret_safe_json(monkeypatch) -> None:
    monkeypatch.setenv(
        "SAFEQUERY_APP_POSTGRES_URL",
        "postgresql://safequery:app-secret@db:5432/safequery",
    )
    monkeypatch.setenv("SAFEQUERY_ENVIRONMENT", "development")
    monkeypatch.setenv("SAFEQUERY_DEV_AUTH_ENABLED", "true")
    monkeypatch.setenv("SAFEQUERY_SQL_GENERATION_PROVIDER", "disabled")
    get_settings.cache_clear()
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(
        main_module,
        "check_database_health",
        lambda _url: {"status": "ok", "detail": "ready"},
    )

    with _session_scope() as session:
        response = _client(session).get("/support/bundle")

    assert response.status_code == 200
    payload = response.json()
    assert payload["bundleVersion"] == 1
    assert payload["application"] == {
        "service": "safequery-api",
        "version": "0.1.0",
        "environment": "development",
    }
    assert payload["activeSources"][0]["sourceId"] == "demo-business-postgres"
    assert payload["redaction"]["excluded"] == [
        "connection_strings",
        "raw_credentials",
        "tokens",
        "raw_result_rows",
        "candidate_sql",
        "raw_identity_payloads",
        "workstation_local_paths",
        "source_connection_references",
    ]
    _assert_secret_safe(response.text)
