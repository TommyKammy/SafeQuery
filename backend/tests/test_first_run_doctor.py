from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.services.first_run_doctor as first_run_doctor_service
from app.db.base import Base
from app.db.models.dataset_contract import DatasetContract
from app.db.models.source_registry import RegisteredSource
from app.services.demo_source_seed import DEMO_SOURCE_UUID, seed_demo_source_governance
from app.services.first_run_doctor import run_first_run_doctor


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
                "VALUES ('0005_retrieval_corpus_scaffold')"
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
        result = run_first_run_doctor(session, database_probe=lambda: None)

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
        result = run_first_run_doctor(session, database_probe=lambda: None)

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["migrations"]["status"] == "fail"
    assert "Unable to read Alembic migration metadata" in sections["migrations"][
        "message"
    ]
    assert sections["migrations"]["detail"] == {
        "error": "RuntimeError",
        "applied_revisions": ["0005_retrieval_corpus_scaffold"],
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
    assert sections["backend"]["status"] == "pass"
    assert sections["frontend"]["status"] == "pass"


def test_first_run_doctor_fails_closed_when_source_seed_is_missing() -> None:
    with _session_scope() as session:
        result = run_first_run_doctor(session, database_probe=lambda: None)

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

        result = run_first_run_doctor(session, database_probe=lambda: None)

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["source_registry"]["status"] == "fail"
    assert sections["source_registry"]["detail"] == {"error": "OperationalError"}
    assert sections["dataset_contract"]["status"] == "fail"
    assert sections["schema_snapshot"]["status"] == "fail"
    assert sections["entitlement_seed"]["status"] == "fail"
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

        result = run_first_run_doctor(session, database_probe=lambda: None)

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

        result = run_first_run_doctor(session, database_probe=lambda: None)

    sections = _doctor_sections(result.model_dump(mode="json"))
    assert result.status == "fail"
    assert sections["entitlement_seed"]["status"] == "fail"
    assert "dev/local entitlement seed" in sections["entitlement_seed"]["message"]
