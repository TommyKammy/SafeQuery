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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Uuid as SqlAlchemyUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RetrievalCorpusAssetKind(str, Enum):
    GLOSSARY_TERM = "glossary_term"
    METRIC_DEFINITION = "metric_definition"
    QUESTION_EXEMPLAR = "question_exemplar"
    ANALYTIC_PLAYBOOK = "analytic_playbook"
    SCHEMA_CONTEXT = "schema_context"


class RetrievalCorpusAssetStatus(str, Enum):
    APPROVED = "approved"
    WITHDRAWN = "withdrawn"


class RetrievalCorpusAsset(Base):
    __tablename__ = "retrieval_corpus_assets"
    __table_args__ = (
        UniqueConstraint("registered_source_id", "asset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        SqlAlchemyUuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    asset_id: Mapped[str] = mapped_column(String(255), nullable=False)
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
    asset_kind: Mapped[RetrievalCorpusAssetKind] = mapped_column(
        SqlEnum(
            RetrievalCorpusAssetKind,
            name="retrieval_corpus_asset_kind",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[RetrievalCorpusAssetStatus] = mapped_column(
        SqlEnum(
            RetrievalCorpusAssetStatus,
            name="retrieval_corpus_asset_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RetrievalCorpusAssetStatus.APPROVED,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    citation_label: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_binding: Mapped[str] = mapped_column(String(255), nullable=False)
    visibility_binding: Mapped[str] = mapped_column(String(255), nullable=False)
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
