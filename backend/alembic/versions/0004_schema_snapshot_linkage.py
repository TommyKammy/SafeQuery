"""Add per-source schema snapshot linkage.

This revision adds source-scoped schema snapshots plus the linkage required to
bind dataset contracts and active registry pointers to one approved schema view
per registered source.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_schema_snapshot_linkage"
down_revision: str | None = "0003_dataset_contract_scaffold"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

schema_snapshot_review_status = sa.Enum(
    "pending",
    "approved",
    "rejected",
    "superseded",
    name="schema_snapshot_review_status",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "schema_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("registered_source_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("review_status", schema_snapshot_review_status, nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
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
            name=op.f("fk_schema_snapshots_registered_source_id_registered_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schema_snapshots")),
        sa.UniqueConstraint(
            "registered_source_id",
            "snapshot_version",
            name=op.f("uq_schema_snapshots_registered_source_id_snapshot_version"),
        ),
        sa.UniqueConstraint(
            "registered_source_id",
            "id",
            name=op.f("uq_schema_snapshots_registered_source_id_id"),
        ),
    )

    op.add_column(
        "dataset_contracts",
        sa.Column("schema_snapshot_id", sa.Uuid(), nullable=False),
    )
    op.create_unique_constraint(
        op.f("uq_dataset_contracts_registered_source_id_id"),
        "dataset_contracts",
        ["registered_source_id", "id"],
    )
    op.create_foreign_key(
        op.f("fk_dataset_contracts_schema_snapshot_id_schema_snapshots"),
        "dataset_contracts",
        "schema_snapshots",
        ["schema_snapshot_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f(
            "fk_dataset_contracts_registered_source_id_schema_snapshot_id_schema_snapshots"
        ),
        "dataset_contracts",
        "schema_snapshots",
        ["registered_source_id", "schema_snapshot_id"],
        ["registered_source_id", "id"],
    )

    op.create_foreign_key(
        op.f(
            "fk_registered_sources_id_dataset_contract_id_dataset_contracts"
        ),
        "registered_sources",
        "dataset_contracts",
        ["id", "dataset_contract_id"],
        ["registered_source_id", "id"],
    )
    op.create_foreign_key(
        op.f(
            "fk_registered_sources_id_schema_snapshot_id_schema_snapshots"
        ),
        "registered_sources",
        "schema_snapshots",
        ["id", "schema_snapshot_id"],
        ["registered_source_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_registered_sources_id_schema_snapshot_id_schema_snapshots"),
        "registered_sources",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_registered_sources_id_dataset_contract_id_dataset_contracts"),
        "registered_sources",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f(
            "fk_dataset_contracts_registered_source_id_schema_snapshot_id_schema_snapshots"
        ),
        "dataset_contracts",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_dataset_contracts_schema_snapshot_id_schema_snapshots"),
        "dataset_contracts",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("uq_dataset_contracts_registered_source_id_id"),
        "dataset_contracts",
        type_="unique",
    )
    op.drop_column("dataset_contracts", "schema_snapshot_id")
    op.drop_table("schema_snapshots")
