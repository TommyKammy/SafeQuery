from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal

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
from app.services.demo_source_seed import (
    DEMO_DEV_GOVERNANCE_BINDING,
    DEMO_DEV_SUBJECT_ID,
)
from app.services.source_entitlements import (
    SourceEntitlementError,
    ensure_subject_is_entitled_for_source,
)

DoctorStatus = Literal["pass", "fail", "degraded"]


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

    expected_heads = _alembic_heads()
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
            .where(RegisteredSource.source_flavor == "demo")
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
        return FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message=(
                "Active demo source has no linked dataset contract. Rerun "
                "`python -m app.cli.seed_demo_source` and verify the seed completed."
            ),
        )
    if contract.registered_source_id != source.id:
        return FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message="Linked dataset contract does not belong to the active demo source.",
        )
    if snapshot is not None and contract.schema_snapshot_id != snapshot.id:
        return FirstRunDoctorCheck(
            name="dataset_contract",
            status="fail",
            message="Linked dataset contract does not point at the source schema snapshot.",
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
        )

    return FirstRunDoctorCheck(
        name="dataset_contract",
        status="pass",
        message="Linked dataset contract and allowed datasets are present.",
        detail={
            "contract_version": contract.contract_version,
            "dataset_count": int(dataset_count),
        },
    )


def _check_schema_snapshot(
    source: RegisteredSource | None,
    snapshot: SchemaSnapshot | None,
) -> FirstRunDoctorCheck:
    if source is None or snapshot is None:
        return FirstRunDoctorCheck(
            name="schema_snapshot",
            status="fail",
            message=(
                "Active demo source has no linked schema snapshot. Rerun "
                "`python -m app.cli.seed_demo_source` and verify migrations are current."
            ),
        )
    if snapshot.registered_source_id != source.id:
        return FirstRunDoctorCheck(
            name="schema_snapshot",
            status="fail",
            message="Linked schema snapshot does not belong to the active demo source.",
        )
    if snapshot.review_status is not SchemaSnapshotReviewStatus.APPROVED:
        return FirstRunDoctorCheck(
            name="schema_snapshot",
            status="fail",
            message="Linked schema snapshot is not approved for first-run evaluation.",
            detail={"review_status": snapshot.review_status.value},
        )

    return FirstRunDoctorCheck(
        name="schema_snapshot",
        status="pass",
        message="Approved schema snapshot is linked to the active demo source.",
        detail={"snapshot_version": snapshot.snapshot_version},
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
        return FirstRunDoctorCheck(
            name="entitlement_seed",
            status="fail",
            message=(
                "The dev/local entitlement seed cannot be evaluated until the "
                "demo source and dataset contract are present."
            ),
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
            detail={"error": str(exc)},
        )

    return FirstRunDoctorCheck(
        name="entitlement_seed",
        status="pass",
        message="Dev/local entitlement seed is coherent for the demo operator.",
        detail={"subject_id": DEMO_DEV_SUBJECT_ID},
    )


def _check_backend_expectation(backend_base_url: str) -> FirstRunDoctorCheck:
    normalized = backend_base_url.rstrip("/")
    return FirstRunDoctorCheck(
        name="backend",
        status="pass",
        message="Backend readiness endpoint is expected to be reachable after startup.",
        detail={"health_url": f"{normalized}/health"},
    )


def _check_frontend_expectation(
    frontend_base_url: str,
    backend_base_url: str,
) -> FirstRunDoctorCheck:
    return FirstRunDoctorCheck(
        name="frontend",
        status="pass",
        message="Frontend is expected to call the configured backend base URL after startup.",
        detail={
            "frontend_url": frontend_base_url.rstrip("/"),
            "backend_base_url": backend_base_url.rstrip("/"),
        },
    )


def run_first_run_doctor(
    session: Session,
    *,
    database_probe: Callable[[], None] | None = None,
    backend_base_url: str | None = None,
    frontend_base_url: str | None = None,
) -> FirstRunDoctorResult:
    resolved_backend_base_url = backend_base_url or os.getenv(
        "NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000"
    )
    resolved_frontend_base_url = frontend_base_url or os.getenv(
        "SAFEQUERY_FRONTEND_BASE_URL", "http://localhost:3000"
    )

    checks = [
        _check_database(session, database_probe),
        _check_migrations(session),
    ]

    active_sources = _active_demo_sources(session)
    primary_source = active_sources[0] if active_sources else None
    contract = _load_linked_contract(session, primary_source)
    snapshot = _load_linked_snapshot(session, primary_source)

    checks.extend(
        [
            _check_source_registry(active_sources),
            _check_dataset_contract(session, primary_source, contract, snapshot),
            _check_schema_snapshot(primary_source, snapshot),
            _check_entitlement_seed(primary_source, contract),
            _check_backend_expectation(resolved_backend_base_url),
            _check_frontend_expectation(
                resolved_frontend_base_url,
                resolved_backend_base_url,
            ),
        ]
    )

    return FirstRunDoctorResult(status=_aggregate_status(checks), checks=checks)
