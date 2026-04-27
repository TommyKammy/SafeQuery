from __future__ import annotations

import logging
import os
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models.dataset_contract import DatasetContract, DatasetContractDataset
from app.db.models.schema_snapshot import SchemaSnapshot, SchemaSnapshotReviewStatus
from app.db.models.source_registry import RegisteredSource, SourceActivationPosture
from app.features.auth.context import AuthenticatedSubject
from app.features.execution import (
    ExecutionConnectorSelectionError,
    MSSQLExecutionRuntimeUnavailable,
    PostgreSQLExecutionRuntimeUnavailable,
    check_mssql_execution_runtime_readiness,
    check_postgresql_execution_runtime_readiness,
    select_execution_connector,
)
from app.services.candidate_lifecycle import SourceBoundCandidateMetadata
from app.services.demo_source_seed import (
    DEMO_DEV_GOVERNANCE_BINDING,
    DEMO_DEV_SUBJECT_ID,
    DEMO_SOURCE_ID,
)
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)

logger = logging.getLogger(__name__)

DoctorStatus = Literal["pass", "fail", "degraded"]
BackendProbeMode = Literal["probe", "served_route"]


@dataclass(frozen=True)
class HttpProbeResponse:
    status_code: int
    body: str
    content_type: str = ""


class FirstRunDoctorCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: DoctorStatus
    message: str
    detail: dict[str, object] = Field(default_factory=dict)


class FirstRunDoctorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DoctorStatus
    checks: list[FirstRunDoctorCheck]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _alembic_heads() -> set[str]:
    config = Config(str(_backend_root() / "alembic.ini"))
    config.set_main_option("script_location", str(_backend_root() / "alembic"))
    return set(ScriptDirectory.from_config(config).get_heads())


def _aggregate_status(checks: list[FirstRunDoctorCheck]) -> DoctorStatus:
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "degraded" for check in checks):
        return "degraded"
    return "pass"


def _check_database(
    session: Session,
    database_probe: Callable[[], None] | None,
) -> FirstRunDoctorCheck:
    try:
        if database_probe is None:
            session.execute(text("SELECT 1")).scalar_one()
        else:
            database_probe()
    except Exception as exc:
        return FirstRunDoctorCheck(
            name="database",
            status="fail",
            message=(
                "Application database is not reachable. Start the local stack and "
                "verify SAFEQUERY_APP_POSTGRES_URL before product evaluation."
            ),
            detail={"error": exc.__class__.__name__},
        )

    return FirstRunDoctorCheck(
        name="database",
        status="pass",
        message="Application database connectivity is ready.",
    )


def _check_migrations(session: Session) -> FirstRunDoctorCheck:
    try:
        applied_revisions = {
            str(row[0])
            for row in session.execute(text("SELECT version_num FROM alembic_version"))
        }
    except SQLAlchemyError as exc:
        return FirstRunDoctorCheck(
            name="migrations",
            status="fail",
            message=(
                "Alembic migration state is missing. Run `alembic upgrade head` "
                "before opening the product evaluation flow."
            ),
            detail={"error": exc.__class__.__name__},
        )

    try:
        expected_heads = _alembic_heads()
    except Exception as exc:
        return FirstRunDoctorCheck(
            name="migrations",
            status="fail",
            message=(
                "Unable to read Alembic migration metadata. Verify "
                "`backend/alembic.ini` and migration scripts are available, "
                "then rerun the first-run doctor."
            ),
            detail={
                "error": exc.__class__.__name__,
                "applied_revisions": sorted(applied_revisions),
            },
        )
    if not applied_revisions:
        return FirstRunDoctorCheck(
            name="migrations",
            status="fail",
            message=(
                "Alembic migration state is empty. Run `alembic upgrade head` "
                "before opening the product evaluation flow."
            ),
            detail={"expected_heads": sorted(expected_heads), "applied_revisions": []},
        )
    if applied_revisions != expected_heads:
        return FirstRunDoctorCheck(
            name="migrations",
            status="fail",
            message=(
                "Application database is not at the current Alembic head. Run "
                "`alembic upgrade head`, then rerun the first-run doctor."
            ),
            detail={
                "expected_heads": sorted(expected_heads),
                "applied_revisions": sorted(applied_revisions),
            },
        )

    return FirstRunDoctorCheck(
        name="migrations",
        status="pass",
        message="Alembic migration posture is current.",
        detail={"heads": sorted(expected_heads)},
    )


