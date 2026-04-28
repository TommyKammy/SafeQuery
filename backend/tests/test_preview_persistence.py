from __future__ import annotations

import importlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
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
from app.features.audit.event_model import SourceAwareAuditEvent
from app.features.auth.session import create_test_application_session
from app.features.evaluation.harness import list_postgresql_evaluation_scenarios
from app.features.guard import SQLGuardEvaluation, SQLGuardRejection
from app.services import request_preview as request_preview_service
from app.services.request_preview import (
    PreviewAuditContext,
    PreviewSubmissionContractError,
    PreviewSubmissionRequest,
    _build_preview_lifecycle_audit_events,
    _persist_candidate_approval_record,
    _sanitized_guard_denial_reason,
    submit_preview_request,
)
from app.services.operator_workflow import get_operator_workflow_snapshot
from app.services.sql_generation_adapter import (
    SQLGenerationAdapterConfigurationError,
    SQLGenerationAdapterResponse,
)


def _load_preview_to_execute_golden_fixture(name: str) -> dict[str, object]:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "preview_to_execute_golden_workflows.json"
    )
    fixture_set = json.loads(fixture_path.read_text())
    serialized_fixture_set = json.dumps(fixture_set, sort_keys=True)
    assert "credential" not in serialized_fixture_set.lower()
    assert "connection_string" not in serialized_fixture_set.lower()
    assert "postgresql://" not in serialized_fixture_set.lower()
    assert "mssql://" not in serialized_fixture_set.lower()
    assert "/Users/" not in serialized_fixture_set
    assert "C:\\" not in serialized_fixture_set
    assert "%USERPROFILE%" not in serialized_fixture_set
    assert fixture_set["authoritative_release_gate_inputs"] == [
        "scenario_id",
        "source_id",
        "candidate_id",
        "guard_decision",
        "guard_audit_event_id",
        "execution_run_id",
        "execution_audit_event_id",
    ]
    for fixture in fixture_set["fixtures"]:
        assert "scenario_id" in fixture["authoritative_fields"]
    fixtures = {
        fixture["name"]: fixture for fixture in fixture_set["fixtures"]
    }
    return fixtures[name]


