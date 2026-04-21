from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Uuid as SqlAlchemyUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SchemaSnapshotReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class SchemaSnapshot(Base):
    __tablename__ = "schema_snapshots"
    __table_args__ = (
        UniqueConstraint("registered_source_id", "snapshot_version"),
        UniqueConstraint("registered_source_id", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    registered_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registered_sources.id"),
        nullable=False,
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[SchemaSnapshotReviewStatus] = mapped_column(
        SqlEnum(
            SchemaSnapshotReviewStatus,
            name="schema_snapshot_review_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
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