def _active_demo_sources(session: Session) -> list[RegisteredSource]:
    return list(
        session.scalars(
            select(RegisteredSource)
            .where(RegisteredSource.activation_posture == SourceActivationPosture.ACTIVE)
            .where(RegisteredSource.source_id == DEMO_SOURCE_ID)
            .order_by(RegisteredSource.source_id)
        )
    )


def _check_source_registry(
    active_demo_sources: list[RegisteredSource],
) -> FirstRunDoctorCheck:
    if not active_demo_sources:
        return FirstRunDoctorCheck(
            name="source_registry",
            status="fail",
            message=(
                "No active demo source is registered. Run "
                "`python -m app.cli.seed_demo_source` after migrations complete."
            ),
        )

    return FirstRunDoctorCheck(
        name="source_registry",
        status="pass",
        message="Active demo source registry record is present.",
        detail={"source_ids": [source.source_id for source in active_demo_sources]},
    )


def _load_linked_contract(
    session: Session,
    source: RegisteredSource | None,
) -> DatasetContract | None:
    if source is None or source.dataset_contract_id is None:
        return None
    return session.get(DatasetContract, source.dataset_contract_id)


def _load_linked_snapshot(
    session: Session,
    source: RegisteredSource | None,
) -> SchemaSnapshot | None:
    if source is None or source.schema_snapshot_id is None:
        return None
    return session.get(SchemaSnapshot, source.schema_snapshot_id)


def _check_dataset_contract(
    session: Session,
    source: RegisteredSource | None,
    contract: DatasetContract | None,
    snapshot: SchemaSnapshot | None,
) -> FirstRunDoctorCheck:
    if source is None or contract is None:
        detail = {"source_id": source.source_id} if source is not None else {}
        return FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message=(
                "Active demo source has no linked dataset contract. Rerun "
                "`python -m app.cli.seed_demo_source` and verify the seed completed."
            ),
            detail=detail,
        )
    if contract.registered_source_id != source.id:
        return FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message="Linked dataset contract does not belong to the active demo source.",
            detail={"source_id": source.source_id},
        )
    if snapshot is not None and contract.schema_snapshot_id != snapshot.id:
        return FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message="Linked dataset contract does not point at the source schema snapshot.",
            detail={"source_id": source.source_id},
        )

    dataset_count = session.scalar(
        select(func.count()).select_from(DatasetContractDataset).where(
            DatasetContractDataset.dataset_contract_id == contract.id
        )
    )
    if not dataset_count:
        return FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message=(
                "Linked dataset contract has no allowed datasets. Rerun "
                "`python -m app.cli.seed_demo_source` before product evaluation."
            ),
            detail={"source_id": source.source_id},
        )

    return FirstRunDoctorCheck(
        name="dataset_contract",
        status="pass",
        message="Linked dataset contract and allowed datasets are present.",
        detail={
            "source_id": source.source_id,
            "contract_version": contract.contract_version,
            "dataset_count": int(dataset_count),
        },
    )


def _check_schema_snapshot(
    source: RegisteredSource | None,
    snapshot: SchemaSnapshot | None,
) -> FirstRunDoctorCheck:
    if source is None or snapshot is None:
        detail = {"source_id": source.source_id} if source is not None else {}
        return FirstRunDoctorCheck(
            name="schema_snapshot",
            status="fail",
            message=(
                "Active demo source has no linked schema snapshot. Rerun "
                "`python -m app.cli.seed_demo_source` and verify migrations are current."
            ),
            detail=detail,
        )
    if snapshot.registered_source_id != source.id:
        return FirstRunDoctorCheck(
            name="schema_snapshot",
            status="fail",
            message="Linked schema snapshot does not belong to the active demo source.",
            detail={"source_id": source.source_id},
        )
    if snapshot.review_status is not SchemaSnapshotReviewStatus.APPROVED:
        return FirstRunDoctorCheck(
            name="schema_snapshot",
            status="fail",
            message="Linked schema snapshot is not approved for first-run evaluation.",
            detail={
                "source_id": source.source_id,
                "review_status": snapshot.review_status.value,
            },
        )

    return FirstRunDoctorCheck(
        name="schema_snapshot",
        status="pass",
        message="Approved schema snapshot is linked to the active demo source.",
        detail={
            "source_id": source.source_id,
            "snapshot_version": snapshot.snapshot_version,
        },
    )


