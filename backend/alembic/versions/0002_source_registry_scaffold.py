"""Add the initial registered sources persistence scaffold.

This revision creates the first application-owned source registry table without
introducing execution routing, source governance, or live connector behavior.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_source_registry_scaffold"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registered_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("display_label", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=64), nullable=False),
        sa.Column("source_flavor", sa.String(length=64), nullable=True),
        sa.Column("activation_posture", sa.String(length=32), nullable=False),
        sa.Column("connector_profile_id", sa.Uuid(), nullable=True),
        sa.Column("dialect_profile_id", sa.Uuid(), nullable=True),
        sa.Column("dataset_contract_id", sa.Uuid(), nullable=True),
        sa.Column("schema_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("execution_policy_id", sa.Uuid(), nullable=True),
        sa.Column("connection_reference", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registered_sources")),
        sa.UniqueConstraint(
            "source_id",
            name=op.f("uq_registered_sources_source_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("registered_sources")
