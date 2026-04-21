from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, Enum as SqlEnum, String, UniqueConstraint, func
from sqlalchemy import Uuid as SqlAlchemyUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceActivationPosture(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    RETIRED = "retired"

    @property
    def is_executable(self) -> bool:
        return self is SourceActivationPosture.ACTIVE


class RegisteredSource(Base):
    __tablename__ = "registered_sources"
    __table_args__ = (
        UniqueConstraint("source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_family: Mapped[str] = mapped_column(String(64), nullable=False)
    source_flavor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    activation_posture: Mapped[SourceActivationPosture] = mapped_column(
        SqlEnum(
            SourceActivationPosture,
            name="source_activation_posture",
            native_enum=False,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
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
    execution_policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        SqlAlchemyUuid,
        nullable=True,
    )
    connection_reference: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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
        onupdate=func.now(),
    )