def _check_entitlement_seed(
    source: RegisteredSource | None,
    contract: DatasetContract | None,
) -> FirstRunDoctorCheck:
    subject = AuthenticatedSubject(
        subject_id=DEMO_DEV_SUBJECT_ID,
        governance_bindings=frozenset({DEMO_DEV_GOVERNANCE_BINDING}),
    )
    if source is None or contract is None:
        detail = {"source_id": source.source_id} if source is not None else {}
        return FirstRunDoctorCheck(
            name="entitlement_seed",
            status="fail",
            message=(
                "The dev/local entitlement seed cannot be evaluated until the "
                "demo source and dataset contract are present."
            ),
            detail=detail,
        )
    try:
        ensure_subject_is_entitled_for_source(subject, source, contract)
    except SourceEntitlementError as exc:
        return FirstRunDoctorCheck(
            name="entitlement_seed",
            status="fail",
            message=(
                "The dev/local entitlement seed is missing or incoherent. Rerun "
                "`python -m app.cli.seed_demo_source` before product evaluation."
            ),
            detail={"source_id": source.source_id, "error": str(exc)},
        )

    return FirstRunDoctorCheck(
        name="entitlement_seed",
        status="pass",
        message="Dev/local entitlement seed is coherent for the demo operator.",
        detail={"source_id": source.source_id, "subject_id": DEMO_DEV_SUBJECT_ID},
    )


def _check_execution_connector(
    source: RegisteredSource | None,
    contract: DatasetContract | None,
    snapshot: SchemaSnapshot | None,
) -> FirstRunDoctorCheck:
    if source is None or contract is None or snapshot is None:
        detail = {"source_id": source.source_id} if source is not None else {}
        return FirstRunDoctorCheck(
            name="execution_connector",
            status="fail",
            message=(
                "Demo source execution connector readiness cannot be evaluated until "
                "the source, dataset contract, and schema snapshot are present."
            ),
            detail=detail,
        )

    try:
        selection = select_execution_connector(
            candidate_source=SourceBoundCandidateMetadata(
                source_id=source.source_id,
                source_family=source.source_family,
                source_flavor=source.source_flavor,
                dataset_contract_version=contract.contract_version,
                schema_snapshot_version=snapshot.snapshot_version,
            )
        )
    except ExecutionConnectorSelectionError as exc:
        return FirstRunDoctorCheck(
            name="execution_connector",
            status="fail",
            message=(
                "Active demo source is not execution-ready because no backend-owned "
                "execution connector matches its source binding."
            ),
            detail={
                "source_id": source.source_id,
                "source_family": source.source_family,
                "source_flavor": source.source_flavor,
                "deny_code": exc.deny_code,
            },
        )

    runtime_dependency = None
    try:
        if selection.connector_id == "mssql_readonly":
            runtime_dependency = "pyodbc/odbc-driver-18"
            runtime_detail = check_mssql_execution_runtime_readiness()
        elif selection.connector_id == "postgresql_readonly":
            runtime_dependency = "psycopg"
            runtime_detail = check_postgresql_execution_runtime_readiness()
        else:
            runtime_detail = {}
    except (
        MSSQLExecutionRuntimeUnavailable,
        PostgreSQLExecutionRuntimeUnavailable,
    ) as exc:
        family_name = "MSSQL" if selection.source_family == "mssql" else "PostgreSQL"
        detail: dict[str, object] = {
            "source_id": selection.source_id,
            "source_family": selection.source_family,
            "source_flavor": selection.source_flavor,
            "connector_id": selection.connector_id,
            "ownership": selection.ownership,
            "runtime_status": "unavailable",
            "error": exc.__class__.__name__,
        }
        if runtime_dependency is not None:
            detail["runtime_dependency"] = runtime_dependency
        return FirstRunDoctorCheck(
            name="execution_connector",
            status="fail",
            message=(
                f"{family_name} driver runtime is unavailable for the "
                "backend-owned execution connector."
            ),
            detail=detail,
        )

    detail = {
        "source_id": selection.source_id,
        "source_family": selection.source_family,
        "source_flavor": selection.source_flavor,
        "connector_id": selection.connector_id,
        "ownership": selection.ownership,
    }
    if runtime_detail:
        detail["runtime_status"] = "available"
        detail["runtime"] = runtime_detail

    return FirstRunDoctorCheck(
        name="execution_connector",
        status="pass",
        message="Backend-owned execution connector is ready for the active demo source.",
        detail=detail,
    )


