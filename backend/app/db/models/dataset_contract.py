from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Uuid as SqlAlchemyUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DatasetContractDatasetKind(str, Enum):
    VIEW = "view"
    TABLE = "table"
    MATERIALIZED_VIEW = "materialized_view"


class DatasetContract(Base):
    __tablename__ = "dataset_contracts"
    __table_args__ = (
        UniqueConstraint("registered_source_id", "contract_version"),
        UniqueConstraint("registered_source_id", "id"),
        ForeignKeyConstraint(
            ["registered_source_id", "schema_snapshot_id"],
            ["schema_snapshots.registered_source_id", "schema_snapshots.id"],
        ),
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
    schema_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schema_snapshots.id"),
        nullable=False,
    )
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_binding: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    security_review_binding: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    exception_policy_binding: Mapped[Optional[str]] = mapped_column(
        String(255),
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
        onupdate=func.now(),
    )


class DatasetContractDataset(Base):
    __tablename__ = "dataset_contract_datasets"
    __table_args__ = (
        UniqueConstraint("dataset_contract_id", "schema_name", "dataset_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    dataset_contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_contracts.id"),
        nullable=False,
    )
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_kind: Mapped[DatasetContractDatasetKind] = mapped_column(
        SqlEnum(
            DatasetContractDatasetKind,
            name="dataset_contract_dataset_kind",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