def _seed_authoritative_source_governance(
    session: Session,
    *,
    source_id: str = "sap-approved-spend",
    include_datasets: bool = True,
    source_posture: SourceActivationPosture = SourceActivationPosture.ACTIVE,
    connection_reference: str = "vault:sap-approved-spend",
    source_family: str = "postgresql",
    source_flavor: str = "warehouse",
    dataset_contract_version: int = 1,
    schema_snapshot_version: int = 1,
) -> None:
    source = RegisteredSource(
        id=uuid4(),
        source_id=source_id,
        display_label="SAP spend cube / approved_vendor_spend",
        source_family=source_family,
        source_flavor=source_flavor,
        activation_posture=source_posture,
        connector_profile_id=None,
        dialect_profile_id=None,
        dataset_contract_id=None,
        schema_snapshot_id=None,
        execution_policy_id=None,
        connection_reference=connection_reference,
    )
    session.add(source)
    session.flush()

    snapshot = SchemaSnapshot(
        id=uuid4(),
        registered_source_id=source.id,
        snapshot_version=schema_snapshot_version,
        review_status=SchemaSnapshotReviewStatus.APPROVED,
        reviewed_at=datetime.now(timezone.utc),
    )
    session.add(snapshot)
    session.flush()

    contract = DatasetContract(
        id=uuid4(),
        registered_source_id=source.id,
        schema_snapshot_id=snapshot.id,
        contract_version=dataset_contract_version,
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
    def __init__(
        self,
        candidate_sql: str = " SELECT vendor_id FROM finance.approved_vendor_spend LIMIT 50; ",
    ) -> None:
        self.adapter_request = None
        self.candidate_sql = candidate_sql

    def generate_sql(self, request):
        self.adapter_request = request
        return SQLGenerationAdapterResponse(
            candidate_sql=self.candidate_sql,
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
        assert persisted_approval.execution_policy_version == 3
        assert persisted_approval.approved_sql is None
        assert persisted_approval.approval_state == "pending_guard"
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


def test_http_preview_allow_path_creates_approved_candidate_and_executes(
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
    monkeypatch.setenv(
        "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        "postgresql://safequery_exec:secret@business-postgres-source:5432/business",
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
        _seed_authoritative_source_governance(
            session,
            connection_reference="env:SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
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

        assert response.status_code == 200
        response_payload = response.json()
        request_id = response.headers["X-Request-ID"]
        candidate_sql = "SELECT vendor_id FROM finance.approved_vendor_spend LIMIT 50"

        assert response_payload["request"]["request_id"] == request_id
        assert response_payload["candidate"]["candidate_sql"] == candidate_sql
        assert response_payload["candidate"]["guard_status"] == "allow"
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
        assert persisted_candidate.guard_status == "allow"
        persisted_approval = session.execute(
            select(PreviewCandidateApproval)
        ).scalar_one()
        assert persisted_approval.approved_sql == candidate_sql
        assert persisted_approval.approval_state == "approved"
        assert persisted_approval.executed_at is None

        calls: list[str] = []

        def query_runner(**_):
            calls.append("called")
            return []

        app.state.execution_query_runner = query_runner
        execute_response = client.post(
            f"/candidates/{persisted_candidate.candidate_id}/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": "sap-approved-spend"},
        )

        assert execute_response.status_code == 200
        assert calls == ["called"]
        session.refresh(persisted_approval)
        assert persisted_approval.approval_state == "executed"
        assert persisted_approval.executed_at is not None
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


def test_http_preview_to_execute_emits_release_gate_scenario_metadata(
    monkeypatch,
) -> None:
    fixture = _load_preview_to_execute_golden_fixture(
        "http_preview_generation_guard_allow_approved_candidate_execute_audit"
    )
    scenario = next(
        scenario
        for scenario in list_postgresql_evaluation_scenarios()
        if scenario.scenario_id == fixture["scenario_id"]
    )
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
    monkeypatch.setenv(
        "SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        "postgresql://safequery_exec:secret@business-postgres-source:5432/business",
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
    adapter = _RecordingHTTPPreviewAdapter(scenario.canonical_sql)

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
        _seed_authoritative_source_governance(
            session,
            source_id=scenario.source.source_id,
            source_family=scenario.source.source_family,
            source_flavor=scenario.source.source_flavor,
            dataset_contract_version=scenario.source.dataset_contract_version,
            schema_snapshot_version=scenario.source.schema_snapshot_version,
            connection_reference="env:SAFEQUERY_BUSINESS_POSTGRES_SOURCE_URL",
        )
        app_session = create_test_application_session(subject)

        preview_response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": scenario.prompt,
                "source_id": scenario.source.source_id,
            },
        )

        assert preview_response.status_code == 200
        preview_payload = preview_response.json()
        assert preview_payload["candidate"]["source_id"] == fixture["source_id"]
        assert preview_payload["candidate"]["source_family"] == fixture["source_family"]
        assert preview_payload["candidate"]["source_flavor"] == fixture["source_flavor"]
        assert preview_payload["candidate"]["dataset_contract_version"] == (
            fixture["dataset_contract_version"]
        )
        assert preview_payload["candidate"]["schema_snapshot_version"] == (
            fixture["schema_snapshot_version"]
        )
        assert preview_payload["candidate"]["guard_status"] == (
            fixture["guard_decision"]
        )
        assert preview_payload["candidate"]["state"] == fixture["candidate_state"]
        persisted_candidate = session.execute(select(PreviewCandidate)).scalar_one()
        persisted_approval = session.execute(
            select(PreviewCandidateApproval)
        ).scalar_one()
        persisted_guard_event = (
            session.execute(
                select(PreviewAuditEvent).where(
                    PreviewAuditEvent.event_type == "guard_evaluated"
                )
            )
            .scalars()
            .one()
        )
        persisted_preview_events = (
            session.execute(
                select(PreviewAuditEvent).order_by(PreviewAuditEvent.lifecycle_order)
            )
            .scalars()
            .all()
        )

        assert [event.event_type for event in persisted_preview_events] == (
            fixture["expected_preview_events"]
        )
        assert persisted_approval.candidate_id == persisted_candidate.candidate_id
        assert persisted_approval.source_id == fixture["source_id"]
        assert persisted_approval.approval_state == (
            fixture["approval_state_after_preview"]
        )
        assert persisted_guard_event.candidate_id == persisted_candidate.candidate_id
        assert persisted_guard_event.source_id == fixture["source_id"]
        assert persisted_guard_event.audit_payload["guard_decision"] == (
            fixture["guard_decision"]
        )

        app.state.execution_query_runner = lambda **_: [
            {"vendor_name": "Acme", "approved_amount": 1000}
        ]
        execute_response = client.post(
            f"/candidates/{persisted_candidate.candidate_id}/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": scenario.source.source_id},
        )

        assert execute_response.status_code == 200
        execute_payload = execute_response.json()
        persisted_execution_event = (
            session.execute(
                select(PreviewAuditEvent).where(
                    PreviewAuditEvent.event_type == "execution_completed"
                )
            )
            .scalars()
            .one()
        )
        persisted_execution_events = (
            session.execute(
                select(PreviewAuditEvent)
                .where(PreviewAuditEvent.event_type.like("execution_%"))
                .order_by(PreviewAuditEvent.lifecycle_order)
            )
            .scalars()
            .all()
        )

        # These release-gate inputs let Epic T fixtures correlate generated SQL,
        # the guard decision, execution run, and authoritative audit evidence.
        expected_guard_metadata = {
            "scenario_id": scenario.scenario_id,
            "source_id": scenario.source.source_id,
            "candidate_id": persisted_candidate.candidate_id,
            "guard_decision": "allow",
            "guard_audit_event_id": str(persisted_guard_event.event_id),
        }
        assert (
            persisted_guard_event.audit_payload["release_gate_scenario"]
            == expected_guard_metadata
        )
        assert persisted_execution_event.audit_payload["release_gate_scenario"] == {
            **expected_guard_metadata,
            "execution_run_id": str(persisted_execution_event.event_id),
            "execution_audit_event_id": str(persisted_execution_event.event_id),
        }
        assert [event.event_type for event in persisted_execution_events] == (
            fixture["expected_execution_events"]
        )
        assert execute_payload["candidate_id"] == persisted_candidate.candidate_id
        assert execute_payload["source_id"] == fixture["source_id"]
        assert execute_payload["metadata"]["candidate_id"] == (
            persisted_candidate.candidate_id
        )
        assert execute_payload["metadata"]["source_id"] == fixture["source_id"]
        assert execute_payload["metadata"]["execution_run_id"] == str(
            persisted_execution_event.event_id
        )
        session.refresh(persisted_approval)
        assert persisted_approval.approval_state == (
            fixture["approval_state_after_execute"]
        )
        assert persisted_approval.executed_at is not None
        serialized_metadata = str(
            [
                persisted_guard_event.audit_payload["release_gate_scenario"],
                persisted_execution_event.audit_payload["release_gate_scenario"],
            ]
        )
        assert "safequery_exec:secret" not in serialized_metadata
        assert "business-postgres-source:5432" not in serialized_metadata
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def _rejected_guard_evaluation(detail: str) -> SQLGuardEvaluation:
    return SQLGuardEvaluation(
        decision="reject",
        profile="postgresql",
        canonical_sql="SELECT 1",
        source=None,
        rejections=[
            SQLGuardRejection(
                code="DENY_TEST",
                detail=detail,
                path="canonical_sql",
            )
        ],
    )


@pytest.mark.parametrize(
    "detail",
    [
        "guard detail referenced " + "/" + "/".join(("home", "alice", "query.sql")),
        "guard detail referenced " + "/" + "/".join(("tmp", "safequery.sql")),
        "guard detail referenced " + "/" + "/".join(("var", "log", "safequery")),
        "guard detail referenced C:" + "\\" + "\\".join(("temp", "safequery.sql")),
        "guard detail referenced "
        + "\\" * 2
        + "\\".join(("fileserver", "share", "safequery.sql")),
        "guard detail referenced ~" + "/" + "safequery/query.sql",
        "guard detail referenced path=" + "/" + "/".join(("tmp", "safequery.sql")),
        "guard detail referenced bearer token in adapter output",
    ],
)
def test_guard_denial_reason_sanitizer_blocks_paths_and_credentials(
    detail: str,
) -> None:
    assert (
        _sanitized_guard_denial_reason(_rejected_guard_evaluation(detail))
        == "SQL guard rejected the generated candidate."
    )


@pytest.mark.parametrize(
    "detail",
    [
        "Guard rejected external reference https://docs.example.test/guard/reason",
        "Guard rejected tokenized input from the parser stage",
        "Guard rejected message from the secretariat review queue",
    ],
)
def test_guard_denial_reason_sanitizer_keeps_benign_reason_terms(
    detail: str,
) -> None:
    assert _sanitized_guard_denial_reason(_rejected_guard_evaluation(detail)) == detail


def test_guard_denial_reason_sanitizer_keeps_truncation_within_cap() -> None:
    detail = "Guard rejection detail " + ("x" * 260)

    sanitized = _sanitized_guard_denial_reason(_rejected_guard_evaluation(detail))

    assert sanitized is not None
    assert len(sanitized) == request_preview_service._MAX_DENIAL_REASON_LENGTH
    assert sanitized.endswith("...")


def test_http_preview_guard_denied_candidate_remains_non_executable(
    monkeypatch,
) -> None:
    fixture = _load_preview_to_execute_golden_fixture(
        "http_preview_generation_guard_denied_no_executable_candidate"
    )
    scenario = next(
        scenario
        for scenario in list_postgresql_evaluation_scenarios()
        if scenario.scenario_id == fixture["scenario_id"]
    )
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
    adapter = _RecordingHTTPPreviewAdapter(scenario.canonical_sql)

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
        _seed_authoritative_source_governance(
            session,
            source_id=scenario.source.source_id,
            source_family=scenario.source.source_family,
            source_flavor=scenario.source.source_flavor,
            dataset_contract_version=scenario.source.dataset_contract_version,
            schema_snapshot_version=scenario.source.schema_snapshot_version,
        )
        app_session = create_test_application_session(subject)

        response = client.post(
            "/requests/preview",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={
                "question": scenario.prompt,
                "source_id": scenario.source.source_id,
            },
        )

        assert response.status_code == 200
        response_payload = response.json()
        assert response_payload["candidate"]["source_id"] == fixture["source_id"]
        assert response_payload["candidate"]["source_family"] == fixture["source_family"]
        assert response_payload["candidate"]["source_flavor"] == fixture["source_flavor"]
        assert response_payload["candidate"]["dataset_contract_version"] == (
            fixture["dataset_contract_version"]
        )
        assert response_payload["candidate"]["schema_snapshot_version"] == (
            fixture["schema_snapshot_version"]
        )
        assert response_payload["candidate"]["guard_status"] == "blocked"
        assert response_payload["candidate"]["state"] == fixture["candidate_state"]
        assert response_payload["candidate"]["primary_deny_code"] == (
            fixture["primary_deny_code"]
        )
        assert response_payload["evaluation"]["state"] == "blocked"
        assert response_payload["evaluation"]["primary_deny_code"] == (
            fixture["primary_deny_code"]
        )

        persisted_request = session.execute(select(PreviewRequest)).scalar_one()
        persisted_candidate = session.execute(select(PreviewCandidate)).scalar_one()
        persisted_approval = session.execute(
            select(PreviewCandidateApproval)
        ).scalar_one()
        persisted_guard_event = (
            session.execute(
                select(PreviewAuditEvent).where(
                    PreviewAuditEvent.event_type == "guard_evaluated"
                )
            )
            .scalars()
            .one()
        )
        persisted_preview_events = (
            session.execute(
                select(PreviewAuditEvent).order_by(PreviewAuditEvent.lifecycle_order)
            )
            .scalars()
            .all()
        )

        assert [event.event_type for event in persisted_preview_events] == (
            fixture["expected_preview_events"]
        )
        assert persisted_request.source_id == fixture["source_id"]
        assert persisted_request.request_state == "blocked"
        assert persisted_candidate.guard_status == "blocked"
        assert persisted_candidate.candidate_state == fixture["candidate_state"]
        assert persisted_candidate.source_id == fixture["source_id"]
        assert persisted_approval.approval_state == (
            fixture["approval_state_after_preview"]
        )
        assert persisted_approval.approved_sql is None
        assert persisted_approval.executed_at is None
        assert persisted_guard_event.primary_deny_code == fixture["primary_deny_code"]
        assert persisted_guard_event.denial_cause == "guard_rejected"
        assert persisted_guard_event.audit_payload["source_id"] == fixture["source_id"]
        assert persisted_guard_event.audit_payload["query_candidate_id"] == (
            persisted_candidate.candidate_id
        )
        assert persisted_guard_event.audit_payload["guard_decision"] == (
            fixture["guard_decision"]
        )
        assert persisted_guard_event.audit_payload["guard_version"] == (
            "postgresql-guard-v1"
        )
        assert persisted_guard_event.audit_payload["release_gate_scenario"] == {
            "scenario_id": fixture["scenario_id"],
            "source_id": fixture["source_id"],
            "candidate_id": persisted_candidate.candidate_id,
            "guard_decision": fixture["guard_decision"],
            "guard_audit_event_id": str(persisted_guard_event.event_id),
        }

        workflow_payload = get_operator_workflow_snapshot(session).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        candidate_item = next(
            item
            for item in workflow_payload["history"]
            if item["itemType"] == "candidate"
        )
        assert candidate_item["guardStatus"] == "blocked"
        assert candidate_item["primaryDenyCode"] == fixture["primary_deny_code"]
        assert candidate_item["auditEvents"][0]["guardDecision"] == "reject"
        serialized_workflow = str(workflow_payload)
        assert "credential" not in serialized_workflow.lower()

        calls: list[str] = []
        app.state.execution_query_runner = lambda **_: calls.append("called")
        execute_response = client.post(
            f"/candidates/{persisted_candidate.candidate_id}/execute",
            headers=app_session.headers,
            cookies=app_session.cookies,
            json={"selected_source_id": fixture["source_id"]},
        )

        assert execute_response.status_code == 403
        execute_payload = execute_response.json()
        assert execute_payload["error"] == {
            "code": "execution_denied",
            "message": "Candidate execution was denied.",
        }
        assert len(execute_payload["audit"]["events"]) == 1
        denial_event = execute_payload["audit"]["events"][0]
        assert denial_event["event_type"] == "execution_denied"
        assert denial_event["primary_deny_code"] == "DENY_CANDIDATE_NOT_APPROVED"
        assert denial_event["denial_cause"] == "candidate_not_approved"
        assert calls == []
        persisted_post_execute_events = (
            session.execute(
                select(PreviewAuditEvent).order_by(PreviewAuditEvent.lifecycle_order)
            )
            .scalars()
            .all()
        )
        persisted_post_execute_events = persisted_post_execute_events[
            len(persisted_preview_events) :
        ]
        assert [event.event_type for event in persisted_post_execute_events] == (
            fixture["expected_execution_events"]
        )
        assert all(
            event.candidate_id == persisted_candidate.candidate_id
            for event in persisted_post_execute_events
        )
        assert all(
            event.source_id == fixture["source_id"]
            for event in persisted_post_execute_events
        )
        assert "execution_run_id" not in str(
            persisted_guard_event.audit_payload["release_gate_scenario"]
        )
        assert calls == []
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_http_preview_submission_rejects_malformed_guard_decision_without_approval(
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
    monkeypatch.setitem(
        request_preview_service._SQL_GUARD_EVALUATOR_BY_SOURCE_FAMILY,
        "postgresql",
        lambda _: {"decision": "allow"},
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
                "code": "preview_guard_malformed",
                "message": "SQL Guard returned malformed decision data.",
            }
        }
        assert session.execute(select(PreviewCandidate)).scalars().all() == []
        assert session.execute(select(PreviewCandidateApproval)).scalars().all() == []
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_http_preview_submission_uses_mssql_guard_profile(
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
    adapter = _RecordingHTTPPreviewAdapter(
        " SELECT TOP 50 vendor_id FROM finance.approved_vendor_spend; "
    )

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
        _seed_authoritative_source_governance(
            session,
            source_family="mssql",
            source_flavor="analytics",
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

        assert response.status_code == 200
        response_payload = response.json()
        assert response_payload["candidate"]["guard_status"] == "allow"
        assert response_payload["candidate"]["source_family"] == "mssql"

        persisted_candidate = session.execute(select(PreviewCandidate)).scalar_one()
        persisted_guard_event = (
            session.execute(
                select(PreviewAuditEvent).where(
                    PreviewAuditEvent.event_type == "guard_evaluated"
                )
            )
            .scalars()
            .one()
        )

        assert persisted_candidate.guard_status == "allow"
        assert persisted_candidate.source_family == "mssql"
        assert persisted_guard_event.audit_payload["guard_version"] == "mssql-guard-v1"
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_preview_lifecycle_audit_guard_version_fails_closed_when_mapping_missing(
    monkeypatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed_authoritative_source_governance(
            session,
            source_family="mssql",
            source_flavor="analytics",
        )
        resolved_source = session.execute(select(RegisteredSource)).scalar_one()
        dataset_contract = session.execute(select(DatasetContract)).scalar_one()
        schema_snapshot = session.execute(select(SchemaSnapshot)).scalar_one()

        monkeypatch.delitem(
            request_preview_service._GUARD_VERSION_BY_SOURCE_FAMILY,
            "mssql",
        )

        with pytest.raises(PreviewSubmissionContractError) as exc_info:
            _build_preview_lifecycle_audit_events(
                resolved_source=resolved_source,
                dataset_contract=dataset_contract,
                schema_snapshot=schema_snapshot,
                audit_context=PreviewAuditContext(
                    occurred_at=datetime.now(timezone.utc),
                    request_id="preview-request-unmapped-guard",
                    correlation_id="preview-correlation-unmapped-guard",
                    user_subject="user:alice",
                    session_id="session-unmapped-guard",
                    query_candidate_id="preview-candidate-unmapped-guard",
                    candidate_owner_subject="user:alice",
                    auth_source="test-helper",
                ),
                guard_evaluation=SQLGuardEvaluation(
                    decision="allow",
                    profile="common",
                    canonical_sql="SELECT 1",
                    source=None,
                    rejections=[],
                ),
            )

        assert "Unsupported source family 'mssql' cannot be guarded." == str(
            exc_info.value
        )


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


def test_preview_revision_from_completed_run_creates_new_authoritative_attempt() -> None:
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
    completed_run_id = uuid4()

    with Session(engine) as session:
        _seed_authoritative_source_governance(session)

        submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by quarterly spend",
                source_id="sap-approved-spend",
            ),
            subject,
            session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                request_id="preview-request-original",
                correlation_id="preview-correlation-original",
                user_subject="user:alice",
                session_id="session-original",
                query_candidate_id="preview-candidate-original",
                candidate_owner_subject="user:alice",
                auth_source="test-helper",
            ),
        )
        request_before = session.scalar(
            select(PreviewRequest).where(
                PreviewRequest.request_id == "preview-request-original"
            )
        )
        candidate_before = session.scalar(
            select(PreviewCandidate).where(
                PreviewCandidate.candidate_id == "preview-candidate-original"
            )
        )
        assert request_before is not None
        assert candidate_before is not None
        original_request_db_id = request_before.id
        original_candidate_db_id = candidate_before.id

        request_preview_service.persist_execution_audit_events(
            session,
            candidate_id="preview-candidate-original",
            audit_events=[
                SourceAwareAuditEvent(
                    event_id=completed_run_id,
                    event_type="execution_completed",
                    occurred_at=datetime(2026, 1, 2, 3, 5, 0, tzinfo=timezone.utc),
                    request_id="preview-request-original",
                    correlation_id="preview-correlation-original",
                    user_subject="user:alice",
                    session_id="session-original",
                    query_candidate_id="preview-candidate-original",
                    candidate_owner_subject="user:alice",
                    source_id="sap-approved-spend",
                    source_family="postgresql",
                    source_flavor="warehouse",
                    dataset_contract_version=1,
                    schema_snapshot_version=1,
                    execution_row_count=3,
                    result_truncated=False,
                )
            ],
        )

        response = submit_preview_request(
            PreviewSubmissionRequest(
                question="Show approved vendors by yearly spend",
                source_id="sap-approved-spend",
                revise_from={
                    "item_type": "run",
                    "request_id": "preview-request-original",
                    "candidate_id": "preview-candidate-original",
                    "run_id": str(completed_run_id),
                },
            ),
            subject,
            session,
            audit_context=PreviewAuditContext(
                occurred_at=datetime(2026, 1, 2, 3, 6, 0, tzinfo=timezone.utc),
                request_id="preview-request-revised",
                correlation_id="preview-correlation-revised",
                user_subject="user:alice",
                session_id="session-revised",
                query_candidate_id="preview-candidate-revised",
                candidate_owner_subject="user:alice",
                auth_source="test-helper",
            ),
        )

        persisted_requests = (
            session.execute(select(PreviewRequest).order_by(PreviewRequest.request_id))
            .scalars()
            .all()
        )
        persisted_candidates = (
            session.execute(
                select(PreviewCandidate).order_by(PreviewCandidate.candidate_id)
            )
            .scalars()
            .all()
        )
        original_request = next(
            request
            for request in persisted_requests
            if request.request_id == "preview-request-original"
        )
        revised_request = next(
            request
            for request in persisted_requests
            if request.request_id == "preview-request-revised"
        )
        original_candidate = next(
            candidate
            for candidate in persisted_candidates
            if candidate.candidate_id == "preview-candidate-original"
        )
        revised_candidate = next(
            candidate
            for candidate in persisted_candidates
            if candidate.candidate_id == "preview-candidate-revised"
        )

    assert response.request.revision_context is not None
    assert response.request.revision_context.run_id == str(completed_run_id)
    assert len(persisted_requests) == 2
    assert len(persisted_candidates) == 2
    assert original_request.id == original_request_db_id
    assert original_request.request_text == "Show approved vendors by quarterly spend"
    assert original_request.revised_from_run_id is None
    assert original_candidate.id == original_candidate_db_id
    assert original_candidate.request_id == "preview-request-original"
    assert original_candidate.revised_from_run_id is None
    assert revised_request.request_text == "Show approved vendors by yearly spend"
    assert revised_request.revised_from_request_id == "preview-request-original"
    assert revised_request.revised_from_candidate_id == "preview-candidate-original"
    assert revised_request.revised_from_run_id == str(completed_run_id)
    assert revised_request.revised_from_source_id == "sap-approved-spend"
    assert revised_candidate.request_id == "preview-request-revised"
    assert revised_candidate.revised_from_request_id == "preview-request-original"
    assert revised_candidate.revised_from_candidate_id == "preview-candidate-original"
    assert revised_candidate.revised_from_run_id == str(completed_run_id)
    assert revised_candidate.revised_from_source_id == "sap-approved-spend"


def test_preview_revision_rejects_reused_authoritative_attempt_ids() -> None:
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
            occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            request_id="preview-request-original",
            correlation_id="preview-correlation-original",
            user_subject="user:alice",
            session_id="session-original",
            query_candidate_id="preview-candidate-original",
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

        with pytest.raises(PreviewSubmissionContractError) as exc_info:
            submit_preview_request(
                PreviewSubmissionRequest(
                    question="Show approved vendors by yearly spend",
                    source_id="sap-approved-spend",
                    revise_from={
                        "item_type": "candidate",
                        "request_id": "preview-request-original",
                        "candidate_id": "preview-candidate-original",
                    },
                ),
                subject,
                session,
                audit_context=audit_context.model_copy(deep=True),
            )

        persisted_request = session.scalar(
            select(PreviewRequest).where(
                PreviewRequest.request_id == "preview-request-original"
            )
        )
        persisted_candidates = session.execute(select(PreviewCandidate)).scalars().all()

    assert str(exc_info.value) == (
        "Revised preview attempts must use new request and candidate identities."
    )
    assert persisted_request is not None
    assert persisted_request.request_text == "Show approved vendors by quarterly spend"
    assert len(persisted_candidates) == 1
    assert persisted_candidates[0].candidate_id == "preview-candidate-original"


def test_preview_candidate_reapproval_clears_invalidation_and_refreshes_expiry() -> None:
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
            occurred_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            request_id="preview-request-approval-reset",
            correlation_id="preview-correlation-approval-reset",
            user_subject="user:alice",
            session_id="session-approval-reset",
            query_candidate_id="preview-candidate-approval-reset",
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
            audit_context=audit_context,
        )
        preview_candidate = session.execute(select(PreviewCandidate)).scalar_one()
        approval = session.execute(select(PreviewCandidateApproval)).scalar_one()
        original_expiry = approval.approval_expires_at

        invalidated_at = datetime(2026, 1, 1, 12, 2, tzinfo=timezone.utc)
        _persist_candidate_approval_record(
            session,
            preview_candidate=preview_candidate,
            authenticated_subject_id="user:alice",
            session_id="session-approval-reset",
            occurred_at=invalidated_at,
            candidate_state="guard_rejected",
            guard_status="blocked",
        )
        assert approval.approval_state == "invalidated"
        assert approval.invalidated_at == invalidated_at

        reapproved_at = datetime(2026, 1, 1, 12, 4, tzinfo=timezone.utc)
        _persist_candidate_approval_record(
            session,
            preview_candidate=preview_candidate,
            authenticated_subject_id="user:alice",
            session_id="session-approval-reset",
            occurred_at=reapproved_at,
            candidate_state="preview_ready",
            guard_status="allow",
        )

    assert approval.approval_state == "approved"
    assert approval.invalidated_at is None
    assert approval.approval_expires_at == reapproved_at + timedelta(minutes=5)
    assert approval.approval_expires_at != original_expiry


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


def test_preview_candidate_approval_model_ties_identity_to_preview_candidate() -> None:
    foreign_keys = {
        tuple(element.parent.name for element in constraint.elements): tuple(
            element.target_fullname for element in constraint.elements
        )
        for constraint in PreviewCandidateApproval.__table__.foreign_key_constraints
    }

    assert foreign_keys[
        (
            "preview_candidate_id",
            "candidate_id",
            "request_id",
            "registered_source_id",
            "source_id",
            "source_family",
            "dataset_contract_version",
            "schema_snapshot_version",
        )
    ] == (
        "preview_candidates.id",
        "preview_candidates.candidate_id",
        "preview_candidates.request_id",
        "preview_candidates.registered_source_id",
        "preview_candidates.source_id",
        "preview_candidates.source_family",
        "preview_candidates.dataset_contract_version",
        "preview_candidates.schema_snapshot_version",
    )