def _source_governance_checks_for_source(
    session: Session,
    source: RegisteredSource,
) -> list[FirstRunDoctorCheck]:
    contract = _load_linked_contract(session, source)
    snapshot = _load_linked_snapshot(session, source)
    return [
        _check_dataset_contract(session, source, contract, snapshot),
        _check_schema_snapshot(source, snapshot),
        _check_entitlement_seed(source, contract),
        _check_execution_connector(source, contract, snapshot),
    ]


def _source_governance_checks(
    session: Session,
    active_sources: list[RegisteredSource],
) -> list[FirstRunDoctorCheck]:
    selected_checks: list[FirstRunDoctorCheck] | None = None
    for source in active_sources:
        candidate_checks = _source_governance_checks_for_source(session, source)
        if all(check.status == "pass" for check in candidate_checks):
            return candidate_checks
        if selected_checks is None:
            selected_checks = candidate_checks

    if selected_checks is not None:
        return selected_checks
    return [
        _check_dataset_contract(session, None, None, None),
        _check_schema_snapshot(None, None),
        _check_entitlement_seed(None, None),
        _check_execution_connector(None, None, None),
    ]


def _source_governance_unavailable_checks(
    exc: SQLAlchemyError,
) -> list[FirstRunDoctorCheck]:
    error_detail = {"error": exc.__class__.__name__}
    return [
        FirstRunDoctorCheck(
            name="source_registry",
            status="fail",
            message=(
                "Unable to read demo source readiness data from the database. "
                "Run `alembic upgrade head`, then rerun "
                "`python -m app.cli.seed_demo_source`."
            ),
            detail=error_detail,
        ),
        FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message=(
                "Dataset contract readiness could not be evaluated because "
                "source readiness data is unavailable."
            ),
        ),
        FirstRunDoctorCheck(
            name="schema_snapshot",
            status="fail",
            message=(
                "Schema snapshot readiness could not be evaluated because "
                "source readiness data is unavailable."
            ),
        ),
        FirstRunDoctorCheck(
            name="entitlement_seed",
            status="fail",
            message=(
                "Entitlement seed readiness could not be evaluated because "
                "source readiness data is unavailable."
            ),
        ),
        FirstRunDoctorCheck(
            name="execution_connector",
            status="fail",
            message=(
                "Execution connector readiness could not be evaluated because "
                "source readiness data is unavailable."
            ),
        ),
    ]


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _http_get(url: str) -> HttpProbeResponse:
    parsed_url = urlsplit(url)
    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP(S) probe URLs are supported.")

    request = Request(url, headers={"Accept": "application/json, text/html"})
    try:
        with urlopen(request, timeout=2.0) as response:  # noqa: S310
            body = response.read(64_000).decode("utf-8", errors="replace")
            return HttpProbeResponse(
                status_code=response.status,
                body=body,
                content_type=response.headers.get_content_type(),
            )
    except HTTPError as exc:
        body = exc.read(64_000).decode("utf-8", errors="replace")
        return HttpProbeResponse(
            status_code=exc.code,
            body=body,
            content_type=exc.headers.get_content_type(),
        )


def _health_status(body: str) -> object:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get("status")


def _check_backend_served_route(backend_base_url: str) -> FirstRunDoctorCheck:
    normalized = _normalize_base_url(backend_base_url)
    return FirstRunDoctorCheck(
        name="backend",
        status="pass",
        message=(
            "Backend doctor route is serving this response; run the CLI doctor "
            "to probe the configured backend health URL."
        ),
        detail={
            "doctor_route": "/doctor/first-run",
            "backend_base_url": normalized,
        },
    )


