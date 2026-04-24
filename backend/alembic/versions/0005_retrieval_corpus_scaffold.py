"""Add source-aware retrieval corpus assets.

This revision adds application-owned retrieval corpus records. The records are
bound to one registered source, one active dataset contract version, and one
schema snapshot version so governed search can return advisory context without
becoming SQL execution authority.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_retrieval_corpus_scaffold"
down_revision: str | None = "0004_schema_snapshot_linkage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

retrieval_corpus_asset_kind = sa.Enum(
    "glossary_term",
    "metric_definition",
    "question_exemplar",
    "analytic_playbook",
    "schema_context",
    name="retrieval_corpus_asset_kind",
    native_enum=False,
    create_constraint=True,
)

retrieval_corpus_asset_status = sa.Enum(
    "approved",
    "withdrawn",
    name="retrieval_corpus_asset_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "retrieval_corpus_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.String(length=255), nullable=False),
        sa.Column("registered_source_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_flavor", sa.String(length=64), nullable=True),
        sa.Column("dataset_contract_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_contract_version", sa.Integer(), nullable=False),
        sa.Column("schema_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("schema_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("asset_kind", retrieval_corpus_asset_kind, nullable=False),
        sa.Column(
            "status",
            retrieval_corpus_asset_status,
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("citation_label", sa.String(length=255), nullable=False),
        sa.Column("owner_binding", sa.String(length=255), nullable=False),
        sa.Column("visibility_binding", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["registered_source_id"],
            ["registered_sources.id"],
            name=op.f("fk_retrieval_corpus_assets_registered_source_id_registered_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_contract_id"],
            ["dataset_contracts.id"],
            name=op.f("fk_retrieval_corpus_assets_dataset_contract_id_dataset_contracts"),
        ),
        sa.ForeignKeyConstraint(
            ["schema_snapshot_id"],
            ["schema_snapshots.id"],
            name=op.f("fk_retrieval_corpus_assets_schema_snapshot_id_schema_snapshots"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_corpus_assets")),
        sa.UniqueConstraint(
            "registered_source_id",
            "asset_id",
            name=op.f("uq_retrieval_corpus_assets_registered_source_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("retrieval_corpus_assets")
