from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy import Uuid as SqlAlchemyUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegisteredSource(Base):
    __tablename__ = "registered_sources"
    __table_args__ = (
        UniqueConstraint("source_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    source_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    source_family: Mapped[str] = mapped_column(String(64), nullable=False)
    source_flavor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    activation_posture: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        SqlAlchemyUuid,
        nullable=True,
    )
    dialect_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        SqlAlchemyUuid,
        nullable=True,
    )
    dataset_contract_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        SqlAlchemyUuid,
        nullable=True,
    )
    schema_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        SqlAlchemyUuid,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