def _check_backend_health(
    backend_base_url: str,
    probe: Callable[[str], HttpProbeResponse],
) -> FirstRunDoctorCheck:
    health_url = f"{_normalize_base_url(backend_base_url)}/health"
    try:
        response = probe(health_url)
    except Exception as exc:
        return FirstRunDoctorCheck(
            name="backend",
            status="fail",
            message=(
                "Backend health endpoint is not reachable. Start the backend "
                "service and verify SAFEQUERY_BACKEND_BASE_URL "
                "(or NEXT_PUBLIC_API_BASE_URL if unset) points at it."
            ),
            detail={"health_url": health_url, "error": exc.__class__.__name__},
        )

    health_status = _health_status(response.body)
    if response.status_code >= 400 or health_status != "ok":
        detail: dict[str, object] = {
            "health_url": health_url,
            "status_code": response.status_code,
        }
        if health_status is not None:
            detail["health_status"] = health_status
        return FirstRunDoctorCheck(
            name="backend",
            status="fail",
            message=(
                "Backend health endpoint returned an unhealthy response. "
                "Check backend logs, database connectivity, and "
                "SAFEQUERY_BACKEND_BASE_URL before product evaluation."
            ),
            detail=detail,
        )

    return FirstRunDoctorCheck(
        name="backend",
        status="pass",
        message="Backend health endpoint is reachable and healthy.",
        detail={"health_url": health_url, "status_code": response.status_code},
    )


def _check_frontend_surface(
    frontend_base_url: str,
    backend_base_url: str,
    probe: Callable[[str], HttpProbeResponse],
) -> FirstRunDoctorCheck:
    normalized_frontend_url = _normalize_base_url(frontend_base_url)
    normalized_backend_url = _normalize_base_url(backend_base_url)
    try:
        response = probe(normalized_frontend_url)
    except Exception as exc:
        return FirstRunDoctorCheck(
            name="frontend",
            status="fail",
            message=(
                "Frontend app surface is not reachable. Start the frontend "
                "service and verify SAFEQUERY_FRONTEND_BASE_URL before product "
                "evaluation."
            ),
            detail={
                "frontend_url": normalized_frontend_url,
                "backend_base_url": normalized_backend_url,
                "error": exc.__class__.__name__,
            },
        )

    if response.status_code >= 400:
        return FirstRunDoctorCheck(
            name="frontend",
            status="fail",
            message=(
                "Frontend app surface returned an unhealthy response. Check "
                "the frontend service and SAFEQUERY_FRONTEND_BASE_URL."
            ),
            detail={
                "frontend_url": normalized_frontend_url,
                "backend_base_url": normalized_backend_url,
                "status_code": response.status_code,
            },
        )

    if "SafeQuery" not in response.body:
        return FirstRunDoctorCheck(
            name="frontend",
            status="fail",
            message=(
                "Frontend did not return the SafeQuery app surface. Verify "
                "SAFEQUERY_FRONTEND_BASE_URL points at the local SafeQuery UI."
            ),
            detail={
                "frontend_url": normalized_frontend_url,
                "backend_base_url": normalized_backend_url,
                "status_code": response.status_code,
            },
        )

    return FirstRunDoctorCheck(
        name="frontend",
        status="pass",
        message="Frontend app surface is reachable.",
        detail={
            "frontend_url": normalized_frontend_url,
            "backend_base_url": normalized_backend_url,
            "status_code": response.status_code,
        },
    )


def run_first_run_doctor(
    session: Session,
    *,
    database_probe: Callable[[], None] | None = None,
    backend_base_url: str | None = None,
    frontend_base_url: str | None = None,
    backend_probe: Callable[[str], HttpProbeResponse] | None = None,
    frontend_probe: Callable[[str], HttpProbeResponse] | None = None,
    backend_probe_mode: BackendProbeMode = "probe",
) -> FirstRunDoctorResult:
    resolved_backend_base_url = backend_base_url or os.getenv(
        "SAFEQUERY_BACKEND_BASE_URL",
        os.getenv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000"),
    )
    resolved_frontend_base_url = frontend_base_url or os.getenv(
        "SAFEQUERY_FRONTEND_BASE_URL", "http://localhost:3000"
    )

    checks = [
        _check_database(session, database_probe),
        _check_migrations(session),
    ]

    try:
        active_sources = _active_demo_sources(session)
        checks.append(_check_source_registry(active_sources))
        checks.extend(_source_governance_checks(session, active_sources))
    except SQLAlchemyError as exc:
        logger.exception("First-run doctor could not read source governance data.")
        checks.extend(_source_governance_unavailable_checks(exc))

    if backend_probe_mode == "served_route":
        checks.append(_check_backend_served_route(resolved_backend_base_url))
    else:
        checks.append(
            _check_backend_health(
                resolved_backend_base_url,
                backend_probe or _http_get,
            )
        )

    checks.append(
        _check_frontend_surface(
            resolved_frontend_base_url,
            resolved_backend_base_url,
            frontend_probe or _http_get,
        )
    )

    return FirstRunDoctorResult(status=_aggregate_status(checks), checks=checks)
