from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Uuid as SqlAlchemyUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PreviewRequest(Base):
    __tablename__ = "preview_requests"
    __table_args__ = (
        UniqueConstraint("request_id"),
        UniqueConstraint("id", "registered_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registered_sources.id"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_family: Mapped[str] = mapped_column(String(64), nullable=False)
    source_flavor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_contracts.id"),
        nullable=False,
    )
    dataset_contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schema_snapshots.id"),
        nullable=False,
    )
    schema_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    authenticated_subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    governance_bindings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entitlement_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    request_state: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PreviewCandidate(Base):
    __tablename__ = "preview_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ("preview_request_id", "registered_source_id"),
            ("preview_requests.id", "preview_requests.registered_source_id"),
        ),
        UniqueConstraint("candidate_id"),
        UniqueConstraint("request_id", "source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    candidate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    preview_request_id: Mapped[uuid.UUID] = mapped_column(SqlAlchemyUuid, nullable=False)
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    registered_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registered_sources.id"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_family: Mapped[str] = mapped_column(String(64), nullable=False)
    source_flavor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_contracts.id"),
        nullable=False,
    )
    dataset_contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schema_snapshots.id"),
        nullable=False,
    )
    schema_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    authenticated_subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_sql: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    guard_status: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_state: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PreviewAuditEvent(Base):
    __tablename__ = "preview_audit_events"
    __table_args__ = (UniqueConstraint("event_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(SqlAlchemyUuid, nullable=False)
    lifecycle_order: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preview_requests.id"),
        nullable=False,
    )
    preview_candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("preview_candidates.id"),
        nullable=True,
    )
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    candidate_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    causation_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        SqlAlchemyUuid,
        nullable=True,
    )
    authenticated_subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    governance_bindings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entitlement_decision: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    entitlement_source_bindings: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    application_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_family: Mapped[str] = mapped_column(String(64), nullable=False)
    source_flavor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_contract_version: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    schema_snapshot_version: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    primary_deny_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    denial_cause: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    candidate_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    audit_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
